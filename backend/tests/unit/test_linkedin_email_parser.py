"""Tests for app/ingestion/linkedin_email_parser.py.

Fixtures reproduce the real LinkedIn alert DOM structure discovered against
the connected Gmail inbox (see the parser's module docstring): a job card is
wrapped by several `<a href=".../jobs/view/<id>/...">` anchors sharing one
job id - a logo image link (no text), the full card (title + "Company ·
Location" + zero or more badge/status lines), and a bare title link. Only
the structural shape is reproduced here - no real email content.
"""

from __future__ import annotations

from app.domain.enums import JobSourceType
from app.ingestion.linkedin_email_parser import parse_linkedin_alert_email
from app.services.location_service import GeographicEligibility, normalize_location


def _card(
    job_id: str,
    title: str,
    *,
    company_location: str | None = None,
    company: str | None = None,
    location: str | None = None,
    badges: tuple[str, ...] = (),
) -> str:
    """One real-shape LinkedIn job card: a logo (empty-text) anchor, the
    full card (title + company/location + badges, all inside one anchor -
    the real structure), and a bare title-only anchor - all three sharing
    the same job id, exactly like the real DOM."""
    href = f"https://www.linkedin.com/comm/jobs/view/{job_id}/"
    parts = [f"<div>{title}</div>"]
    if company_location is not None:
        parts.append(f"<div>{company_location}</div>")
    else:
        if company is not None:
            parts.append(f"<div>{company}</div>")
        if location is not None:
            parts.append(f"<div>{location}</div>")
    for badge in badges:
        parts.append(f"<div>{badge}</div>")

    logo = f'<a href="{href}"></a>'
    full_card = f'<a href="{href}">{"".join(parts)}</a>'
    bare_title = f'<a href="{href}">{title}</a>'
    return f"<table><tr><td>{logo}{full_card}{bare_title}</td></tr></table>"


def _digest_email(*cards: str) -> str:
    return f"<html><body>{''.join(cards)}</body></html>"


# --- 1. standard job card ---


def test_standard_job_card():
    html = _digest_email(
        _card("1001", "Graduate Data Scientist", company_location="Acme · Melbourne, VIC")
    )
    postings = parse_linkedin_alert_email(html, message_id="li-1")

    assert len(postings) == 1
    p = postings[0]
    assert p.title == "Graduate Data Scientist"
    assert p.company == "Acme"
    assert p.location == "Melbourne, VIC"
    assert p.source_type == JobSourceType.LINKEDIN
    assert p.external_id == "1001"


# --- 2. "Actively recruiting" inserted ---


def test_actively_recruiting_badge_does_not_become_location():
    html = _digest_email(
        _card(
            "1002",
            "Data Scientist",
            company_location="Whizdom · Sydney, NSW (Hybrid)",
            badges=("Actively recruiting",),
        )
    )
    postings = parse_linkedin_alert_email(html, message_id="li-2")

    assert len(postings) == 1
    assert postings[0].company == "Whizdom"
    assert postings[0].location == "Sydney, NSW (Hybrid)"
    assert "Actively recruiting" not in (postings[0].raw_description or "")


# --- 3. school alumni line inserted ---


def test_school_alumni_badge_does_not_become_location():
    html = _digest_email(
        _card(
            "1003",
            "Data Analyst | Power BI & Reporting",
            company_location="Versent · Melbourne, VIC (Hybrid)",
            badges=("41 school alumni",),
        )
    )
    postings = parse_linkedin_alert_email(html, message_id="li-3")

    assert len(postings) == 1
    assert postings[0].company == "Versent"
    assert postings[0].location == "Melbourne, VIC (Hybrid)"


def test_singular_alum_badge_phrasing_variant():
    """Real LinkedIn phrasing for a count of exactly one is singular ("1
    school alum"), not "1 school alumni" - this must not leak into the
    description as if it were real content."""
    html = _digest_email(
        _card(
            "1003c",
            "Junior Software Engineer",
            company_location="AE Capital · Melbourne, Victoria, Australia",
            badges=("1 school alum",),
        )
    )
    postings = parse_linkedin_alert_email(html, message_id="li-3c")
    assert postings[0].location == "Melbourne, Victoria, Australia"
    assert "alum" not in postings[0].raw_description.lower()


