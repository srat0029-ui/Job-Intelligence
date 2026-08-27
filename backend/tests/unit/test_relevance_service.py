"""Unit tests for the email-alert-only relevance/role-family gate (Parts 7,
8, 10 of the simplification brief) - no LLM, no DB. Mirrors
test_prefilter_service.py's style."""

from __future__ import annotations

from app.domain.candidate import Candidate, CandidatePreferences
from app.domain.enums import JobSourceType
from app.ingestion.job_source import RawJobPosting
from app.services.relevance_service import evaluate_relevance


def _posting(title: str, description: str = "") -> RawJobPosting:
    return RawJobPosting(
        title=title,
        company="Acme",
        location="Melbourne, VIC",
        source_type=JobSourceType.SEEK,
        raw_description=description or title,
    )


def _candidate(**prefs) -> Candidate:
    return Candidate(name="Test Candidate", preferences=CandidatePreferences(**prefs))


def test_graduate_software_engineer_passes():
    result = evaluate_relevance(_posting("Graduate Software Engineer"), _candidate())
    assert result.passed
    assert result.matched_family == "Software Engineering"


def test_plain_software_engineer_title_passes_without_graduate_wording():
    """Part 8: don't reject just because the title lacks the literal word
    "graduate"/"junior" - a plain title can still be early-career."""
    result = evaluate_relevance(_posting("Software Engineer"), _candidate())
    assert result.passed


def test_plain_data_analyst_title_passes():
    result = evaluate_relevance(_posting("Data Analyst"), _candidate())
    assert result.passed
    assert result.matched_family == "Data Analytics"


def test_senior_title_is_rejected():
    result = evaluate_relevance(_posting("Senior Software Engineer"), _candidate())
    assert not result.passed
    assert "senior" in (result.reason or "").lower()


def test_manager_title_is_rejected():
    result = evaluate_relevance(_posting("Engineering Manager"), _candidate())
    assert not result.passed


def test_lead_title_is_rejected():
    result = evaluate_relevance(_posting("Lead Data Engineer"), _candidate())
    assert not result.passed


def test_years_of_experience_requirement_is_rejected():
    result = evaluate_relevance(
        _posting("Software Engineer", "Requires 8+ years of experience in distributed systems."),
        _candidate(),
    )
    assert not result.passed


def test_bare_architect_title_without_experience_signal_is_not_rejected():
    """Part 8: "architect roles requiring substantial experience" - not
    architect roles as such."""
    result = evaluate_relevance(
        _posting("Solutions Architect Graduate Program", "Great starting role for graduates."),
        _candidate(),
    )
    assert result.passed


def test_architect_title_with_years_signal_is_rejected():
    result = evaluate_relevance(
        _posting(
            "Solutions Architect",
            "Requires 10+ years of enterprise architecture experience.",
        ),
        _candidate(),
    )
    assert not result.passed


def test_sales_role_is_rejected():
    result = evaluate_relevance(_posting("Sales Development Representative"), _candidate())
    assert not result.passed


def test_marketing_role_is_rejected():
    result = evaluate_relevance(_posting("Marketing Coordinator"), _candidate())
    assert not result.passed


def test_mechanical_engineer_is_rejected():
    result = evaluate_relevance(_posting("Graduate Mechanical Engineer"), _candidate())
    assert not result.passed


def test_healthcare_role_is_rejected():
    result = evaluate_relevance(_posting("Graduate Registered Nurse"), _candidate())
    assert not result.passed


def test_adjacent_role_with_incidental_marketing_mention_is_generously_kept():
    """Part 10: "be generous with genuine adjacent technology roles" - a
    data role mentioning "marketing" only in passing (e.g. the team name)
    must not be rejected just for that word."""
    result = evaluate_relevance(
        _posting("Data Analyst - Marketing Team", "Analyse campaign data for the marketing team."),
        _candidate(),
    )
    assert result.passed
    assert result.matched_family == "Data Analytics"


def test_cyber_security_family_matches():
    result = evaluate_relevance(_posting("Graduate Cyber Security Analyst"), _candidate())
    assert result.passed
    assert result.matched_family == "Cyber Security"


def test_cloud_family_matches():
    result = evaluate_relevance(_posting("Graduate Cloud Engineer"), _candidate())
    assert result.passed
    assert result.matched_family == "Cloud / Systems"


def test_unrelated_retail_role_with_no_family_or_technology_match_is_rejected():
    result = evaluate_relevance(_posting("Retail Store Assistant"), _candidate())
    assert not result.passed


def test_preferred_technology_mention_alone_is_enough_to_pass():
    result = evaluate_relevance(
        _posting("Graduate Program", "You'll be working with Python and FastAPI daily."),
        _candidate(preferred_technologies=["Python", "FastAPI"]),
    )
    assert result.passed


# --- broadened role-family phrasing (Part 1 of the recommendation-quality review) ---


def test_forward_deployed_ai_scientist_title_matches_ai_family():
    """A role shouldn't need the exact word "Engineer" to match AI - real
    postings use "Scientist"/"Applied Scientist"/"Forward Deployed" for the
    same underlying work."""
    result = evaluate_relevance(
        _posting("Forward Deployed AI Scientist - Consulting (Graduate)"), _candidate()
    )
    assert result.passed
    assert result.matched_family == "AI / Machine Learning"


def test_quant_analyst_title_matches_quant_family():
    result = evaluate_relevance(
        _posting("Junior Software Engineer/Quantitative Developer/Quantitative Analyst"),
        _candidate(),
    )
    assert result.passed


# --- generic graduate-program fallback ---


def test_generic_graduate_technology_program_passes_via_fallback():
    """Part 1: a broad graduate-program title with no specific role-family
    phrase should still pass when it names a technical stream."""
    result = evaluate_relevance(
        _posting("Graduate Analyst - Technology - 2027 Graduate Program"), _candidate()
    )
    assert result.passed
    assert result.matched_family == "Technology Graduate Program"


def test_generic_graduate_program_with_no_technical_stream_signal_is_rejected():
    """Part 1: "do not let unrelated graduate roles through solely because
    they say 'graduate'" - a bare graduate-campaign title with no technical
    stream signal anywhere must not pass on the word "graduate" alone."""
    result = evaluate_relevance(_posting("2027 Graduate Campaign"), _candidate())
    assert not result.passed


def test_graduate_program_fallback_does_not_override_an_irrelevant_title():
    """A graduate marketing program still has an early-career indicator and
    might incidentally mention "digital" (e.g. "digital marketing"), but an
    explicitly irrelevant title must still be rejected."""
    result = evaluate_relevance(
        _posting("Graduate Marketing Coordinator", "Join our digital marketing team."),
        _candidate(),
    )
    assert not result.passed
