"""Seeds (or re-seeds) the candidate profile from app/seed/candidate_seed.json.

Run with: python scripts/seed.py [path/to/other_seed.json]

This is the one supported way to bulk-load candidate data in V1. It goes
through CandidateService/CandidateRepository like any other write, so it's
exercising the same code path a future "upload CV" flow would use - only the
CandidateDocumentSource implementation differs (SeedFileCandidateSource vs a
future ResumeFileSource).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.ingestion.candidate_document_source import SeedFileCandidateSource  # noqa: E402
from app.services.candidate_service import CandidateService  # noqa: E402

DEFAULT_SEED_PATH = Path(__file__).resolve().parent.parent / "app" / "seed" / "candidate_seed.json"


def main() -> None:
    seed_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SEED_PATH
    source = SeedFileCandidateSource(seed_path)
    candidate = source.load()

    db = SessionLocal()
    try:
        saved = CandidateService().save_profile(db, candidate)
        print(f"Seeded candidate '{saved.name}' with {len(saved.projects)} projects, "
              f"{len(saved.evidence)} evidence records, {len(saved.skills)} skills.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
