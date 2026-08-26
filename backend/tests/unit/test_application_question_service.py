"""Unit tests for application-question classification (deterministic) and
deterministic salary/work-rights answering - these must never be answered
by the LLM when the profile already has the data."""

from __future__ import annotations

import uuid

from app.ai.providers.fake_provider import FakeLLMProvider
from app.ai.schemas.application_question import LLMApplicationQuestionOutput
from app.domain.candidate import Candidate, CandidatePreferences
from app.domain.communication_style import CommunicationStyle
from app.domain.enums import AIOperationType, QuestionType
from app.services.application_question_service import ApplicationQuestionService, classify_question


def test_classify_salary_question():
    assert QuestionType.SALARY in classify_question("What is your expected salary?")


def test_classify_work_rights_question():
    assert QuestionType.WORK_RIGHTS in classify_question("Do you require visa sponsorship?")


def test_classify_company_motivation_question():
    assert QuestionType.COMPANY_MOTIVATION in classify_question("Why do you want to work here?")


def test_unclassifiable_question_falls_back_to_general_background():
    assert classify_question("Random unrelated text with no keywords.") == [
        QuestionType.GENERAL_BACKGROUND
    ]


def test_salary_question_answered_deterministically_when_profile_has_data():
    candidate = Candidate(
        name="Test",
        preferences=CandidatePreferences(
            salary_expectation_min=90000, salary_expectation_max=110000, salary_currency="AUD"
        ),
    )
    fake_llm = FakeLLMProvider()  # would raise if called - proves no LLM call happens
    service = ApplicationQuestionService(fake_llm)

    response, trace = service.answer(
        workspace_id=uuid.uuid4(), question_text="What is your expected salary?",
        job_title="Engineer", company="Acme", candidate=candidate, evidence=[],
        research_claims=[], style=CommunicationStyle(), input_identifier="test",
    )
    assert response.answered_deterministically is True
    assert "90000" in response.response_text
    assert trace is None


def test_work_rights_question_answered_deterministically_when_profile_has_data():
    candidate = Candidate(
        name="Test",
        preferences=CandidatePreferences(work_rights=["Australian Citizen"]),
    )
    fake_llm = FakeLLMProvider()
    service = ApplicationQuestionService(fake_llm)

    response, trace = service.answer(
        workspace_id=uuid.uuid4(), question_text="Do you have the right to work in Australia?",
        job_title="Engineer", company="Acme", candidate=candidate, evidence=[],
        research_claims=[], style=CommunicationStyle(), input_identifier="test",
    )
    assert response.answered_deterministically is True
    assert "Australian Citizen" in response.response_text


def test_salary_question_falls_through_to_llm_when_no_profile_data():
    candidate = Candidate(name="Test")  # no salary preferences set
    fake_llm = FakeLLMProvider()
    fake_llm.set_response(
        AIOperationType.APPLICATION_QUESTION,
        LLMApplicationQuestionOutput(
            response_text="I'd like to discuss salary during the process."
        ),
    )
    service = ApplicationQuestionService(fake_llm)

    response, trace = service.answer(
        workspace_id=uuid.uuid4(), question_text="What is your expected salary?",
        job_title="Engineer", company="Acme", candidate=candidate, evidence=[],
        research_claims=[], style=CommunicationStyle(), input_identifier="test",
    )
    assert response.answered_deterministically is False
    assert trace is not None


def test_general_question_uses_llm_with_grounded_evidence():
    candidate = Candidate(name="Test")
    fake_llm = FakeLLMProvider()
    fake_llm.set_response(
        AIOperationType.APPLICATION_QUESTION,
        LLMApplicationQuestionOutput(response_text="I led a small team on a university project."),
    )
    service = ApplicationQuestionService(fake_llm)

    response, trace = service.answer(
        workspace_id=uuid.uuid4(), question_text="Describe a time you showed leadership.",
        job_title="Engineer", company="Acme", candidate=candidate, evidence=[],
        research_claims=[], style=CommunicationStyle(), input_identifier="test",
    )
    assert QuestionType.LEADERSHIP in response.classifications
    assert trace is not None
