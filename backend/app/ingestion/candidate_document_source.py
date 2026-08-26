"""Interface for ingesting candidate documents (CVs, portfolios, etc).

Not wired into the API in V1 - the only working implementation is
`SeedFileCandidateSource`, used by the seed script to load the initial
candidate profile from a structured JSON file. Adding a real CV parser
(PDF/DOCX -> structured Candidate fields, likely via an LLM extraction
step similar to job extraction) is future work; the interface exists now so
that work slots in without touching CandidateService or the API layer.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from app.domain.candidate import Candidate


class CandidateDocumentSource(ABC):
    """A source that can produce a (partial or full) Candidate profile."""

    @abstractmethod
    def load(self) -> Candidate:
        raise NotImplementedError


class SeedFileCandidateSource(CandidateDocumentSource):
    """Loads a Candidate from a structured JSON seed file.

    This is intentionally NOT a CV parser - it reads already-structured
    JSON (see app/seed/candidate_seed.json). A future `ResumeFileSource`
    implementing this same interface would take an uploaded PDF/DOCX and run
    it through an LLM extraction step to produce the same `Candidate` shape.
    """

    def __init__(self, seed_path: Path) -> None:
        self._seed_path = seed_path

    def load(self) -> Candidate:
        data = json.loads(self._seed_path.read_text(encoding="utf-8"))
        return Candidate.model_validate(data)