def test_alumni_badge_phrasing_variant():
    """The user's own example phrasing ("N <school> alumni work here")."""
    html = _digest_email(
        _card(
            "1003b",
            "Software Engineer",
            company_location="Acme · Melbourne, VIC",
            badges=("12 Monash University alumni work here",),
        )
    )
    postings = parse_linkedin_alert_email(html, message_id="li-3b")
    assert postings[0].location == "Melbourne, VIC"


# --- 4. promoted/status badge ---


def test_promoted_and_early_applicant_badges_do_not_become_location():
    html = _digest_email(
        _card(
            "1004",
            "Junior Software Engineer",
            company_location="DevShop · Brisbane, QLD",
            badges=("Promoted", "Be an early applicant"),
        )
    )
    postings = parse_linkedin_alert_email(html, message_id="li-4")

    assert len(postings) == 1
    assert postings[0].company == "DevShop"
    assert postings[0].location == "Brisbane, QLD"


def test_applicant_count_badge_does_not_become_location():
    html = _digest_email(
        _card(
            "1004b",
            "Analyst",
            company_location="Acme · Perth, WA",
            badges=("Over 100 applicants",),
        )
    )
    postings = parse_linkedin_alert_email(html, message_id="li-4b")
    assert postings[0].location == "Perth, WA"


def test_connections_badge_does_not_become_location():
    html = _digest_email(
        _card(
            "1004c",
            "Insights Analyst",
            company_location="LMG · Melbourne, VIC (Hybrid)",
            badges=("1 connection",),
        )
    )
    postings = parse_linkedin_alert_email(html, message_id="li-4c")
    assert postings[0].location == "Melbourne, VIC (Hybrid)"


# --- 5/6/7. hybrid Melbourne / Sydney / Australian Remote ---


def test_hybrid_melbourne_job_normalises_eligible():
    html = _digest_email(
        _card("1005", "Software Engineer", company_location="carsales · Melbourne, VIC (Hybrid)")
    )
    posting = parse_linkedin_alert_email(html, message_id="li-5")[0]
    assert posting.location == "Melbourne, VIC (Hybrid)"
    result = normalize_location(location=posting.location)
    assert result.eligibility == GeographicEligibility.ELIGIBLE


def test_sydney_job_normalises_eligible():
    html = _digest_email(
        _card("1006", "Data Scientist", company_location="Woolworths Group · Surry Hills, NSW")
    )
    posting = parse_linkedin_alert_email(html, message_id="li-6")[0]
    result = normalize_location(location=posting.location)
    assert result.eligibility == GeographicEligibility.ELIGIBLE


def test_australian_remote_job_normalises_eligible():
    html = _digest_email(
        _card(
            "1007",
            "Forward Deployed Engineer",
            company_location="ElevenLabs · Australia (Remote)",
        )
    )
    posting = parse_linkedin_alert_email(html, message_id="li-7")[0]
    result = normalize_location(location=posting.location)
    assert result.eligibility == GeographicEligibility.ELIGIBLE


# --- 8. overseas job still excluded ---


def test_overseas_job_normalises_ineligible():
    html = _digest_email(
        _card(
            "1008",
            "Backend Software Engineer",
            company_location="Palantir · London, United Kingdom",
        )
    )
    posting = parse_linkedin_alert_email(html, message_id="li-8")[0]
    assert posting.location == "London, United Kingdom"
    result = normalize_location(location=posting.location)
    assert result.eligibility == GeographicEligibility.INELIGIBLE


# --- 9. generic Remote remains unconfirmed ---


def test_generic_remote_with_no_country_stays_unconfirmed():
    html = _digest_email(_card("1009", "Data Engineer", company_location="Acme · Remote"))
    posting = parse_linkedin_alert_email(html, message_id="li-9")[0]
    result = normalize_location(location=posting.location)
    assert result.eligibility == GeographicEligibility.LOCATION_UNCONFIRMED


