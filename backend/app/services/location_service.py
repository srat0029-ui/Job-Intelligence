"""Deterministic geographic eligibility gate - the highest-priority
correctness rule in the product: only postings clearly available to an
Australia-based candidate may ever reach the recommended feed or be
analysed.

This is intentionally NOT a scoring preference and NOT an LLM call. It is a
hard, deterministic text-normalisation pass over `RawJobPosting.location`
(primary signal) and, only when that's genuinely ambiguous, a narrow phrase
scan of `raw_description` for an explicit statement of Australian remote
eligibility. It runs once per posting in `DiscoveryService._process_posting`
immediately after source normalisation - identically for Adzuna, Lever,
Greenhouse, and any future adapter - so there is exactly one place "is this
job in Australia" is decided, never per-adapter logic.

Three outcomes, not two, because the DEBUGGING distinction matters even
though both are hidden from the recommended feed the same way:
- ELIGIBLE - a clear Australian signal was found (a known AU city/state, the
  word "Australia", or an explicit "remote - Australia" style phrase).
- INELIGIBLE - a clear NON-Australian signal was found (a known foreign
  city/country) with no Australian signal alongside it.
- LOCATION_UNCONFIRMED - neither a positive nor a confidently-foreign signal
  was found (bare "Remote", "Worldwide", "APAC", blank, or an unrecognised
  location string). Kept distinct from INELIGIBLE so "we don't know" is
  never silently reclassified as "we know it's overseas". This also covers
  a bare state-code collision such as "WA" (Western Australia or Washington
  State) or "Remote, WA" with no city/country/"Australia" alongside it - see
  AMBIGUOUS_AU_STATE_ABBREVIATIONS below: this gate fails closed rather than
  guessing when a 2-letter code is genuinely ambiguous.

Calibration source of truth: tests/unit/test_location_service.py - every
example the milestone brief called out by name is asserted there.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from app.domain.enums import GeographicEligibility

# --- Australia reference data ---

AU_STATE_ABBREVIATIONS: dict[str, str] = {
    "vic": "VIC",
    "nsw": "NSW",
    "qld": "QLD",
    "sa": "SA",
    "wa": "WA",
    "tas": "TAS",
    "nt": "NT",
    "act": "ACT",
}

AU_STATE_NAMES: dict[str, str] = {
    "victoria": "VIC",
    "new south wales": "NSW",
    "queensland": "QLD",
    "south australia": "SA",
    "western australia": "WA",
    "tasmania": "TAS",
    "northern territory": "NT",
    "australian capital territory": "ACT",
}

# city (lowercase) -> state abbreviation. Deliberately a modest, well-known
# set rather than an exhaustive gazetteer - "a robust deterministic text
# normalisation system is sufficient for the current product."
AU_CITIES: dict[str, str] = {
    "melbourne": "VIC",
    "geelong": "VIC",
    "ballarat": "VIC",
    "bendigo": "VIC",
    "sydney": "NSW",
    "newcastle": "NSW",
    "wollongong": "NSW",
    "wagga wagga": "NSW",
    "albury": "NSW",
    "brisbane": "QLD",
    "gold coast": "QLD",
    "sunshine coast": "QLD",
    "cairns": "QLD",
    "townsville": "QLD",
    "toowoomba": "QLD",
    "mackay": "QLD",
    "rockhampton": "QLD",
    "adelaide": "SA",
    "perth": "WA",
    "hobart": "TAS",
    "launceston": "TAS",
    "canberra": "ACT",
    "darwin": "NT",
    "alice springs": "NT",
}

# --- Foreign reference data (deliberately covers the milestone's explicit
# test examples plus the real overseas locations found in this project's
# own discovered_jobs data, so the backfill script correctly reclassifies
# real historical rows too) ---

FOREIGN_CITIES: dict[str, str] = {
    "new york": "United States",
    "san francisco": "United States",
    "seattle": "United States",
    "washington": "United States",
    "washington, d.c.": "United States",
    "palo alto": "United States",
    "denver": "United States",
    "miami": "United States",
    "fayetteville": "United States",
    "honolulu": "United States",
    "london": "United Kingdom",
    "toronto": "Canada",
    "auckland": "New Zealand",
    "singapore": "Singapore",
    "berlin": "Germany",
    "seoul": "South Korea",
    "amsterdam": "Netherlands",
    "tel aviv": "Israel",
    "tokyo": "Japan",
    "vilnius": "Lithuania",
    "abu dhabi": "United Arab Emirates",
    "dubai": "United Arab Emirates",
    "copenhagen": "Denmark",
    "paris": "France",
    "warsaw": "Poland",
    "stockholm": "Sweden",
}

FOREIGN_COUNTRY_PHRASES: dict[str, str] = {
    "united states": "United States",
    "usa": "United States",
    "u.s.a.": "United States",
    "us": "United States",
    "united kingdom": "United Kingdom",
    "uk": "United Kingdom",
    "canada": "Canada",
    "new zealand": "New Zealand",
    "india": "India",
    "germany": "Germany",
    "france": "France",
    "japan": "Japan",
    "south korea": "South Korea",
    "netherlands": "Netherlands",
    "sweden": "Sweden",
    "israel": "Israel",
    "poland": "Poland",
    "denmark": "Denmark",
    "united arab emirates": "United Arab Emirates",
    "uae": "United Arab Emirates",
    "lithuania": "Lithuania",
    "north america": "North America",
    "europe": "Europe",
    "emea": "EMEA",
}

# These AU state abbreviations collide with a well-known non-Australian
# meaning, so the bare 2-letter code alone is never sufficient evidence of
# Australia - "WA" is Western Australia *or* Washington State, "SA" is South
# Australia *or* South Africa, "NT" is the Northern Territory *or* Canada's
# Northwest Territories. Unlike the unambiguous codes (VIC, NSW, QLD, TAS,
# ACT), these require independent corroboration - a recognised AU city, the
# word "Australia", or the state's full name - before they're trusted (all
# handled by earlier steps in normalize_location). A bare, uncorroborated
# match on one of these must fail closed to LOCATION_UNCONFIRMED rather than
# being inferred as Australian.
AMBIGUOUS_AU_STATE_ABBREVIATIONS = {"wa", "sa", "nt"}

# Weak fallback signal only - checked last, only against the location
# string (never the description), only when nothing else matched.
US_STATE_CODES = {
    "ny", "ca", "tx", "fl", "nc", "co", "hi", "dc", "ma", "il", "pa", "ga",
    "oh", "mi", "nj", "az", "tn", "mo", "wi", "mn", "sc", "al", "la", "ky",
    "or", "ok", "ct", "ia", "ms", "ar", "ks", "ut", "nv", "nm", "ne", "wv",
    "id", "me", "nh", "ri", "mt", "de", "sd", "nd", "ak", "vt", "wy", "va",
}  # fmt: skip

AMBIGUOUS_REMOTE_TERMS = {"remote", "work from home", "wfh", "anywhere"}
AMBIGUOUS_SCOPE_TERMS = {"worldwide", "global", "apac"}

_AU_REMOTE_DESCRIPTION_PATTERNS = [
    re.compile(r"remote\s*[-–—]?\s*australia", re.IGNORECASE),
    re.compile(r"remote\s*\(australia\)", re.IGNORECASE),
    re.compile(r"remote,?\s*australia", re.IGNORECASE),
    re.compile(r"based\s+(anywhere\s+)?in\s+australia", re.IGNORECASE),
    re.compile(r"must\s+be\s+(based|located)\s+in\s+australia", re.IGNORECASE),
    re.compile(
        r"open\s+to\s+(candidates|applicants)\s+(based|located)\s+in\s+australia", re.IGNORECASE
    ),
    re.compile(r"eligible\s+to\s+work\s+in\s+australia", re.IGNORECASE),
    re.compile(r"australian?\s+applicants?\s+only", re.IGNORECASE),
    re.compile(r"australia\s+only", re.IGNORECASE),
]  # fmt: skip


class LocationNormalizationResult(BaseModel):
    country: str | None = None
    state: str | None = None
    city: str | None = None
    is_remote: bool = False
    eligibility: GeographicEligibility
    confidence: float
    reason: str


def _word_in(term: str, haystack: str) -> bool:
    return re.search(rf"\b{re.escape(term)}\b", haystack) is not None


def normalize_location(
    *, location: str | None, description: str | None = None, remote_type: str | None = None
) -> LocationNormalizationResult:
    """The single canonical eligibility rule every JobSource's normalised
    output goes through - see module docstring for the three-outcome
    design and tests/unit/test_location_service.py for the calibration
    examples this was tuned against."""
    raw = (location or "").strip()
    lowered = raw.lower()
    is_remote = remote_type == "remote" or any(t in lowered for t in AMBIGUOUS_REMOTE_TERMS)

    if not lowered or lowered in {"not specified", "unspecified", "n/a", "none"}:
        return LocationNormalizationResult(
            is_remote=is_remote,
            eligibility=GeographicEligibility.LOCATION_UNCONFIRMED,
            confidence=0.0,
            reason="No location information provided.",
        )

    # 1. Known foreign city - most specific, checked first so e.g. "Seattle,
    # WA" resolves as the US city rather than a Western Australia false
    # match on the bare state code "WA".
    for city, country in FOREIGN_CITIES.items():
        if _word_in(city, lowered):
            return LocationNormalizationResult(
                country=country,
                city=city.title(),
                is_remote=is_remote,
                eligibility=GeographicEligibility.INELIGIBLE,
                confidence=0.95,
                reason=f"Located in {city.title()}, {country} - not Australia.",
            )

    # 2. Known Australian city.
    for city, state in AU_CITIES.items():
        if _word_in(city, lowered):
            return LocationNormalizationResult(
                country="AU",
                state=state,
                city=city.title(),
                is_remote=is_remote,
                eligibility=GeographicEligibility.ELIGIBLE,
                confidence=0.95,
                reason=f"Located in {city.title()}, {state}, Australia.",
            )

    # 3. Literal "Australia" mention (e.g. "Remote Australia", "Australia -
    # Remote", bare "Australia").
    if _word_in("australia", lowered):
        australia_state = next(
            (abbr for name, abbr in AU_STATE_NAMES.items() if name in lowered), None
        )
        if australia_state is None:
            australia_state = next(
                (
                    abbr
                    for abbr in AU_STATE_ABBREVIATIONS.values()
                    if _word_in(abbr.lower(), lowered)
                ),
                None,
            )
        return LocationNormalizationResult(
            country="AU",
            state=australia_state,
            is_remote=is_remote,
            eligibility=GeographicEligibility.ELIGIBLE,
            confidence=0.9,
            reason="Location explicitly mentions Australia.",
        )

    # 4. Australian state name or abbreviation with no city recognised
    # (e.g. bare "Tasmania", "Victoria, Australia" already caught above).
    for name, abbr in AU_STATE_NAMES.items():
        if name in lowered:
            return LocationNormalizationResult(
                country="AU",
                state=abbr,
                is_remote=is_remote,
                eligibility=GeographicEligibility.ELIGIBLE,
                confidence=0.85,
                reason=f"Location matches the Australian state '{name.title()}'.",
            )
    ambiguous_abbr_match: str | None = None
    for abbr in AU_STATE_ABBREVIATIONS.values():
        if not _word_in(abbr.lower(), lowered):
            continue
        if abbr.lower() in AMBIGUOUS_AU_STATE_ABBREVIATIONS:
            ambiguous_abbr_match = abbr
            continue
        return LocationNormalizationResult(
            country="AU",
            state=abbr,
            is_remote=is_remote,
            eligibility=GeographicEligibility.ELIGIBLE,
            confidence=0.8,
            reason=f"Location contains the Australian state code '{abbr}'.",
        )

    # 5. Known foreign country/region phrase.
    for phrase, country in FOREIGN_COUNTRY_PHRASES.items():
        if _word_in(phrase, lowered):
            return LocationNormalizationResult(
                country=country,
                is_remote=is_remote,
                eligibility=GeographicEligibility.INELIGIBLE,
                confidence=0.85,
                reason=f"Location matches '{phrase.title()}' - not Australia.",
            )

    # 6. Weak fallback: a bare US state code with nothing else recognised.
    for code in US_STATE_CODES:
        if _word_in(code, lowered):
            return LocationNormalizationResult(
                country="United States",
                is_remote=is_remote,
                eligibility=GeographicEligibility.INELIGIBLE,
                confidence=0.6,
                reason=f"Location contains the US state code '{code.upper()}'.",
            )

    # 7. Genuinely ambiguous - bare remote/worldwide/global/apac, or an
    # unrecognised location string. Give the description one narrow chance
    # to prove Australian eligibility before giving up.
    if description:
        for pattern in _AU_REMOTE_DESCRIPTION_PATTERNS:
            if pattern.search(description):
                return LocationNormalizationResult(
                    country="AU",
                    is_remote=True,
                    eligibility=GeographicEligibility.ELIGIBLE,
                    confidence=0.7,
                    reason="Description explicitly confirms Australian eligibility.",
                )

    scope_term = next((t for t in AMBIGUOUS_SCOPE_TERMS if _word_in(t, lowered)), None)
    if ambiguous_abbr_match:
        reason = (
            f"Location contains the ambiguous state code '{ambiguous_abbr_match}', which "
            "could mean an Australian state or a non-Australian region that uses the same "
            "code (e.g. Washington State) - no independent Australian evidence was found."
        )
    elif scope_term:
        reason = (
            f"Location says '{scope_term}' with no evidence Australia specifically is eligible."
        )
    elif is_remote:
        reason = "Location says 'remote' with no country/region specified."
    else:
        reason = (
            f"Location is ambiguous ('{raw}') and no explicit Australian "
            "eligibility statement was found."
        )
    return LocationNormalizationResult(
        is_remote=is_remote,
        eligibility=GeographicEligibility.LOCATION_UNCONFIRMED,
        confidence=0.0,
        reason=reason,
    )
