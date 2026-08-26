"""Calibration tests for the deterministic Australia eligibility gate -
every example named explicitly in the milestone brief is asserted here."""

from __future__ import annotations

import pytest

from app.domain.enums import GeographicEligibility
from app.services.location_service import normalize_location

INCLUDE_LOCATIONS = [
    "Melbourne, VIC",
    "Melbourne, Australia",
    "Sydney NSW",
    "Hobart TAS",
    "Brisbane QLD",
    "Perth WA",
    "Adelaide SA",
    "Canberra ACT",
    "Darwin NT",
    "Remote Australia",
    "Australia - Remote",
    "Victoria, Australia",
    "Tasmania",
    "Australia",
]

EXCLUDE_LOCATIONS = [
    "New York",
    "San Francisco",
    "London",
    "Toronto",
    "Singapore",
    "Auckland",
    "Remote - US",
    "United States",
    "UK",
    "India",
    "Berlin",
]

DO_NOT_RECOMMEND_LOCATIONS = [
    "Remote",
    "Worldwide",
    "Global",
    "APAC",
    "",
]


@pytest.mark.parametrize("location", INCLUDE_LOCATIONS)
def test_australian_locations_are_eligible(location):
    result = normalize_location(location=location)
    assert result.eligibility == GeographicEligibility.ELIGIBLE, (location, result.reason)
    assert result.country == "AU"


@pytest.mark.parametrize("location", EXCLUDE_LOCATIONS)
def test_overseas_locations_are_ineligible(location):
    result = normalize_location(location=location)
    assert result.eligibility == GeographicEligibility.INELIGIBLE, (location, result.reason)
    assert result.country != "AU"


@pytest.mark.parametrize("location", DO_NOT_RECOMMEND_LOCATIONS)
def test_ambiguous_locations_are_unconfirmed_not_eligible(location):
    result = normalize_location(location=location)
    assert result.eligibility != GeographicEligibility.ELIGIBLE, (location, result.reason)


def test_generic_remote_is_unconfirmed_not_ineligible():
    """A bare "Remote" isn't confidently foreign either - it's genuinely
    unknown, and the two must stay distinguishable for debugging."""
    result = normalize_location(location="Remote")
    assert result.eligibility == GeographicEligibility.LOCATION_UNCONFIRMED
    assert result.is_remote is True


def test_remote_with_explicit_australia_description_is_eligible():
    result = normalize_location(
        location="Remote",
        description="This role is remote - Australia based candidates only.",
    )
    assert result.eligibility == GeographicEligibility.ELIGIBLE
    assert result.country == "AU"


def test_generic_remote_us_company_is_not_rescued_by_unrelated_australia_mention():
    """A stray mention of Australia somewhere in a big description (e.g.
    "we have a small Australia office") must never override a confidently
    foreign location - only a genuinely ambiguous location gets the
    description-rescue chance."""
    result = normalize_location(
        location="New York",
        description="We have offices in New York and a small Australia office too.",
    )
    assert result.eligibility == GeographicEligibility.INELIGIBLE


def test_city_beats_ambiguous_us_state_code_collision():
    """"Perth WA" must resolve as Western Australia, and "Seattle, WA" must
    resolve as Washington state (US) - the same two-letter code, resolved
    correctly by city context in both directions."""
    perth = normalize_location(location="Perth WA")
    assert perth.eligibility == GeographicEligibility.ELIGIBLE
    assert perth.state == "WA"

    seattle = normalize_location(location="Seattle, WA")
    assert seattle.eligibility == GeographicEligibility.INELIGIBLE
    assert seattle.country == "United States"


def test_no_location_provided_is_unconfirmed():
    result = normalize_location(location=None)
    assert result.eligibility == GeographicEligibility.LOCATION_UNCONFIRMED


def test_real_historical_overseas_locations_are_ineligible():
    """The exact set of overseas locations found in this project's own
    discovered_jobs table before the fix (see the M4A->this-milestone
    root-cause investigation) - a regression guard for the backfill."""
    real_overseas = [
        "Washington, D.C.",
        "New York, NY",
        "London, United Kingdom",
        "Seoul, South Korea",
        "Amsterdam, Netherlands",
        "Honolulu, HI",
        "Palo Alto, CA",
        "Stockholm, Sweden",
        "Tel Aviv, Israel",
        "Tokyo, Japan",
        "Vilnius, Lithuania",
        "Abu Dhabi, United Arab Emirates",
        "Copenhagen, Denmark",
        "Denver, CO",
        "Dubai, United Arab Emirates",
        "Fayetteville, NC",
        "Miami, FL",
        "Paris, France",
        "Seattle, WA",
        "Singapore, Singapore",
        "Warsaw, Poland",
    ]
    for location in real_overseas:
        result = normalize_location(location=location)
        assert result.eligibility == GeographicEligibility.INELIGIBLE, (location, result.reason)


def test_real_historical_australian_location_stays_eligible():
    result = normalize_location(location="Sydney, Australia")
    assert result.eligibility == GeographicEligibility.ELIGIBLE
