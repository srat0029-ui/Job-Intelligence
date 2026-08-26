# Job Intelligence

An AI-powered job search command centre: maintain a candidate profile, paste in job
descriptions, run AI extraction + evidence-based matching, and get an explainable fit score
and recommendation.

This is a **V1 foundation** - see [Incomplete / deferred](#incomplete--deferred) for what's
intentionally not built yet.

## Architecture

```
frontend/   Next.js (App Router) + TypeScript + Tailwind - talks to the backend over HTTP only
backend/
  app/
    domain/       Framework-free Pydantic models (Candidate, Job, MatchResult, FitScore, ...)
    db/           SQLAlchemy ORM models + session + Alembic-managed schema
    repositories/ Data access - translates between ORM rows and domain models
    ai/
      providers/  LLMProvider interface + AnthropicProvider + FakeLLMProvider (tests/dev)
      prompts/    Versioned prompt modules (extraction_v1, matching_v1)
      schemas/    Typed structured-output contracts for the LLM
    ingestion/    JobSource + CandidateDocumentSource interfaces (adapters live here later)
    services/     Business logic: extraction, matching, scoring, orchestration, dashboard
    api/          Thin FastAPI routers - no business logic lives here
  tests/
    unit/         Pure-logic tests (scoring, matching guardrails) - no DB, no network
    integration/  Full API workflow against a real Postgres + FakeLLMProvider
    evals/        Extraction/matching evaluation framework (see below)
```

**Why this split:** domain models never import SQLAlchemy or FastAPI, so the scoring and
matching logic can be unit-tested as pure functions and reused by the eval framework without
spinning up a database. Repositories are the only layer that touches the ORM. Services hold
business logic; routes only translate HTTP <-> services.

### The anti-hallucination guarantee

The spec that matters most here: **the LLM must never be able to assert experience the
candidate doesn't have on file.** This is enforced in code, not just prompt wording:

1. Matching feeds the model a *fixed list* of candidate `Evidence` records (with IDs) alongside
   each job requirement.
2. The model may only cite `evidence_id`s from that list, classify an evidence tier
   (`explicit` / `transferable` / `weak_inference` / `no_evidence`), and give a confidence score.
3. `MatchingService` (see `app/services/matching_service.py`) strips any `evidence_id` the model
   returns that wasn't actually in the allowed set. If that leaves zero evidence for a claimed
   non-`no_evidence` tier, the tier is force-downgraded to `no_evidence`.
4. `is_gap` is **never** taken from the model - it's derived in code from tier + importance.
5. Final numeric fit scores are computed entirely in `ScoringService` from tiers/importances
   using fixed, named weights - the LLM never outputs a number that ends up in the score.

This is covered by `tests/unit/test_matching_service.py` and
`tests/evals/test_hallucination_rate.py` (a CI-runnable "hallucination rate" metric using
adversarial fake-model responses).

### AI engineering

- Every LLM call goes through `LLMProvider.generate_structured()`, which returns a *validated*
  Pydantic object plus an `AITrace` (operation type, prompt version, model, latency, token
  usage, estimated cost, status) - persisted to the `ai_traces` table. No hidden
  chain-of-thought is stored, only concise, user-facing output.
- Prompts are versioned modules (`app/ai/prompts/extraction_v1.py`, `matching_v1.py`), so an
  `AITrace.prompt_version` can be traced back to exact wording, and a v2 can be evaluated
  side-by-side before replacing v1.
- Retries on validation/provider failures are handled inside `AnthropicProvider`, up to
  `LLM_MAX_RETRIES`, with one `AITrace` logged per attempt.
- `app/ai/providers/factory.py` picks the provider: real `AnthropicProvider` if
  `ANTHROPIC_API_KEY` is set, otherwise a `FakeLLMProvider` (with a loud warning) so the app is
  still explorable without a key.

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

## Environment variables

See [.env.example](.env.example). The important ones:

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | Postgres connection string (psycopg3 driver) |
| `ANTHROPIC_API_KEY` | for real AI features | Server-side only, never sent to the browser. Without it, extraction/matching falls back to a fake provider and will error when you try to analyse a job. |
| `ANTHROPIC_MODEL` | no | Defaults to `claude-sonnet-5-20250929` |
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

- **CV upload/parsing** - the `CandidateDocumentSource` interface and seed mechanism exist
  (`app/ingestion/candidate_document_source.py`), but only `SeedFileCandidateSource` (structured
  JSON) is implemented. A `ResumeFileSource` that parses an uploaded PDF/DOCX via an LLM
  extraction step is the natural next implementation of the same interface.
- **Automated job sources** (Seek, LinkedIn, career pages, email, GradConnection, Prosple,
  Indeed) - the `JobSource` interface exists; only `ManualJobSource` (pasted text) is
  implemented, per the spec's explicit instruction not to build fragile scrapers in V1.
- **Education / work history / achievements editing UI** - the domain model, database, and API
  fully support these (and round-trip correctly), but the Profile page's editor currently only
  exposes skills, projects, evidence, and preferences. Education/work history can be set today
  via the seed JSON or a direct `PUT /api/candidate` call; the list-editor UI for them is the
  same pattern as the Skills/Projects editors already built, just not yet wired up.
- **Application tracking, tailored document generation, interview prep, and outcome-based
  calibration** - out of scope for V1 per the spec; the schema (e.g. `ai_traces`, stored
  `JobAnalysis` history) is structured so these can be layered on without a rewrite.
- **pgvector-based retrieval** - the `evidence.embedding` column and extension exist, but V1
  matching uses direct skill-tag/requirement-name comparison since the candidate's evidence set
  is small; semantic retrieval is reserved for when that stops being true.
