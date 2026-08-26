"""Unit tests for company watchlist CRUD."""

from __future__ import annotations

from app.domain.company_watchlist import CompanyWatchlistEntry
from app.domain.enums import ATSType, CompanyPriority
from app.services.company_watchlist_service import CompanyWatchlistService


def test_create_and_get_round_trip(db):
    service = CompanyWatchlistService()
    created = service.create(
        db,
        CompanyWatchlistEntry(
            company_name="Data Co",
            ats_type=ATSType.LEVER,
            ats_identifier="data-co",
            priority=CompanyPriority.HIGH,
            preferred_locations=["Melbourne"],
        ),
    )
    assert created.id is not None
    assert created.source_key == "lever:data-co"

    fetched = service.get(db, created.id)
    assert fetched is not None
    assert fetched.company_name == "Data Co"
    assert fetched.priority == CompanyPriority.HIGH


def test_disabled_entries_excluded_from_list_enabled(db):
    service = CompanyWatchlistService()
    enabled = service.create(
        db,
        CompanyWatchlistEntry(
            company_name="Enabled Co", ats_type=ATSType.LEVER, ats_identifier="enabled-co"
        ),
    )
    service.create(
        db,
        CompanyWatchlistEntry(
            company_name="Disabled Co",
            ats_type=ATSType.GREENHOUSE,
            ats_identifier="disabled-co",
            enabled=False,
        ),
    )

    enabled_entries = service.list_enabled(db)
    assert [e.id for e in enabled_entries] == [enabled.id]


def test_update_and_delete(db):
    service = CompanyWatchlistService()
    created = service.create(
        db,
        CompanyWatchlistEntry(
            company_name="Original", ats_type=ATSType.LEVER, ats_identifier="original"
        ),
    )

    updated = service.update(
        db,
        created.id,
        CompanyWatchlistEntry(
            company_name="Renamed",
            ats_type=ATSType.LEVER,
            ats_identifier="original",
            priority=CompanyPriority.LOW,
        ),
    )
    assert updated is not None
    assert updated.company_name == "Renamed"
    assert updated.priority == CompanyPriority.LOW

    assert service.delete(db, created.id) is True
    assert service.get(db, created.id) is None
