"""Unit tests for automatic discovery scheduling
(`run_scheduled_discovery_if_due`).

Calls the tick function directly rather than spinning up a real
APScheduler thread - it's a plain function specifically so it can be
tested this way. `DiscoveryService` is faked out (its own pipeline is
covered by tests/integration/test_discovery_pipeline.py) so these tests
stay focused on the scheduling decision itself: due vs. not-due,
enabled vs. disabled, and graceful handling of an already-running
discovery run (overlap prevention).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

import app.scheduler as scheduler_module
from app.repositories.app_settings_repository import AppSettingsRepository
from app.services.discovery_service import DiscoveryAlreadyRunningError


class _FakeDiscoveryService:
    """Records whether/how it was invoked instead of running the real
    (expensive, network-calling) discovery pipeline."""

    calls: list[str] = []
    raise_already_running = False

    def __init__(self, llm_provider=None) -> None:
        pass

    def run(self, db, *, triggered_by="manual"):
        if _FakeDiscoveryService.raise_already_running:
            raise DiscoveryAlreadyRunningError("a run is already in progress")
        _FakeDiscoveryService.calls.append(triggered_by)


@pytest.fixture(autouse=True)
def _reset_fake_service():
    _FakeDiscoveryService.calls = []
    _FakeDiscoveryService.raise_already_running = False
    yield
    _FakeDiscoveryService.calls = []
    _FakeDiscoveryService.raise_already_running = False


@pytest.fixture()
def patched_scheduler(monkeypatch, engine, db):
    """Points the scheduler's module-level SessionLocal at the test
    database (it normally binds to the real dev DB via app.db.session),
    and swaps in the fake DiscoveryService."""
    test_session_factory = sessionmaker(bind=engine, future=True)
    monkeypatch.setattr(scheduler_module, "SessionLocal", test_session_factory)
    monkeypatch.setattr(scheduler_module, "DiscoveryService", _FakeDiscoveryService)
    monkeypatch.setattr(scheduler_module, "get_llm_provider", lambda: None)
    return scheduler_module


def test_noop_when_auto_discovery_disabled(patched_scheduler, db):
    settings_repo = AppSettingsRepository()
    settings = settings_repo.get(db)
    assert settings.auto_discovery_enabled is False  # default

    patched_scheduler.run_scheduled_discovery_if_due()

    assert _FakeDiscoveryService.calls == []
    unchanged = settings_repo.get(db)
    assert unchanged.last_scheduled_run_at is None


def test_noop_when_not_yet_due(patched_scheduler, db):
    settings_repo = AppSettingsRepository()
    settings_repo.update(
        db, settings_repo.get(db).model_copy(update={"auto_discovery_enabled": True})
    )
    future = datetime.now(UTC) + timedelta(hours=2)
    settings_repo.set_schedule_timestamps(db, next_scheduled_run_at=future)

    patched_scheduler.run_scheduled_discovery_if_due()

    assert _FakeDiscoveryService.calls == []


def test_runs_and_updates_timestamps_when_due(patched_scheduler, db):
    settings_repo = AppSettingsRepository()
    enabled = settings_repo.get(db).model_copy(
        update={"auto_discovery_enabled": True, "discovery_frequency_hours": 6}
    )
    settings_repo.update(db, enabled)
    past = datetime.now(UTC) - timedelta(hours=1)
    settings_repo.set_schedule_timestamps(db, next_scheduled_run_at=past)

    before = datetime.now(UTC)
    patched_scheduler.run_scheduled_discovery_if_due()
    after = datetime.now(UTC)

    assert _FakeDiscoveryService.calls == ["scheduled"]

    updated = settings_repo.get(db)
    assert updated.last_scheduled_run_at is not None
    last_run = updated.last_scheduled_run_at.replace(tzinfo=UTC)
    assert before.replace(tzinfo=None) <= last_run.replace(tzinfo=None) <= after.replace(
        tzinfo=None
    )
    expected_next = last_run + timedelta(hours=6)
    next_run = updated.next_scheduled_run_at.replace(tzinfo=UTC)
    assert abs((next_run - expected_next).total_seconds()) < 1


def test_runs_when_next_scheduled_run_at_is_never_set(patched_scheduler, db):
    """A freshly-enabled schedule (no prior run) must be treated as due
    immediately rather than never firing."""
    settings_repo = AppSettingsRepository()
    enabled = settings_repo.get(db).model_copy(update={"auto_discovery_enabled": True})
    settings_repo.update(db, enabled)

    patched_scheduler.run_scheduled_discovery_if_due()

    assert _FakeDiscoveryService.calls == ["scheduled"]


def test_already_running_discovery_is_skipped_gracefully(patched_scheduler, db):
    """Overlap prevention: if a run is already in progress, the tick must
    not raise, and must still update its own bookkeeping timestamps so it
    doesn't spin trying the same instant again."""
    settings_repo = AppSettingsRepository()
    enabled = settings_repo.get(db).model_copy(update={"auto_discovery_enabled": True})
    settings_repo.update(db, enabled)
    _FakeDiscoveryService.raise_already_running = True

    patched_scheduler.run_scheduled_discovery_if_due()  # must not raise

    updated = settings_repo.get(db)
    assert updated.last_scheduled_run_at is not None
