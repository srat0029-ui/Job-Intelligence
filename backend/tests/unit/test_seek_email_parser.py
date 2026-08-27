"""Tests for app/ingestion/seek_email_parser.py.

Fixture HTML is inline (matching the existing test_adzuna_source.py style
rather than separate fixture files) - a realistic-shape synthetic SEEK
alert since this session has no real inbox access (see the parser's own
docstring)."""

from __future__ import annotations

from app.domain.enums import JobSourceType
from app.ingestion.seek_email_parser import parse_seek_alert_email


def _job_row(job_id: str, title: str, company: str, location: str, extra: str = "") -> str:
    return f"""
    <table>
      <tr>
        <td>
          <a href="https://www.seek.com.au/job/{job_id}?type=standard">{title}</a>
          <div>{company}</div>
          <div>{location}</div>
          {extra}
          <a href="https://www.seek.com.au/job/{job_id}?type=standard">View job</a>
        </td>
      </tr>
    </table>
    """


def _multi_job_email(rows: list[str]) -> str:
    return f"<html><body>{''.join(rows)}</body></html>"


def test_multiple_jobs_in_one_alert_become_separate_postings():
    html = _multi_job_email(
        [
            _job_row("111", "Graduate Software Engineer", "Acme Pty Ltd", "Melbourne VIC"),
            _job_row("222", "Junior Data Analyst", "DataCo", "Sydney NSW"),
            _job_row("333", "Graduate AI Engineer", "AI Labs", "Hobart TAS"),
        ]
    )
    postings = parse_seek_alert_email(html, message_id="msg-1")

    assert len(postings) == 3
    titles = {p.title for p in postings}
    assert titles == {"Graduate Software Engineer", "Junior Data Analyst", "Graduate AI Engineer"}
    for posting in postings:
        assert posting.source_type == JobSourceType.SEEK
        assert posting.source_metadata["gmail_message_id"] == "msg-1"
        assert posting.external_id is not None
        assert posting.source_url is not None and "seek.com.au/job/" in posting.source_url


def test_title_link_and_view_job_link_do_not_create_duplicate_postings():
    html = _multi_job_email([_job_row("999", "Graduate Developer", "Acme", "Melbourne VIC")])
    postings = parse_seek_alert_email(html, message_id="msg-2")
    assert len(postings) == 1


def test_company_location_extracted():
    html = _multi_job_email(
        [_job_row("444", "Graduate Data Scientist", "Analytics Co", "Brisbane QLD")]
    )
    postings = parse_seek_alert_email(html, message_id="msg-3")
    assert len(postings) == 1
    assert postings[0].company == "Analytics Co"
    assert postings[0].location == "Brisbane QLD"


def test_salary_extracted_when_present():
    html = _multi_job_email(
        [
            _job_row(
                "555",
                "Graduate Software Engineer",
                "Acme",
                "Melbourne VIC",
                extra="<div>$70,000 - $80,000</div>",
            )
        ]
    )
    postings = parse_seek_alert_email(html, message_id="msg-4")
    assert len(postings) == 1
    assert postings[0].source_metadata.get("salary_text") is not None


def test_malformed_html_does_not_raise():
    postings = parse_seek_alert_email("<html><body><div>not a job alert</div>", message_id="msg-5")
    assert postings == []


def test_empty_or_none_body_returns_empty_list():
    assert parse_seek_alert_email("", message_id="msg-6") == []
    assert parse_seek_alert_email("   ", message_id="msg-7") == []
