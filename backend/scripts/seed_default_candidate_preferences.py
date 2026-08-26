"""One-off maintenance script: seeds the candidate's default job-search
preferences (Part 12 of the product-simplification brief).

These are the specific, real preferences the product is being built around
right now (early-career AI/ML/data/software roles, Melbourne/Hobart highest
priority, Sydney/Brisbane also acceptable, no senior-level roles) - but they
are seeded as *data* (the candidate's `preferences` fields, and the existing
"AI / Data Early Career" SearchProfile's `locations`/`max_experience_level`
knobs), not hard-coded into any domain/service code. Editing them later only
ever means editing this profile/search-profile data (via the Profile page,
the Advanced > Discover search-profile editor, or re-running this script),
never a code change.

Safe to re-run: it reads the existing candidate/search-profile rows and only
overwrites the specific preference fields below, leaving skills, evidence,
projects, and everything else untouched.

Usage:

    python scripts/seed_default_candidate_preferences.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.domain.enums import SeniorityLevel  # noqa: E402
from app.repositories.candidate_repository import CandidateRepository  # noqa: E402
from app.repositories.search_profile_repository import SearchProfileRepository  # noqa: E402

DEFAULT_JOB_CATEGORIES = [
    "AI/ML",
    "Data Science",
    "Data Analytics",
    "Software Engineering",
    "Tech Consulting",
    "Cloud",
    "Cyber Security",
    "Graduate Program",
]

# Priority tier (Melbourne/Victoria, Hobart/Tasmania) first, then the
# "also acceptable" tier (Sydney/NSW, Brisbane/QLD) - the scoring component
# that reads this list only does a flat preferred/not-preferred check today,
# so ordering itself has no functional effect, but keeping it in stated
# priority order makes this file readable as the source of truth.
DEFAULT_PREFERRED_LOCATIONS = [
    "Melbourne",
    "Victoria",
    "Hobart",
    "Tasmania",
    "Sydney",
    "New South Wales",
    "Brisbane",
    "Queensland",
]


def main() -> int:
    db = SessionLocal()
    try:
        candidate_repo = CandidateRepository()
        candidate = candidate_repo.get_singleton(db)
        if candidate is None:
            print("No candidate profile exists yet - nothing to seed. Create one first.")
            return 1

        candidate.preferences.preferred_job_categories = DEFAULT_JOB_CATEGORIES
        candidate.preferences.preferred_locations = DEFAULT_PREFERRED_LOCATIONS
        candidate_repo.upsert(db, candidate)
        print(
            "Candidate preferences updated: "
            f"preferred_job_categories={DEFAULT_JOB_CATEGORIES}, "
            f"preferred_locations={DEFAULT_PREFERRED_LOCATIONS}"
        )

        profile_repo = SearchProfileRepository()
        profiles = profile_repo.list_all(db)
        early_career = next(
            (p for p in profiles if p.name == "AI / Data Early Career"), None
        )
        if early_career is not None:
            early_career.locations = DEFAULT_PREFERRED_LOCATIONS
            early_career.max_experience_level = SeniorityLevel.JUNIOR
            assert early_career.id is not None
            profile_repo.update(db, early_career.id, early_career)
            print(
                f"Search profile '{early_career.name}' updated: "
                f"locations={DEFAULT_PREFERRED_LOCATIONS}, max_experience_level=junior "
                "(rejects senior/lead/principal/staff/director/head-of titles and "
                "postings requiring 6+ years experience)."
            )
        else:
            print(
                "No 'AI / Data Early Career' search profile found - skipped "
                "the seniority-ceiling/location update for it."
            )

        db.commit()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
