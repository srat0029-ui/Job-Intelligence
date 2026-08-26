"""Interface for ingesting candidate documents (CVs, portfolios, etc).

Two implementations:
- `SeedFileCandidateSource` reads already-structured JSON (see
  app/seed/candidate_seed.json) - no AI involved, `trace` is always None.
- `ResumeFileSource` takes raw PDF bytes, extracts text, and runs it through
  an LLM extraction step (see app/ai/prompts/cv_extraction_v1.py) to produce
  the same `Candidate` shape, with `trace` set to the resulting AITrace.

`load()` returns the parsed data ONLY - it never touches the database.
Nothing here overwrites the stored candidate profile: the API route that
calls `ResumeFileSource.load()` returns the result to the client as a
*proposal* for review, and the existing `PUT /api/candidate` (already
wired to the Profile page's "Save profile" button) is what the user
explicitly triggers to actually persist any of it. See
app/api/routes/candidate.py.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from app.ai.prompts import cv_extraction_v1
from app.ai.providers.base import LLMProvider
from app.ai.schemas.cv_extraction import CVExtraction
from app.domain.ai_trace import AITrace
from app.domain.candidate import Candidate, CandidatePreferences, Evidence
from app.domain.enums import AIOperationType, EvidenceSourceType
from app.ingestion.pdf_text import extract_text_from_pdf


class CandidateDocumentSource(ABC):
    """A source that can produce a (partial or full) Candidate profile."""

    @abstractmethod
    def load(self) -> tuple[Candidate, AITrace | None]:
        raise NotImplementedError


class SeedFileCandidateSource(CandidateDocumentSource):
    """Loads a Candidate from a structured JSON seed file - not a CV parser,
    just a bulk-load mechanism for already-structured data."""

    def __init__(self, seed_path: Path) -> None:
        self._seed_path = seed_path

    def load(self) -> tuple[Candidate, AITrace | None]:
        data = json.loads(self._seed_path.read_text(encoding="utf-8"))
        return Candidate.model_validate(data), None


class ResumeFileSource(CandidateDocumentSource):
    """Parses an uploaded PDF resume into a Candidate-shaped proposal via a
    single LLM extraction call. Evidence provenance is forced to "cv" in
    code, never trusted from the model output."""

    def __init__(self, *, pdf_bytes: bytes, filename: str, llm_provider: LLMProvider) -> None:
        self._pdf_bytes = pdf_bytes
        self._filename = filename
        self._llm_provider = llm_provider

    def load(self) -> tuple[Candidate, AITrace | None]:
        resume_text = extract_text_from_pdf(self._pdf_bytes)
        user_prompt = cv_extraction_v1.build_user_prompt(resume_text=resume_text)

        result = self._llm_provider.generate_structured(
            operation_type=AIOperationType.CV_EXTRACTION,
            prompt_version=cv_extraction_v1.PROMPT_VERSION,
            system_prompt=cv_extraction_v1.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_schema=CVExtraction,
            input_identifier=self._filename,
        )
        extraction: CVExtraction = result.output

        evidence = [
            Evidence(
                source_type=EvidenceSourceType.CV.value,
                source_label=f"CV: {self._filename}",
                statement=e.statement,
                skill_tags=list(e.skill_tags),
            )
            for e in extraction.evidence
        ]

        candidate = Candidate(
            name=extraction.name or "",
            email=extraction.email,
            summary=extraction.summary,
            education=extraction.education,
            work_history=extraction.work_history,
            projects=extraction.projects,
            skills=extraction.skills,
            achievements=extraction.achievements,
            certifications=extraction.certifications,
            evidence=evidence,
            preferences=CandidatePreferences(),
        )
        return candidate, result.trace
