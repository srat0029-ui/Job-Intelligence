# Job Intelligence

An AI-powered job search command centre: maintain a candidate profile, discover and paste in
jobs, run AI extraction + evidence-based matching, get an explainable fit score, and see a
ranked, prioritised feed of opportunities.

This document covers both the V1 foundation (manual analysis) and Milestone 2 (automated
discovery, deduplication, pre-filtering, cost controls). See
[Incomplete / deferred](#incomplete--deferred) for what's intentionally not built yet.

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
    ingestion/     JobSource (ManualJobSource, AdzunaJobSource) + CandidateDocumentSource
                   (SeedFileCandidateSource, ResumeFileSource) adapters
    services/      Business logic: extraction, matching, scoring, orchestration, discovery,
                   deduplication, pre-filter, priority classification, dashboard
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

- **Automated job sources beyond Adzuna** (Lever, Greenhouse, career pages, email alerts, Seek,
  LinkedIn, GradConnection, Prosple, Indeed) - the `JobSource` interface and discovery pipeline
  are source-agnostic; only `AdzunaJobSource` is implemented. Scraping LinkedIn/Seek is
  explicitly out of scope.
- **Fuzzy/near-duplicate matching** - deduplication is exact/deterministic (external id,
  canonical URL, normalised fields, description hash). Genuinely fuzzy matching (edit distance,
  embeddings) is a real gap for postings reworded between boards, not yet built.
- **Model routing** - the provider abstraction supports per-call model overrides, but there's no
  logic yet choosing a cheaper model for extraction vs. a stronger one for matching.
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
