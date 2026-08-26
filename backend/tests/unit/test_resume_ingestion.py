"""Unit tests for CV/resume ingestion.

`extract_text_from_pdf` is tested against real (if minimal) invalid input.
`ResumeFileSource` is tested with `extract_text_from_pdf` monkeypatched to
return fixed text - this avoids needing to hand-construct a real PDF binary
just to test the extraction/provenance logic downstream of text extraction,
which is the part actually worth testing here.
"""

from __future__ import annotations

import pytest

from app.ai.providers.fake_provider import FakeLLMProvider
from app.ai.schemas.cv_extraction import CVExtraction
from app.domain.candidate import Achievement, Education, Evidence, Skill
from app.domain.enums import AIOperationType, EvidenceSourceType
from app.ingestion import candidate_document_source
from app.ingestion.candidate_document_source import ResumeFileSource
from app.ingestion.pdf_text import UnreadablePdfError, extract_text_from_pdf


def test_extract_text_from_pdf_rejects_garbage_bytes():
    with pytest.raises(UnreadablePdfError):
        extract_text_from_pdf(b"this is not a pdf file at all")


def test_resume_file_source_forces_cv_provenance_on_evidence(monkeypatch):
    monkeypatch.setattr(
        candidate_document_source, "extract_text_from_pdf", lambda data: "Jane Doe resume text"
    )

    provider = FakeLLMProvider()
    provider.set_response(
        AIOperationType.CV_EXTRACTION,
        CVExtraction(
            name="Jane Doe",
            email="jane@example.com",
            education=[Education(institution="Uni", qualification="BSc")],
            skills=[Skill(name="Python")],
            achievements=[Achievement(title="Won a hackathon")],
            evidence=[
                Evidence(
                    # The model might set anything here - it should be
                    # ignored/overwritten, never trusted.
                    source_type="work_experience",
                    source_label="whatever the model said",
                    statement="Built a Python service",
                    skill_tags=["python"],
                )
            ],
        ),
    )

    source = ResumeFileSource(
        pdf_bytes=b"irrelevant", filename="jane_doe.pdf", llm_provider=provider
    )
    candidate, trace = source.load()

    assert candidate.name == "Jane Doe"
    assert candidate.email == "jane@example.com"
    assert len(candidate.education) == 1
    assert len(candidate.skills) == 1
    assert len(candidate.achievements) == 1

    assert len(candidate.evidence) == 1
    assert candidate.evidence[0].source_type == EvidenceSourceType.CV.value
    assert "jane_doe.pdf" in candidate.evidence[0].source_label

    assert trace is not None
    assert trace.operation_type == AIOperationType.CV_EXTRACTION


def test_resume_file_source_never_extracts_preferences(monkeypatch):
    """Preferences (salary, location, remote, work rights) are never
    inferred from a CV - they stay manually curated."""
    monkeypatch.setattr(
        candidate_document_source, "extract_text_from_pdf", lambda data: "resume text"
    )
    provider = FakeLLMProvider()
    provider.set_response(AIOperationType.CV_EXTRACTION, CVExtraction(name="Someone"))

    source = ResumeFileSource(pdf_bytes=b"irrelevant", filename="cv.pdf", llm_provider=provider)
    candidate, _trace = source.load()

    assert candidate.preferences.salary_expectation_min is None
    assert candidate.preferences.preferred_locations == []
    assert candidate.preferences.work_rights == []