# --- fail-closed: no separator line and the second line isn't a location ---


def test_no_location_line_is_left_unset_not_guessed():
    """Fail closed (module docstring): if nothing after the title looks
    like a location, `location` must stay None rather than picking a badge
    or other non-location line."""
    html = _digest_email(
        _card("1009b", "Data Engineer", company="Acme", badges=("Actively recruiting",))
    )
    posting = parse_linkedin_alert_email(html, message_id="li-9b")[0]
    assert posting.company == "Acme"
    assert posting.location is None


def test_company_and_location_on_separate_lines_no_middle_dot():
    """The other real template variant: company and location as separate
    lines with no "·" separator at all."""
    html = _digest_email(
        _card("1009c", "Full Stack Engineer", company="Technology CII", location="Carlton, VIC")
    )
    posting = parse_linkedin_alert_email(html, message_id="li-9c")[0]
    assert posting.company == "Technology CII"
    assert posting.location == "Carlton, VIC"


# --- 10/11. multiple cards isolated, no field bleed ---


def test_multiple_cards_stay_isolated_no_field_bleed():
    html = _digest_email(
        _card("2001", "Job A", company_location="Company A · Melbourne, VIC"),
        _card(
            "2002",
            "Job B",
            company_location="Company B · Sydney, NSW",
            badges=("Actively recruiting",),
        ),
    )
    postings = parse_linkedin_alert_email(html, message_id="li-10")

    assert len(postings) == 2
    by_title = {p.title: p for p in postings}
    assert by_title["Job A"].company == "Company A"
    assert by_title["Job A"].location == "Melbourne, VIC"
    assert by_title["Job B"].company == "Company B"
    assert by_title["Job B"].location == "Sydney, NSW"


# --- 12. duplicate links for one job remain one posting ---


def test_duplicate_links_for_one_job_remain_one_posting():
    # _card() itself already emits 3 anchors (logo/full-card/bare-title)
    # sharing one job id - this asserts that structural duplication never
    # produces more than one posting.
    html = _digest_email(
        _card("3001", "Graduate Developer", company_location="Acme · Melbourne, VIC")
    )
    postings = parse_linkedin_alert_email(html, message_id="li-11")
    assert len(postings) == 1


def test_title_and_apply_link_do_not_create_duplicate_postings():
    html = (
        "<table><tr><td>"
        '<a href="https://www.linkedin.com/comm/jobs/view/2002/">Graduate Data Scientist</a>'
        "<div>Acme</div><div>Brisbane, QLD</div>"
        '<a href="https://www.linkedin.com/comm/jobs/view/2002/">Easy Apply</a>'
        "</td></tr></table>"
    )
    postings = parse_linkedin_alert_email(html, message_id="li-msg-2")
    assert len(postings) == 1


# --- existing coverage retained ---


def test_multiple_jobs_in_one_alert_become_separate_postings():
    html = _digest_email(
        _card("1101", "Associate AI Engineer", company_location="TechCo · Melbourne, Victoria"),
        _card("1102", "Junior Software Engineer", company_location="DevShop · Sydney, NSW"),
    )
    postings = parse_linkedin_alert_email(html, message_id="li-msg-1")

    assert len(postings) == 2
    titles = {p.title for p in postings}
    assert titles == {"Associate AI Engineer", "Junior Software Engineer"}
    for posting in postings:
        assert posting.source_type == JobSourceType.LINKEDIN
        assert posting.source_metadata["gmail_message_id"] == "li-msg-1"


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
    """Calibrated against a real LinkedIn alert: each job anchor wraps its
    own nested table with the title in one cell and "Company · Location"
    (joined by U+00B7 MIDDLE DOT) in the next. A flat `anchor.get_text()`
    would concatenate every nested cell with no separating space (e.g.
    "TitleCompany · Location") - the fix reads the anchor's own lines
    individually instead."""
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
