"""End-to-end tests of the discovery pipeline through the real API + real
Postgres:

    search results -> normalisation -> deduplication -> deterministic
    pre-filter -> fake LLM extraction/matching -> deterministic scoring
    -> ranked opportunity feed

Uses a FakeLLMProvider (no network/API key needed) and fake JobSources
injected via dependency overrides / factory seams (no Adzuna/Lever
credentials needed), exactly like test_analysis_workflow.py does for the
plain analysis pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.ai.providers.factory import get_llm_provider
from app.ai.providers.fake_provider import FakeLLMProvider
from app.ai.schemas.matching import LLMMatchingOutput, LLMRequirementMatchItem
from app.api.deps import get_db, get_discovery_service
from app.domain.candidate import Candidate, CandidatePreferences, Evidence
from app.domain.company_watchlist import CompanyWatchlistEntry
from app.domain.enums import AIOperationType, ATSType, EvidenceTier, JobSourceType, SeniorityLevel
from app.domain.gmail_credential import GmailCredential
from app.domain.job import ExtractedJob, ExtractedRequirement
from app.ingestion.job_source import JobSource, RawJobPosting
from app.main import app
from app.repositories.candidate_repository import CandidateRepository
from app.repositories.company_watchlist_repository import CompanyWatchlistRepository
from app.repositories.gmail_credential_repository import GmailCredentialRepository
from app.services.discovery_service import DiscoveryService


class _FakeSource(JobSource):
    source_type = JobSourceType.ADZUNA

    def __init__(self, postings: list[RawJobPosting]) -> None:
        self._postings = postings

    def fetch(self) -> list[RawJobPosting]:
        return self._postings


def test_full_discovery_pipeline(db):
    candidate = CandidateRepository().upsert(
        db,
        Candidate(
            name="Integration Test Candidate",
            evidence=[
                Evidence(
                    source_type="project",
                    source_label="AFL Pricing Engine",
                    statement="Built a FastAPI backend with SQLAlchemy and Python.",
                    skill_tags=["python", "fastapi"],
                )
            ],
            preferences=CandidatePreferences(preferred_locations=["Melbourne"]),
        ),
    )
    evidence_id = str(candidate.evidence[0].id)

    fake_provider = FakeLLMProvider()
    fake_provider.set_response(
        AIOperationType.JOB_EXTRACTION,
        ExtractedJob(
            title="Junior Backend Engineer",
            company="Acme Corp",
            location="Melbourne, VIC",
            requirements=[
                ExtractedRequirement(
                    name="Python",
                    raw_phrase="Python",
                    category="technical_skill",
                    importance="required",
                )
            ],
        ),
    )
    fake_provider.set_response(
        AIOperationType.REQUIREMENT_MATCHING,
        LLMMatchingOutput(
            matches=[
                LLMRequirementMatchItem(
                    requirement_name="Python",
                    tier=EvidenceTier.EXPLICIT,
                    confidence=0.9,
                    evidence_ids=[evidence_id],
                    evidence_summary="Directly demonstrated.",
                )
            ]
        ),
    )

    postings = [
        # Eligible - should survive dedup + pre-filter and get analysed.
        RawJobPosting(
            title="Junior Backend Engineer",
            company="Acme Corp",
            location="Melbourne, VIC",
            source_type=JobSourceType.ADZUNA,
            raw_description="Junior Backend Engineer role requiring Python.",
            external_id="job-1",
        ),
        # Clearly senior - should be pre-filter rejected, never reaching the LLM.
        RawJobPosting(
            title="Senior Principal Backend Engineer",
            company="Acme Corp",
            location="Melbourne, VIC",
            source_type=JobSourceType.ADZUNA,
            raw_description="Senior Principal role requiring 12+ years experience.",
            external_id="job-2",
        ),
        # Duplicate of the first posting (same external_id) - must be deduped.
        RawJobPosting(
            title="Junior Backend Engineer",
            company="Acme Corp",
            location="Melbourne, VIC",
            source_type=JobSourceType.ADZUNA,
            raw_description="Junior Backend Engineer role requiring Python.",
            external_id="job-1",
        ),
    ]

    discovery_service = DiscoveryService(
        llm_provider=fake_provider,
        adzuna_source_factory=lambda config: _FakeSource(postings),
    )

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_llm_provider] = lambda: fake_provider
    app.dependency_overrides[get_discovery_service] = lambda: discovery_service
    try:
        client = TestClient(app)

        profile_resp = client.post(
            "/api/discovery/search-profiles",
            json={
                "name": "Early Career Backend",
                "keywords": ["backend engineer"],
                "locations": ["Melbourne"],
                "include_remote": True,
                "max_experience_level": SeniorityLevel.GRADUATE.value,
                "excluded_keywords": [],
                "enabled": True,
                "source_config": {},
            },
        )
        assert profile_resp.status_code == 201
        profile_id = profile_resp.json()["id"]

        run_resp = client.post("/api/discovery/run", json={"search_profile_ids": [profile_id]})
        assert run_resp.status_code == 200, run_resp.text
        run = run_resp.json()

        assert run["counts"]["retrieved"] == 3
        assert run["counts"]["new"] == 2  # dedup collapsed the third posting
        assert run["counts"]["duplicates"] == 1
        assert run["counts"]["prefilter_rejected"] == 1  # the senior posting
        assert run["counts"]["eligible"] == 1
        assert run["counts"]["analysed"] == 1
        assert run["estimated_cost_usd"] == 0.0  # FakeLLMProvider reports zero cost

        # Default feed view hides pre-filter-rejected jobs.
        feed_resp = client.get("/api/discovery/opportunities")
        assert feed_resp.status_code == 200
        feed = feed_resp.json()
        assert feed["total"] == 1
        opportunity = feed["items"][0]
        assert opportunity["title"] == "Junior Backend Engineer"
        assert opportunity["status"] == "analysed"
        assert opportunity["overall_score"] is not None
        assert opportunity["priority"] is not None
        assert "Python" in opportunity["strong_matches"]
        assert len(opportunity["why_summary"]) > 0

        # Rejected jobs are visible when explicitly requested.
        full_feed_resp = client.get("/api/discovery/opportunities?include_rejected=true")
        assert full_feed_resp.status_code == 200
        full_feed = full_feed_resp.json()
        assert full_feed["total"] == 2
        rejected = next(o for o in full_feed["items"] if o["status"] == "prefilter_rejected")
        assert rejected["prefilter_reason"] is not None
    finally:
        app.dependency_overrides.clear()


def test_multi_source_dedup_and_shortlist(db):
    """The PART 19 end-to-end scenario: an Adzuna result + a direct Lever
    posting for the SAME job (different source, same underlying role) +
    one genuinely distinct Lever job at the same company ->
    normalisation -> duplicate resolution (exact id, since both share the
    same external id path isn't realistic here, so this exercises the
    deterministic-fingerprint stage instead, which is the common real case
    for an aggregator vs. a direct listing with slightly different URLs) ->
    pre-filter -> analysis prioritisation -> fake LLM analysis -> existing
    evidence matching -> deterministic fit score -> ranked shortlist.

    Verifies the same job from two sources becomes ONE canonical
    opportunity while BOTH source observations are preserved.
    """
    candidate = CandidateRepository().upsert(
        db,
        Candidate(
            name="Multi Source Candidate",
            evidence=[
                Evidence(
                    source_type="project",
                    source_label="Data Project",
                    statement="Built ML pipelines in Python.",
                    skill_tags=["python", "machine learning"],
                )
            ],
        ),
    )
    evidence_id = str(candidate.evidence[0].id)

    CompanyWatchlistRepository().create(
        db,
        CompanyWatchlistEntry(
            company_name="Data Co",
            ats_type=ATSType.LEVER,
            ats_identifier="data-co",
            preferred_locations=[],
        ),
    )

    fake_provider = FakeLLMProvider()
    fake_provider.set_response(
        AIOperationType.JOB_EXTRACTION,
        ExtractedJob(
            title="Graduate Data Scientist",
            company="Data Co",
            requirements=[
                ExtractedRequirement(
                    name="Python",
                    raw_phrase="Python",
                    category="technical_skill",
                    importance="required",
                )
            ],
        ),
    )
    fake_provider.set_response(
        AIOperationType.REQUIREMENT_MATCHING,
        LLMMatchingOutput(
            matches=[
                LLMRequirementMatchItem(
                    requirement_name="Python",
                    tier=EvidenceTier.EXPLICIT,
                    confidence=0.9,
                    evidence_ids=[evidence_id],
                    evidence_summary="Directly demonstrated.",
                )
            ]
        ),
    )

    shared_description = (
        "Graduate Data Scientist role at Data Co. Requires Python and machine learning skills."
    )

    adzuna_postings = [
        RawJobPosting(
            title="Graduate Data Scientist",
            company="Data Co",
            location="Melbourne",
            source_type=JobSourceType.ADZUNA,
            raw_description=shared_description,
            external_id="adzuna-1",
            source_url="https://adzuna.example/jobs/1",
        )
    ]
    lever_postings = [
        # Same underlying job as the Adzuna posting above, but via the
        # direct employer feed with its own id/URL - must be recognised as
        # the SAME opportunity (deterministic description-fingerprint match).
        RawJobPosting(
            title="Graduate Data Scientist",
            company="Data Co",
            location="Melbourne",
            source_type=JobSourceType.LEVER,
            raw_description=shared_description,
            external_id="lever-1",
            source_url="https://jobs.lever.co/data-co/1",
        ),
        # A genuinely different role at the same company.
        RawJobPosting(
            title="Graduate Backend Engineer",
            company="Data Co",
            location="Melbourne",
            source_type=JobSourceType.LEVER,
            raw_description="Graduate Backend Engineer role at Data Co requiring Java and SQL.",
            external_id="lever-2",
            source_url="https://jobs.lever.co/data-co/2",
        ),
    ]

    discovery_service = DiscoveryService(
        llm_provider=fake_provider,
        adzuna_source_factory=lambda config: _FakeSource(adzuna_postings),
        ats_source_factory=lambda entry: _FakeSource(lever_postings),
    )

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_llm_provider] = lambda: fake_provider
    app.dependency_overrides[get_discovery_service] = lambda: discovery_service
    try:
        client = TestClient(app)

        profile_resp = client.post(
            "/api/discovery/search-profiles",
            json={
                "name": "Data roles",
                "keywords": ["data scientist"],
                "locations": [],
                "include_remote": True,
                "excluded_keywords": [],
                "enabled": True,
                "source_config": {},
            },
        )
        assert profile_resp.status_code == 201

        run_resp = client.post("/api/discovery/run", json={})
        assert run_resp.status_code == 200, run_resp.text
        run = run_resp.json()

        # 1 (Adzuna) + 2 (Lever) retrieved; the Adzuna/Lever pair collapses
        # into one canonical job, so only 2 canonical DiscoveredJobs exist.
        assert run["counts"]["retrieved"] == 3
        assert run["counts"]["new"] == 2
        assert run["counts"]["duplicates"] == 1
        assert run["counts"]["analysed"] == 2

        feed = client.get("/api/discovery/opportunities?include_rejected=true").json()
        assert feed["total"] == 2

        merged = next(o for o in feed["items"] if o["title"] == "Graduate Data Scientist")
        # Direct Lever posting should be promoted as canonical over Adzuna.
        assert merged["source_url"] == "https://jobs.lever.co/data-co/1"

        history_resp = client.get(f"/api/discovery/runs/{run['id']}")
        assert history_resp.status_code == 200
    finally:
        app.dependency_overrides.clear()

    # Both source observations survive the merge - verified directly via
    # the repository since there's no dedicated API for this yet.
    from app.repositories.discovered_job_repository import DiscoveredJobRepository

    discovered = DiscoveredJobRepository()
    canonical = next(
        d for d in discovered.list_all(db) if d.title == "Graduate Data Scientist"
    )
    observations = discovered.list_observations(db, canonical.id)
    assert {o.source.value for o in observations} == {"adzuna", "lever"}
    assert {o.external_id for o in observations} == {"adzuna-1", "lever-1"}


def test_dependency_override_isolation():
    """Sanity check that dependency_overrides is actually cleared between
    tests (guards against a previous test leaking state)."""
    assert get_db not in app.dependency_overrides
    assert get_llm_provider not in app.dependency_overrides
    assert get_discovery_service not in app.dependency_overrides


def test_mixed_location_ats_results_only_australian_jobs_survive_to_feed(db):
    """The required product-simplification scenario: a mixed international
    ATS feed (the realistic Lever/Greenhouse situation - one company board
    posting to many countries) must only ever surface its Australian
    postings in the recommended feed, regardless of source, and regardless
    of whether the company's watchlist entry configured any location
    preference at all - the eligibility gate is hard and independent of any
    per-profile configuration (Part 1/3 of the brief).

    normalisation -> Australian eligibility gate -> discovery -> analysis
    -> recommendation feed - only Melbourne/Sydney/Hobart survive; San
    Francisco, London, and a generic "Remote" posting must not appear in
    the default feed, even though "Remote" isn't confidently foreign
    either (LOCATION_UNCONFIRMED, not INELIGIBLE - still hidden).
    """
    candidate = CandidateRepository().upsert(
        db,
        Candidate(
            name="AU Candidate",
            evidence=[
                Evidence(
                    source_type="project",
                    source_label="Data Project",
                    statement="Built data pipelines in Python.",
                    skill_tags=["python"],
                )
            ],
            preferences=CandidatePreferences(preferred_locations=["Melbourne"]),
        ),
    )
    evidence_id = str(candidate.evidence[0].id)

    # Deliberately NO preferred_locations configured on the watchlist entry -
    # the old bug: an empty locations list was treated as "no constraint,
    # accept everything". The hard gate must reject non-AU postings from
    # this company regardless.
    CompanyWatchlistRepository().create(
        db,
        CompanyWatchlistEntry(
            company_name="Global Co",
            ats_type=ATSType.LEVER,
            ats_identifier="global-co",
            preferred_locations=[],
        ),
    )

    fake_provider = FakeLLMProvider()
    fake_provider.set_response(
        AIOperationType.JOB_EXTRACTION,
        ExtractedJob(
            title="Graduate Engineer",
            company="Global Co",
            requirements=[
                ExtractedRequirement(
                    name="Python", raw_phrase="Python",
                    category="technical_skill", importance="required",
                )
            ],
        ),
    )
    fake_provider.set_response(
        AIOperationType.REQUIREMENT_MATCHING,
        LLMMatchingOutput(
            matches=[
                LLMRequirementMatchItem(
                    requirement_name="Python", tier=EvidenceTier.EXPLICIT, confidence=0.9,
                    evidence_ids=[evidence_id], evidence_summary="Directly demonstrated.",
                )
            ]
        ),
    )

    postings = [
        RawJobPosting(
            title="Graduate Software Engineer", company="Global Co", location="Melbourne, VIC",
            source_type=JobSourceType.LEVER,
            raw_description=(
                "Join our Melbourne team building payment reconciliation systems in Python "
                "and PostgreSQL. Work with a small squad on internal tooling for the finance team."
            ),
            external_id="melbourne-1",
        ),
        RawJobPosting(
            title="Graduate Data Analyst", company="Global Co", location="Sydney NSW",
            source_type=JobSourceType.LEVER,
            raw_description=(
                "Our Sydney analytics team is hiring a graduate to build dashboards and reports "
                "using SQL and Python, working closely with the marketing department."
            ),
            external_id="sydney-1",
        ),
        RawJobPosting(
            title="Graduate DevOps Engineer", company="Global Co", location="Hobart TAS",
            source_type=JobSourceType.LEVER,
            raw_description=(
                "Based in Hobart, help automate deployment pipelines with Python scripting and "
                "container tooling, supporting the wider infrastructure team."
            ),
            external_id="hobart-1",
        ),
        RawJobPosting(
            title="Graduate Machine Learning Engineer", company="Global Co",
            location="San Francisco",
            source_type=JobSourceType.LEVER,
            raw_description=(
                "Our San Francisco headquarters is hiring a graduate ML engineer to train "
                "recommendation models in Python, collaborating with the product research group."
            ),
            external_id="sf-1",
        ),
        RawJobPosting(
            title="Graduate Backend Developer", company="Global Co", location="London",
            source_type=JobSourceType.LEVER,
            raw_description=(
                "Our London office needs a graduate backend developer to work on billing "
                "microservices in Python, reporting to the platform engineering lead."
            ),
            external_id="london-1",
        ),
        RawJobPosting(
            title="Graduate Support Engineer", company="Global Co", location="Remote",
            source_type=JobSourceType.LEVER,
            raw_description=(
                "Fully remote, open worldwide - provide technical customer support and write "
                "small Python automation scripts to resolve common support tickets."
            ),
            external_id="remote-1",
        ),
    ]

    discovery_service = DiscoveryService(
        llm_provider=fake_provider,
        adzuna_source_factory=lambda config: _FakeSource([]),
        ats_source_factory=lambda entry: _FakeSource(postings),
    )

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_llm_provider] = lambda: fake_provider
    app.dependency_overrides[get_discovery_service] = lambda: discovery_service
    try:
        client = TestClient(app)

        run_resp = client.post("/api/discovery/run", json={})
        assert run_resp.status_code == 200, run_resp.text
        run = run_resp.json()
        assert run["counts"]["retrieved"] == 6
        assert run["counts"]["new"] == 6
        # SF, London, Remote all rejected by the hard eligibility gate
        # before ever reaching per-profile pre-filter or analysis.
        assert run["counts"]["prefilter_rejected"] == 3
        assert run["counts"]["eligible"] == 3
        assert run["counts"]["analysed"] == 3

        default_feed = client.get("/api/discovery/opportunities").json()
        assert default_feed["total"] == 3
        titles = {item["title"] for item in default_feed["items"]}
        assert titles == {
            "Graduate Software Engineer",
            "Graduate Data Analyst",
            "Graduate DevOps Engineer",
        }

        # The excluded postings are still stored (for audit/debugging) -
        # just correctly classified as geographically ineligible/unconfirmed,
        # never silently deleted.
        full_feed = client.get("/api/discovery/opportunities?include_rejected=true").json()
        assert full_feed["total"] == 6
    finally:
        app.dependency_overrides.clear()


def test_seek_and_linkedin_alert_emails_only_relevant_australian_jobs_survive_to_feed(db):
    """The Part 24 required scenario for the Gmail job-alert milestone: a
    SEEK alert (Graduate Software Engineer Melbourne / Senior Marketing
    Manager Sydney / Junior Data Analyst Hobart) and a LinkedIn alert
    (Associate AI Engineer Melbourne / Senior Software Architect San
    Francisco / a duplicate of the SEEK Graduate Software Engineer posting)
    through email parsing -> deduplication -> Australia/relevance
    filtering -> existing AI matching -> ranking.

    No SearchProfile or CompanyWatchlist entry is configured at all - Gmail
    being connected is the only thing that makes discovery possible (Part
    21: the app must work with Adzuna disabled and watchlists empty).

    Expected default feed: exactly the 3 relevant Australian roles
    (Graduate Software Engineer Melbourne, Junior Data Analyst Hobart,
    Associate AI Engineer Melbourne) - no overseas roles (San Francisco),
    no irrelevant/senior roles (Marketing Manager), and the duplicate
    LinkedIn posting merged rather than double-counted.
    """
    candidate = CandidateRepository().upsert(
        db,
        Candidate(
            name="Gmail Integration Test Candidate",
            evidence=[
                Evidence(
                    source_type="project",
                    source_label="AI Project",
                    statement="Built machine learning models and data pipelines in Python.",
                    skill_tags=["python", "machine learning"],
                )
            ],
            preferences=CandidatePreferences(
                preferred_locations=["Melbourne", "Hobart"],
                preferred_technologies=["Python", "Machine Learning"],
            ),
        ),
    )
    evidence_id = str(candidate.evidence[0].id)

    GmailCredentialRepository().save(
        db,
        GmailCredential(
            connected_email="candidate@example.com",
            refresh_token_encrypted="irrelevant-for-this-test",
            connected_at=datetime.now(UTC),
        ),
    )

    fake_provider = FakeLLMProvider()
    fake_provider.set_response(
        AIOperationType.JOB_EXTRACTION,
        ExtractedJob(
            title="Graduate Role",
            company="Some Co",
            requirements=[
                ExtractedRequirement(
                    name="Python", raw_phrase="Python",
                    category="technical_skill", importance="required",
                )
            ],
        ),
    )
    fake_provider.set_response(
        AIOperationType.REQUIREMENT_MATCHING,
        LLMMatchingOutput(
            matches=[
                LLMRequirementMatchItem(
                    requirement_name="Python", tier=EvidenceTier.EXPLICIT, confidence=0.9,
                    evidence_ids=[evidence_id], evidence_summary="Directly demonstrated.",
                )
            ]
        ),
    )

    swe_description = (
        "Join our Melbourne engineering team building internal tooling in Python and "
        "SQL, working alongside a small squad of graduate engineers."
    )

    seek_postings = [
        RawJobPosting(
            title="Graduate Software Engineer", company="BuildCo", location="Melbourne VIC",
            source_type=JobSourceType.SEEK, raw_description=swe_description,
            external_id="seek-swe-1",
        ),
        RawJobPosting(
            title="Senior Marketing Manager", company="BrandCo", location="Sydney NSW",
            source_type=JobSourceType.SEEK,
            raw_description=(
                "Lead our marketing team's brand strategy and campaign execution across "
                "Australia, managing a team of coordinators."
            ),
            external_id="seek-marketing-1",
        ),
        RawJobPosting(
            title="Junior Data Analyst", company="DataCo", location="Hobart TAS",
            source_type=JobSourceType.SEEK,
            raw_description=(
                "Support our Hobart analytics team building dashboards and reports in "
                "SQL and Python for internal stakeholders."
            ),
            external_id="seek-data-1",
        ),
    ]
    linkedin_postings = [
        RawJobPosting(
            title="Associate AI Engineer", company="AICo", location="Melbourne, Victoria",
            source_type=JobSourceType.LINKEDIN,
            raw_description=(
                "Build and evaluate machine learning models in Python as part of our "
                "Melbourne AI team, working closely with senior researchers."
            ),
            external_id="li-ai-1",
        ),
        RawJobPosting(
            title="Senior Software Architect", company="ArchCo", location="San Francisco",
            source_type=JobSourceType.LINKEDIN,
            raw_description=(
                "Own the architecture for our core platform, requiring 10+ years of "
                "distributed systems experience, based at our San Francisco HQ."
            ),
            external_id="li-arch-1",
        ),
        RawJobPosting(
            # Same company/title/description as the SEEK posting above -
            # the same real job advertised through two channels.
            title="Graduate Software Engineer", company="BuildCo", location="Melbourne VIC",
            source_type=JobSourceType.LINKEDIN, raw_description=swe_description,
            external_id="li-swe-dup-1",
        ),
    ]

    discovery_service = DiscoveryService(
        llm_provider=fake_provider,
        adzuna_source_factory=lambda config: _FakeSource([]),
        ats_source_factory=lambda entry: _FakeSource([]),
        email_source_factory=lambda db: _FakeSource(seek_postings + linkedin_postings),
    )

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_llm_provider] = lambda: fake_provider
    app.dependency_overrides[get_discovery_service] = lambda: discovery_service
    try:
        client = TestClient(app)

        run_resp = client.post("/api/discovery/run", json={})
        assert run_resp.status_code == 200, run_resp.text
        run = run_resp.json()
        assert run["counts"]["retrieved"] == 6
        assert run["counts"]["duplicates"] == 1
        assert run["counts"]["new"] == 5
        # Marketing Manager (irrelevant + senior) and the San Francisco
        # Architect (overseas, also senior) are both rejected before
        # analysis - one by the relevance filter, one by the Australia gate.
        assert run["counts"]["prefilter_rejected"] == 2
        assert run["counts"]["eligible"] == 3
        assert run["counts"]["analysed"] == 3

        default_feed = client.get("/api/discovery/opportunities").json()
        assert default_feed["total"] == 3
        titles = {item["title"] for item in default_feed["items"]}
        assert titles == {
            "Graduate Software Engineer",
            "Junior Data Analyst",
            "Associate AI Engineer",
        }
        companies = {item["company"] for item in default_feed["items"]}
        assert "BrandCo" not in companies  # Marketing Manager
        assert "ArchCo" not in companies  # San Francisco Architect

        full_feed = client.get("/api/discovery/opportunities?include_rejected=true").json()
        # 5 surviving-dedup postings stored total - the 6th (LinkedIn's
        # duplicate) was merged into the SEEK original, never double-stored.
        assert full_feed["total"] == 5
    finally:
        app.dependency_overrides.clear()
