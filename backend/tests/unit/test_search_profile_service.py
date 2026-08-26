"""Unit tests for search profile CRUD + enabled/disabled behaviour."""

from __future__ import annotations

from app.domain.discovery import SearchProfile
from app.domain.enums import SeniorityLevel
from app.services.search_profile_service import SearchProfileService


def test_create_and_get_round_trip(db):
    service = SearchProfileService()
    created = service.create(
        db,
        SearchProfile(
            name="AI / Data Early Career",
            keywords=["graduate data scientist", "junior ai engineer"],
            locations=["Melbourne", "Hobart"],
            include_remote=True,
            max_experience_level=SeniorityLevel.GRADUATE,
        ),
    )
    assert created.id is not None

    fetched = service.get(db, created.id)
    assert fetched is not None
    assert fetched.name == "AI / Data Early Career"
    assert fetched.keywords == ["graduate data scientist", "junior ai engineer"]
    assert fetched.max_experience_level == SeniorityLevel.GRADUATE


def test_disabled_profiles_excluded_from_list_enabled(db):
    service = SearchProfileService()
    enabled = service.create(db, SearchProfile(name="Enabled", enabled=True))
    service.create(db, SearchProfile(name="Disabled", enabled=False))

    enabled_profiles = service.list_enabled(db)

    assert [p.id for p in enabled_profiles] == [enabled.id]


def test_update_persists_changes(db):
    service = SearchProfileService()
    created = service.create(db, SearchProfile(name="Original", keywords=["a"]))

    updated = service.update(
        db, created.id, SearchProfile(name="Renamed", keywords=["a", "b"], enabled=False)
    )

    assert updated is not None
    assert updated.name == "Renamed"
    assert updated.keywords == ["a", "b"]
    assert updated.enabled is False


def test_delete_removes_profile(db):
    service = SearchProfileService()
    created = service.create(db, SearchProfile(name="To Delete"))

    assert service.delete(db, created.id) is True
    assert service.get(db, created.id) is None
    assert service.delete(db, created.id) is False
