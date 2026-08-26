# Job Intelligence

An AI-powered job search command centre: maintain a candidate profile, discover and paste in
jobs, run AI extraction + evidence-based matching, get an explainable fit score, and see a
ranked, prioritised feed of opportunities.

This document covers the V1 foundation (manual analysis), Milestone 2 (automated discovery,
deduplication, pre-filtering, cost controls), and Milestone 3 (autonomous discovery: company
watchlists, fuzzy multi-source deduplication, scheduling, analysis prioritisation, source health,
attention/notifications). See [Incomplete / deferred](#incomplete--deferred) for what's
intentionally not built yet.

## Architecture

```
frontend/   Next.js (App Router) + TypeScript + Tailwind - talks to the backend over HTTP only
backend/
  app/
    domain/       Framework-free Pydantic models (Candidate, Job, MatchResult, FitScore,
                   DiscoveredJob, SearchProfile, DiscoveryRun, ApplicationStatusEvent, ...)
    db/           SQLAlchemy ORM models + session + Alembic-managed schema
    repositories/ Data access - translates between ORM rows and domain models
    ai/
      providers/  LLMProvider interface + AnthropicProvider + FakeLLMProvider (tests/dev)
      prompts/    Versioned prompt modules (extraction_v1, matching_v1, cv_extraction_v1)
      schemas/    Typed structured-output contracts for the LLM
    ingestion/     JobSource (ManualJobSource, AdzunaJobSource, LeverJobSource,
                   GreenhouseJobSource) + CandidateDocumentSource (SeedFileCandidateSource,
                   ResumeFileSource) adapters
    services/      Business logic: extraction, matching, scoring, orchestration, discovery,
                   deduplication (exact + fuzzy), pre-filter, analysis-priority scoring,
                   priority classification, source health, attention/notifications, scheduling,
                   dashboard
    api/           Thin FastAPI routers - no business logic lives here
  tests/
    unit/         Pure-logic tests (scoring, matching guardrails, prefilter, dedup, discovery
                  orchestration, adzuna normalisation) - no network; DB tests use real Postgres
    integration/  Full API workflows against a real Postgres + FakeLLMProvider
    evals/        Extraction/matching evaluation framework (see below)
```

**Why this split:** domain models never import SQLAlchemy or FastAPI, so scoring, matching,
pre-filtering, and deduplication logic can be unit-tested as pure functions without spinning up
a database. Repositories are the only layer that touches the ORM. Services hold business logic;
routes only translate HTTP <-> services.

### The anti-hallucination guarantee

The rule that matters most here: **the LLM must never be able to assert experience the
candidate doesn't have on file.** This is enforced in code, not just prompt wording:

1. Matching feeds the model a *fixed list* of candidate `Evidence` records (with IDs) alongside
   each job requirement.
2. The model may only cite `evidence_id`s from that list, classify an evidence tier
   (`explicit` / `transferable` / `weak_inference` / `no_evidence`), and give a confidence score.
3. `MatchingService` strips any `evidence_id` the model returns that wasn't actually in the
   allowed set. If that leaves zero evidence for a claimed non-`no_evidence` tier, the tier is
   force-downgraded to `no_evidence`.
4. `is_gap` is **never** taken from the model - it's derived in code from tier + importance.
5. Final numeric fit scores are computed entirely in `ScoringService` from tiers/importances
   using fixed, named weights - the LLM never outputs a number that ends up in the score.
6. The same discipline applies to CV import (`ResumeFileSource`): evidence provenance
   (`source_type="cv"`) is forced in code after extraction, never trusted from the model, and
   nothing from a CV is written to the stored profile until the user reviews and saves it.

Covered by `tests/unit/test_matching_service.py`, `tests/unit/test_resume_ingestion.py`, and
`tests/evals/test_hallucination_rate.py` (a CI-runnable "hallucination rate" metric using
adversarial fake-model responses).

### AI engineering

- Every LLM call goes through `LLMProvider.generate_structured()`, which returns a *validated*
  Pydantic object plus an `AITrace` (operation type, prompt version, model, latency, token
  usage, estimated cost, status) - persisted to the `ai_traces` table. No hidden
  chain-of-thought is stored, only concise, user-facing output.
- Prompts are versioned modules (`extraction_v1`, `matching_v1`, `cv_extraction_v1`), so an
  `AITrace.prompt_version` can be traced back to exact wording, and a v2 can be evaluated
  side-by-side before replacing v1.
- `AnthropicProvider` sets an explicit request timeout (`LLM_TIMEOUT_SECONDS`), retries
  validation/provider failures up to `LLM_MAX_RETRIES` with bounded exponential backoff (capped,
  longer for rate-limit errors specifically), and logs one `AITrace` per attempt - never an
  unbounded retry loop.
- `app/ai/providers/factory.py` picks the provider: real `AnthropicProvider` if
  `ANTHROPIC_API_KEY` is set, otherwise a `FakeLLMProvider` (with a loud warning) so the app is
  still explorable without a key.
- `scripts/smoke_test_llm.py` makes exactly **one** real structured-generation call to confirm
  the configured provider/model/key actually work, without running discovery or analysing real
  jobs. Run it deliberately after changing `ANTHROPIC_API_KEY`/`ANTHROPIC_MODEL` - nothing in
  this codebase runs it automatically just because a key is present.

### Evaluation framework

- `tests/evals/fixtures/*.json` - job description fixtures with expected required/preferred
  skills and role-category keywords.
- `tests/evals/eval_extraction.py` - a script (not a pytest test - costs real tokens) that runs
  the *real* extractor against fixtures and reports required/preferred-skill recall. Run with
  `python -m tests.evals.eval_extraction` from `backend/` once `ANTHROPIC_API_KEY` is set.
- `tests/evals/test_hallucination_rate.py` - a CI-runnable pytest eval that drives
  `MatchingService` with adversarial fake responses and asserts the hallucination rate is
  exactly zero.
- `tests/unit/test_scoring_service.py::test_score_is_deterministic_across_runs` - a basic score
  stability check (same inputs -> byte-identical score, every time).

## Milestone 2: automated discovery

### Pipeline

```
JobSource.fetch()  (Adzuna today; Lever/Greenhouse/etc. later)
   -> normalisation into RawJobPosting (canonical, source-agnostic fields)
   -> deduplication (deterministic - external id, canonical URL, company+title+location,
                      description fingerprint)
   -> deterministic pre-filter (title/seniority, years-experience ceiling, location,
                                  work rights, excluded keywords - all before any LLM call)
   -> [only for postings that survive both]: promote to a `Job` row and run the EXISTING,
      unmodified extraction -> matching -> scoring pipeline via AnalysisOrchestrator
   -> priority classification (deterministic, score-only bucket) + "why this job" summary
      (built entirely from stored analysis fields)
```

`DiscoveryService` (`app/services/discovery_service.py`) is a coordinator, not a second analysis
system - once a posting survives dedup + pre-filter, it's handed to the same
`AnalysisOrchestrator` the manual "paste a job" flow uses. Nothing about *how* a job gets
analysed changes; only *whether it's worth analysing at all* does.

### Why deterministic filtering happens before any LLM call

Every discovered posting costs nothing to fetch but real money to analyse (each analysis is 2
LLM calls - extraction + matching). Two purely-Python passes - deduplication then pre-filter -
reject the postings that are cheap to identify as unsuitable (a repost, an explicitly senior
role when you want graduate roles, a role needing sponsorship you don't have) using plain
string/regex matching against stored preferences, with zero API cost. Only what survives both
reaches the LLM. This is also more auditable: `PREFILTER_REJECTED` postings carry a concrete,
human-readable `prefilter_reason` string (e.g. *"Title contains 'senior', which exceeds the
configured max experience level (graduate)"*), not an LLM's opaque judgement call.

Rules are deliberately conservative (see `app/services/prefilter_service.py`) - a posting is
only rejected on a strong, explicit signal (a real "8+ years" phrase, a title literally
containing "Senior"/"Principal"/etc.), specifically to avoid discarding a good stretch role.

### JobSource adapter architecture

`JobSource` (`app/ingestion/job_source.py`) is the interface every source implements;
`RawJobPosting` is the canonical shape every source normalises into (title, company,
description, plus optional richer fields - salary, dates, employment type, remote type,
external id, and a free-form `source_metadata` bag for anything vendor-specific). Nothing
Adzuna-specific ever leaks into core domain code - vendor detail lives only in
`source_metadata`.

- `ManualJobSource` - the user pastes a description (V1's only source).
- `AdzunaJobSource` (`app/ingestion/adzuna_source.py`) - calls the real Adzuna Australia API.
  One HTTP request per (location, page), using Adzuna's `what_or` parameter to OR-match every
  configured keyword in a *single* query rather than one request per keyword variant - a search
  profile with 8 keyword variants and 3 locations is 3 requests per page, not 24. Handles HTTP
  errors, rate limits (429), malformed JSON, and missing fields per-request without ever raising
  out of `fetch()` - one bad page/location stops paging just that location, never the whole run.

Adding Lever, Greenhouse, a company career page, or an email-alert parser later means one new
file implementing `JobSource` and one line in `DiscoveryService`'s source-builder list - nothing
else changes. Scraping LinkedIn/Seek is explicitly out of scope (terms of service).

### Deduplication strategy

`app/services/deduplication_service.py` - purely deterministic, checked in order of
reliability, no LLM involved at any point:

1. Same source + same `external_id`.
2. Same canonical URL (query string/fragment/trailing slash stripped).
3. Same normalised (company, title, location) triple.
4. Same description fingerprint (SHA-256 of normalised description text) - catches a repost
   under a different title/URL.

A duplicate updates `first_seen_at`/`last_seen_at`/`times_seen` on the existing
`DiscoveredJob` row rather than being discarded, so the system knows a posting keeps
reappearing without losing that signal. Fuzzy/near-duplicate matching (edit distance,
embeddings) is a deliberately unbuilt extension point, not a gap papered over - exact
deterministic checks are enough at this project's current source count.

### Cost controls

- `AppSettings` (a live, DB-backed singleton row, editable from **Settings**, not an env var
  requiring a restart): `auto_ai_analysis_enabled`, `max_ai_analyses_per_run`,
  `daily_ai_analysis_budget_usd`.
- During the automated phase of a discovery run, `DiscoveryService` analyses eligible jobs up to
  the per-run cap and stops once today's actual spend (summed from real `AITrace` cost records)
  would meet or exceed the daily budget. Jobs past either limit are left `awaiting_analysis`
  ("deferred due to run limit"), never silently dropped.
- `POST /api/discovery/discovered-jobs/{id}/analyze` force-analyses one specific job regardless
  of these limits - the explicit manual override the brief asked for.
- **Settings** also shows spend-today and all-time spend (summed from `ai_traces`), and the
  scoring weights (unrelated to cost, kept there since it's the other "how does this system
  make decisions" reference panel).
- Model routing (a cheap model for extraction, a stronger one for harder matching) is
  deliberately not built yet - the provider abstraction supports it (swap `model=` per call),
  but there's no evidence yet that the current model needs help on either step.

### Configuring Adzuna

1. Register at https://developer.adzuna.com and get an `app_id`/`app_key` for the Australian
   jobs API.
2. Set `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` in `backend/.env` (and the root `.env` for Docker
   Compose). `ADZUNA_COUNTRY` defaults to `au`.
3. Without these set, `DiscoveryService` logs a warning and skips Adzuna for every search
   profile - a discovery run still completes successfully, just with zero results, rather than
   erroring. `tests/unit/test_adzuna_source.py` covers the adapter entirely with
   `httpx.MockTransport` fixtures, so its correctness isn't dependent on having real credentials.

### Running discovery manually

From the UI: the **Discover** page has a "Run discovery" button, plus a search-profile manager
(add/edit/enable/disable/delete) since search profiles are stored in the database, not
hard-coded.

From the command line (same `DiscoveryService`, same result - there is exactly one discovery
implementation):

```bash
cd backend
python scripts/run_discovery.py                    # every enabled search profile
python scripts/run_discovery.py <profile-uuid> ...  # only these profiles
```

Reports retrieved/new/duplicate/pre-filter-rejected/eligible/analysed/deferred/failed counts,
Strong-Apply-or-better count, and estimated AI cost for the run - the same shape stored in the
`discovery_runs` audit table and returned by `GET /api/discovery/runs`.

### How outcomes will eventually calibrate scoring

`Job.application_status` (`interested` -> `applying` -> `applied` -> `interview` -> `offer` /
`rejected` / `withdrawn` / `ignored`) plus its full history in `application_status_events` exists
purely to eventually answer "which kinds of jobs I score highly actually turn into interviews?".
No automatic applications are ever submitted - this is a manual tracker only. Once enough
outcome data exists, a future milestone can compare `FitScore` component values against
`interview`/`offer` outcomes to recalibrate the fixed weights in `ScoringService` - the schema
is shaped for that today, but no calibration logic exists yet (there isn't enough outcome data
to calibrate against).

## Milestone 3: autonomous discovery

Turns the manual-trigger discovery of Milestone 2 into something that runs itself: it watches
specific employers directly (not just broad job-board search), catches the same job posted
across multiple sources without ever merging two genuinely different roles, prioritises its own
limited AI budget toward the postings actually worth spending it on, runs on a schedule without
needing a human to remember, and surfaces its own health/failures instead of failing silently.

### 1. Broad discovery vs. direct-employer discovery

Two structurally different ways of finding jobs, both feeding the same pipeline downstream:

- **Broad discovery** (`AdzunaJobSource`, unchanged from M2) - a keyword/location search across
  an aggregator. High recall, but everything is filtered through someone else's index, and
  postings can be stale, re-posted by recruiters, or missing entirely if the aggregator hasn't
  indexed a company yet.
- **Direct-employer discovery** (new: `LeverJobSource`, `GreenhouseJobSource`) - reads a specific
  company's own public postings feed. Higher precision (it's the employer's own listing) and
  often fresher, but only covers companies you've explicitly told the system to watch.

Both run in the same `DiscoveryService.run()` call and feed the same dedup -> pre-filter ->
analysis pipeline; a job found by either path becomes an identical `DiscoveredJob` row. Source
type only ever affects *provenance and canonical-field promotion* (see topic 3) - never fit
score.

### 2. Why Lever/Greenhouse are company-scoped, not global search

Lever and Greenhouse's public APIs (`api.lever.co/v0/postings/{site}`,
`boards-api.greenhouse.io/v1/boards/{token}`) are **per-tenant** - there is no "search all
companies on Lever" endpoint, unlike Adzuna's aggregated index. So `CompanyWatchlist`
(`app/domain/company_watchlist.py`) exists as the thing a user explicitly curates: one row per
company, holding which ATS it uses and that ATS's identifier for this company
(`ats_type` + `ats_identifier`), a priority, preferred locations, and enabled/disabled.
`DiscoveryService._discover_via_watchlist_entry()` builds one `JobSource` per *enabled* watchlist
entry via `_build_ats_source()`, which is the **only** place that switches on `ATSType` - the
orchestrator itself stays entirely source-agnostic. Adding a third ATS is one new
`JobSource` implementation plus one `if` branch there; nothing about `DiscoveryService.run()`,
dedup, pre-filter, or the UI changes.

### 3. Deduplication: exact/deterministic, then fuzzy - never an LLM

`app/services/deduplication_service.py` runs in three stages, in order of confidence, and stops
at the first match:

1. **Exact ID/URL** - same source + `external_id`, or the same canonical URL (query
   string/fragment/trailing slash stripped) - checked first against every prior
   `SourceObservation` (not just the canonical row), so a job already seen via Adzuna is
   recognised the instant the *same* URL/ID shows up again via a company's own Lever feed.
2. **Deterministic fingerprint** - SHA-256 of normalised `(company, title, location)`, and
   separately of normalised description text - catches the same role reposted with a different
   URL/ID but byte-identical (post-normalisation) content.
3. **Fuzzy** (new) - word-token Jaccard similarity (`_word_tokens` + `_jaccard`) across title
   *and* description, gated hard by exact company match and a
   `FUZZY_CANDIDATE_DATE_WINDOW_DAYS = 21` posting-date window, so comparison is always bounded
   to a small, plausible candidate set - **never O(n²) over the whole table.** A weighted score
   (`TITLE_SIMILARITY_WEIGHT=0.15`, `DESCRIPTION_SIMILARITY_WEIGHT=0.70`,
   `DATE_PROXIMITY_WEIGHT=0.15`) must clear `AUTO_MERGE_THRESHOLD=0.60`, **and** title similarity
   alone must clear `MIN_TITLE_TOKEN_SIMILARITY=0.15` - a hard floor specifically so two
   different roles at the same company (e.g. "Data Analyst" vs. "Marketing Coordinator") can
   never merge purely on a similar-sounding description. Every fuzzy match records its stage,
   confidence, and a human-readable reason on the new `match_stage`/`match_confidence`/
   `match_reason` fields of `SourceObservation`, so a merge decision is always auditable, never a
   black box.

An LLM is never involved in any of this. Two reasons: (1) an LLM's judgement of "same job?" is
neither deterministic nor auditable at the confidence level a merge decision needs, and (2)
calling one per candidate-pair comparison would be both slow and another real-money cost for a
purely structural decision that string similarity answers reliably. The three stages are
calibrated (see `deduplication_service.py`'s module docstring and
`tests/unit/test_fuzzy_deduplication.py`) to prefer a **false negative** (two observations of the
same job stay as separate `DiscoveredJob` rows) over a **false positive** (two different roles
silently merged) - a missed merge just means the same job shows up twice in the feed; a wrongful
merge would hide a real, different opportunity and corrupt the audit trail permanently.

Nothing is ever discarded on a match: the existing canonical `DiscoveredJob` gets a new
`SourceObservation` row (source, external_id, URL, match stage/confidence/reason, first/last
seen, times seen) rather than being duplicated or overwritten - see
`tests/integration/test_discovery_pipeline.py::test_multi_source_dedup_and_shortlist` for the
full "same job via Adzuna and Lever, plus one genuinely different Lever job" scenario end to end.

### 4. Source quality and canonical-field promotion

`SOURCE_QUALITY_RANK` (`deduplication_service.py`) ranks `manual < adzuna < lever == greenhouse`
- a direct-employer feed outranks an aggregator. When a new observation of an already-known job
comes from a higher-ranked source, `maybe_promote_canonical_fields()` updates the canonical
row's *presentation* fields only (title text, company text, URL) to the higher-quality source's
version - e.g. preferring the employer's own posting URL over an aggregator's redirect link.
This **never** touches `analysis_priority`, `latest_overall_score`, `latest_recommendation`, or
anything scoring-related - source quality is strictly a display/provenance concern, enforced by
which fields `maybe_promote_canonical_fields()` is allowed to write.

### 5. Analysis priority vs. fit score - two scores, never conflated

- **`analysis_priority`** (`app/services/analysis_priority_service.py`) - deterministic,
  computed **before** any LLM call, from free signals only: early-career title keywords (boost),
  senior title keywords / explicit high years-of-experience phrases (penalty), posting recency,
  location-priority match (from `SearchProfile.location_priority`), direct-employer source
  (small boost over aggregator), and **`CompanyWatchlistEntry.priority`** (High/Normal/Low -
  boosts or penalises). Clamped 0-100. Its only job is to decide *analysis order* when the AI
  budget for a run can't cover every eligible posting.
- **Fit score / `Recommendation` / `JobPriority`** - unchanged from M1/M2: entirely post-LLM,
  evidence-grounded, computed by the existing `ScoringService` from fixed named weights. Company
  watchlist priority, source type, and posting recency have **zero** influence on this number.

The domain models keep the two fields physically separate (`DiscoveredJob.analysis_priority` vs.
`latest_overall_score`/`latest_recommendation`/`latest_priority`) and the UI labels them
distinctly (Companies page: *"Priority here boosts analysis order only - it never changes the
candidate fit score"*) specifically so this distinction can't quietly blur over time.

### 6. Scheduling: in-process `BackgroundScheduler`, not a worker queue or bare cron

`app/scheduler.py` runs an APScheduler `BackgroundScheduler` inside the same FastAPI process,
wired into `main.py`'s lifespan (`start_scheduler()`/`stop_scheduler()`), ticking every
`CHECK_INTERVAL_MINUTES = 15` to ask "is a run due yet?" (`AppSettings.next_scheduled_run_at`),
rather than scheduling discovery directly at its configured frequency.

**Why this over the alternatives, at this project's actual scale (a single-user tool running a
few times a day):**

| Approach | Trade-off |
|---|---|
| **In-process `BackgroundScheduler`** (chosen) | Zero extra infrastructure; "next run" / enable-disable are just DB fields the API already exposes. Scheduling state lives only in this process's memory - a restart re-derives "is it due" from Postgres, so nothing is lost, but it isn't a real distributed lock: two instances of this process would each independently decide "it's due" (limited by `DiscoveryService.run()` refusing a second concurrent run - see topic 7 - to "ran twice," not corruption). |
| Dedicated worker (Celery/RQ + Redis) | Real infrastructure (a broker, a second deployable, ops surface) that buys retry/backoff semantics and multi-instance safety this project doesn't need yet. |
| Bare OS cron + `scripts/run_discovery.py` | No extra infrastructure, and still fully supported (the documented upgrade path) - but needs OS-level configuration outside the app, and can't expose "next scheduled run"/toggle through the API the way the in-process scheduler does. |

The tick itself (`run_scheduled_discovery_if_due()`) is a small, independently testable function
(not a bare lambda inside `add_job`) specifically so `tests/unit/test_scheduler.py` can call it
directly - due/not-due, enabled/disabled, and the already-running case - without spinning up a
real scheduler thread.

### 7. Failure isolation and automation safety

Every layer that could fail during an unattended run is isolated so one bad source, job, or
budget overrun degrades gracefully rather than aborting the whole run:

- **Overlap prevention** - `DiscoveryService.run()` checks
  `DiscoveryRunRepository.get_running()` first and raises `DiscoveryAlreadyRunningError` rather
  than starting a second concurrent run; the scheduler tick catches this and just logs a skip.
- **Per-source failure isolation** - `fetch_with_health_tracking()`
  (`app/services/source_health_service.py`) wraps every source's `fetch()` call, catching any
  exception, recording it against that source's `SourceHealth` row, and returning an empty list
  rather than raising - one source being down (a bad Lever slug, a network blip) never stops
  discovery from running the rest.
- **Per-job failure isolation** - a single posting's normalisation/analysis exception is caught,
  counted in `DiscoveryRunCounts.failed`, and an `AttentionItem` is raised once failures cross
  `ANALYSIS_FAILURE_ATTENTION_THRESHOLD`; the run continues processing the remaining postings.
- **Bounded fetch/AI caps** - `max_postings_per_source_per_run` bounds how much any one source
  can flood a single run; `max_ai_analyses_per_run` and `daily_ai_analysis_budget_usd` bound
  spend (see topic 8) - jobs past either limit are marked `awaiting_analysis` ("deferred"), never
  silently dropped or force-failed. Verified live: a real run against Palantir's public Lever
  feed with the cap set to 1 retrieved 100 postings, found 63 new, analysed exactly 1, and
  correctly deferred the other 62 rather than erroring (see the Milestone 3 verification section
  below).
- **Instant scheduler disable** - `AppSettings.auto_discovery_enabled` is checked first thing in
  every tick; flipping it off in Settings takes effect on the very next 15-minute check, no
  restart needed.

### 8. Cost controls (extended from M2)

Unchanged from M2 (`auto_ai_analysis_enabled`, `max_ai_analyses_per_run`,
`daily_ai_analysis_budget_usd`) plus, new in M3: `max_postings_per_source_per_run` (caps fetch
volume per source, independent of AI spend) and the scheduling fields
(`auto_discovery_enabled`, `discovery_frequency_hours`). All are one live `AppSettings` row,
editable from **Settings** with no restart required. `DiscoveryRunCounts` now also tracks
`ai_calls`/`ai_input_tokens`/`ai_output_tokens` per run (visible on the Discovery Run detail
page) alongside the existing `estimated_cost_usd`, so a budget-constrained run's actual spend is
fully auditable after the fact, not just capped in advance.

### 9. Source health monitoring

`SourceHealth` (`app/domain/source_health.py`, one row per `source_key` - `"adzuna"` or
`"lever:<slug>"`/`"greenhouse:<slug>"` per watchlisted company) tracks status
(`healthy`/`degraded`/`error`/`unknown`), last attempt/success timestamps, consecutive failures,
a coarse `last_error_category` (the exception's class name, e.g. `ConnectionError` -
**never** a raw stack trace or exception message, so nothing sensitive or overly implementation-
specific leaks into the UI), jobs retrieved last run, and average latency.
`fetch_with_health_tracking()` is the single place every source's health is updated, shared by
Adzuna and every watchlist entry, so there's one source of truth rather than parallel bookkeeping
per source type. Surfaced on the Dashboard (compact badges) and the Companies page (inline per
watchlist entry, matched by `CompanyWatchlistEntry.source_key`).

### 10. Avoiding reprocessing without permanently losing jobs on transient failure

Two independent mechanisms, deliberately not one:

- **Deduplication is the primary watermark.** Because dedup checks `SourceObservation` rows
  first (stage 1: exact ID/URL against *every* prior observation, not just the canonical row), a
  posting seen in a previous run is recognised as a duplicate on every later run - there's no
  separate "last processed timestamp" cursor to fall behind or corrupt. If a fetch fails
  entirely (see topic 7), nothing was marked as seen, so those postings are naturally retried
  the next run rather than being permanently skipped - the "watermark" is just "have I already
  created an observation for this ID/URL/fingerprint," which self-corrects after any transient
  failure with no separate recovery logic needed.
- **`analysis_priority` + budget caps decide what's worth analysing when there's a backlog** -
  a burst of new postings after a source outage doesn't get silently dropped; everything above
  the pre-filter is created as a `DiscoveredJob` and analysed in priority order across as many
  runs as it takes to clear the `awaiting_analysis` backlog.

### Milestone 3 verification (real, not mocked)

Live Adzuna credentials were not available in this environment (`ADZUNA_APP_ID`/`ADZUNA_APP_KEY`
are unset in `backend/.env` - only `ADZUNA_COUNTRY` is set), so Adzuna validation is deferred, as
in Milestone 2. A real `ANTHROPIC_API_KEY` **was** configured, so the Lever integration and the
whole autonomous-discovery pipeline were verified against **live, real data** instead: a
temporary `CompanyWatchlist` entry against Palantir's real public Lever board
(`api.lever.co/v0/postings/palantir`), with `max_ai_analyses_per_run` deliberately capped to `1`
for the duration of the test (restored to its normal value afterward) to keep it a controlled,
bounded-cost test rather than a bulk analysis run. Result: 100 postings retrieved (capped by
`max_postings_per_source_per_run`), 63 recognised as new, 37 correctly recognised as duplicates
(Palantir posts near-identical roles across many regional variants), 1 analysed with a real,
evidence-grounded fit score and gap, the other 62 correctly deferred by the AI cap rather than
failing the run, and accurate token/cost accounting (`$0.0672` for 2 real LLM calls). The test
watchlist entry was left in the database **disabled** (not deleted) with an explanatory note, so
the real discovery-run audit trail this produced stays intact without the entry causing future
runs to keep pulling Palantir jobs.

## Running locally

### Option A: Docker Compose (everything)

```bash
cp .env.example .env
docker compose up --build
```

Backend: http://localhost:8000/docs · Frontend: http://localhost:3000

Then seed the candidate profile once, and apply migrations if not already applied by the
container's start command:

```bash
docker compose exec backend python scripts/seed.py
```

### Option B: run backend and frontend directly

```bash
# Postgres (pgvector) only, via Docker
docker compose up -d db

# Backend
cd backend
python -m venv .venv && .venv/Scripts/activate  # or source .venv/bin/activate on macOS/Linux
pip install -e ".[dev]"
cp ../.env.example .env   # edit DATABASE_URL to localhost if needed
alembic upgrade head
python scripts/seed.py
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Visit http://localhost:3000 - you'll land on the Dashboard.

**If you also run via Docker Compose at some point**: the `backend` container binds host port
8000, same as a locally-run `uvicorn`. Only run one at a time, or you'll be confused about which
one is actually answering your requests (ask me how I know).

## Environment variables

See [.env.example](.env.example). The important ones:

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | Postgres connection string (psycopg3 driver) |
| `ANTHROPIC_API_KEY` | for real AI features | Server-side only, never sent to the browser. Without it, extraction/matching/CV-parsing fall back to a fake provider and error when actually invoked. |
| `ANTHROPIC_MODEL` | no | Defaults to `claude-sonnet-5` |
| `LLM_TIMEOUT_SECONDS` | no | Per-attempt request timeout, defaults to 60 |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | for discovery | Without these, discovery runs complete with zero Adzuna results rather than erroring |
| `ADZUNA_COUNTRY` | no | Defaults to `au` |
| `NEXT_PUBLIC_API_BASE_URL` | yes (frontend) | Where the Next.js app reaches the FastAPI backend |

## Tests & checks

```bash
# Backend (from backend/, with a running Postgres - docker compose up -d db)
ruff check .
mypy app
pytest -q

# Frontend
npm run lint
npm run test
npm run build
```

## Incomplete / deferred

Labelled explicitly rather than hidden behind working-looking UI:

- **Automated job sources beyond Adzuna/Lever/Greenhouse** (career pages without a Lever/
  Greenhouse-style public API, email alerts, Seek, LinkedIn, GradConnection, Prosple, Indeed) -
  the `JobSource` interface and discovery pipeline are source-agnostic; adding one is one new
  adapter file. Scraping LinkedIn/Seek is explicitly out of scope (terms of service).
- **Live Adzuna validation** - no real `ADZUNA_APP_ID`/`ADZUNA_APP_KEY` were available in this
  environment; the adapter is fully unit-tested against mocked responses
  (`tests/unit/test_adzuna_source.py`) and a discovery run completes successfully with zero
  Adzuna results when unconfigured, but it hasn't been exercised against the real Adzuna API.
- **Model routing** - the provider abstraction supports per-call model overrides, but there's no
  logic yet choosing a cheaper model for extraction vs. a stronger one for matching.
- **External notifications (email/push)** - `AttentionItem` is a fully-built internal
  read/unread notification system (high-priority jobs, watchlisted-company postings, analysis
  failures, unhealthy sources), deliberately channel-agnostic in its design, but no email/push
  delivery channel is wired up yet - notifications are only visible in-app.
- **True distributed scheduling** - the scheduler is a single in-process `BackgroundScheduler`
  (see Milestone 3, topic 6); running more than one instance of the backend would mean each
  independently decides "a run is due," limited to "ran twice" (not corruption) by
  `DiscoveryService.run()`'s overlap check, not a real distributed lock. Documented as the
  accepted trade-off at this project's current (single-user, single-instance) scale.
- **Outcome-based score calibration** - the schema (`application_status_events`) exists to
  support it, but no calibration logic exists yet; there isn't enough outcome data to calibrate
  against.
- **Tailored application material generation, interview prep** - out of scope for this
  milestone.
- **pgvector-based retrieval** - the `evidence.embedding` column and extension exist, but
  matching uses direct skill-tag/requirement-name comparison since the candidate's evidence set
  is small; semantic retrieval is reserved for when that stops being true.
- **CV import is category-granular, not item-granular** - `POST /api/candidate/cv/parse`
  returns a full proposal, and the Profile page lets you add each *category* (education, work
  history, projects, ...) found in the CV to your draft profile before saving; it doesn't yet
  offer per-item checkboxes within a category. Remove-after-adding (already supported by every
  editor) covers the same need today with one extra click.
