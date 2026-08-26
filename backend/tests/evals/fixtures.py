"""Loads job-extraction eval fixtures from tests/evals/fixtures/*.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@dataclass
class ExtractionFixture:
    name: str
    title: str
    company: str
    location: str | None
    raw_description: str
    expected_required_skills: list[str]
    expected_preferred_skills: list[str]
    expected_role_category_keywords: list[str]


def load_fixtures() -> list[ExtractionFixture]:
    fixtures = []
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        fixtures.append(
            ExtractionFixture(
                name=path.stem,
                title=data["title"],
                company=data["company"],
                location=data.get("location"),
                raw_description=data["raw_description"],
                expected_required_skills=data.get("expected_required_skills", []),
                expected_preferred_skills=data.get("expected_preferred_skills", []),
                expected_role_category_keywords=data.get("expected_role_category_keywords", []),
            )
        )
    return fixtures
