"""Unit tests for ApplicationWorkspaceRepository, including a regression
test for a race found via manual browser testing: two near-simultaneous
get_or_create calls for the same job (a double-fired React effect, in
practice) must not raise a unique-constraint IntegrityError up to the
caller - the loser of the race should just read back what the winner
created."""

from __future__ import annotations

from app.db.models.application_workspace import ApplicationWorkspaceModel
from app.domain.enums import JobSourceType
from app.ingestion.job_source import RawJobPosting
from app.repositories.application_workspace_repository import ApplicationWorkspaceRepository
from app.repositories.job_repository import JobRepository


def _seed_job(db):
    return JobRepository().create_from_posting(
        db,
        RawJobPosting(
            title="Engineer", company="Acme", source_type=JobSourceType.MANUAL,
            raw_description="desc",
        ),
    )


def test_get_or_create_returns_same_workspace_on_repeated_calls(db):
    job = _seed_job(db)
    repo = ApplicationWorkspaceRepository()

    first = repo.get_or_create(db, job.id)
    second = repo.get_or_create(db, job.id)

    assert first.id == second.id


def test_get_or_create_survives_concurrent_insert_race(db, monkeypatch):
    """Forces the exact interleaving a real race produces: a row for this
    job already exists (as if a concurrent request just created it), but
    this call's own initial SELECT is made to behave as if it ran before
    that - so it still attempts its own INSERT and hits the real
    unique-constraint conflict, which get_or_create must recover from
    rather than let propagate.
    """
    job = _seed_job(db)
    repo = ApplicationWorkspaceRepository()

    existing = ApplicationWorkspaceModel(job_id=job.id)
    db.add(existing)
    db.commit()
    db.refresh(existing)

    real_execute = db.execute
    call_count = {"n": 0}

    class _EmptyResult:
        def scalar_one_or_none(self):
            return None

    def racy_execute(statement, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _EmptyResult()
        return real_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db, "execute", racy_execute)

    result = repo.get_or_create(db, job.id)
    assert result.id == existing.id
