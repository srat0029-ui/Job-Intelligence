"""Tests for app/ingestion/linkedin_email_parser.py - same inline-fixture
style as test_seek_email_parser.py."""

from __future__ import annotations

from app.domain.enums import JobSourceType
from app.ingestion.linkedin_email_parser import parse_linkedin_alert_email


def _job_row(job_id: str, title: str, company: str, location: str) -> str:
    return f"""
    <table>
      <tr>
        <td>
          <a href="https://www.linkedin.com/comm/jobs/view/{job_id}/">{title}</a>
          <div>{company}</div>
          <div>{location}</div>
          <a href="https://www.linkedin.com/comm/jobs/view/{job_id}/">Easy Apply</a>
        </td>
      </tr>
    </table>
    """


def _multi_job_email(rows: list[str]) -> str:
    return f"<html><body>{''.join(rows)}</body></html>"


def test_multiple_jobs_in_one_alert_become_separate_postings():
    html = _multi_job_email(
        [
            _job_row("1001", "Associate AI Engineer", "TechCo", "Melbourne, Victoria"),
            _job_row("1002", "Junior Software Engineer", "DevShop", "Sydney, NSW"),
        ]
    )
    postings = parse_linkedin_alert_email(html, message_id="li-msg-1")

    assert len(postings) == 2
    titles = {p.title for p in postings}
    assert titles == {"Associate AI Engineer", "Junior Software Engineer"}
    for posting in postings:
        assert posting.source_type == JobSourceType.LINKEDIN
        assert posting.source_metadata["gmail_message_id"] == "li-msg-1"


def test_title_and_apply_link_do_not_create_duplicate_postings():
    html = _multi_job_email([_job_row("2002", "Graduate Data Scientist", "Acme", "Brisbane, QLD")])
    postings = parse_linkedin_alert_email(html, message_id="li-msg-2")
    assert len(postings) == 1


def test_non_jobs_view_url_is_ignored():
    html = """
    <html><body>
      <a href="https://www.linkedin.com/feed/update/1234">Some unrelated post</a>
    </body></html>
    """
    assert parse_linkedin_alert_email(html, message_id="li-msg-3") == []


def test_malformed_html_does_not_raise():
    postings = parse_linkedin_alert_email("<div><span>broken", message_id="li-msg-4")
    assert postings == []


def test_empty_body_returns_empty_list():
    assert parse_linkedin_alert_email("", message_id="li-msg-5") == []


def test_nested_title_cell_with_middle_dot_company_location_is_split_correctly():
    """Calibrated against a real LinkedIn alert (Part 25's live sync): each
    job anchor wraps its own nested table with the title in one cell and
    "Company · Location" (joined by U+00B7 MIDDLE DOT) in the next. A flat
    `anchor.get_text()` would concatenate every nested cell with no
    separating space (e.g. "TitleCompany · Location") - the fix reads the
    anchor's own lines individually instead."""
    html = (
        "<html><body><table><tr><td>"
        '<a href="https://www.linkedin.com/comm/jobs/view/999/">'
        "<table><tr><td><table><tr><td>"
        "<div>AI &amp; Automation Engineer</div>"
        "</td></tr></table></td></tr>"
        "<tr><td>Scope (Aust) · Hawthorn East, VIC</td></tr>"
        "</table></a>"
        "</td></tr></table></body></html>"
    )
    postings = parse_linkedin_alert_email(html, message_id="li-msg-6")
    assert len(postings) == 1
    assert postings[0].title == "AI & Automation Engineer"
    assert postings[0].company == "Scope (Aust)"
    assert postings[0].location == "Hawthorn East, VIC"
