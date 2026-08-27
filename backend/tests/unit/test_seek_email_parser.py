"""Tests for app/ingestion/seek_email_parser.py.

Fixtures mirror the real SEEK alert structure discovered against the
connected Gmail inbox (see the parser's module docstring): the entire job
card - title, company, badges, location, salary, highlight bullets - is
wrapped in a single `<a href="https://email.s.seek.com.au/...">` opaque
ESP tracking link, never a direct `seek.com.au/job/<id>` URL. Only the
structural shape (single-anchor-per-card, tracking-domain hrefs, the mix of
job cards and single-line nav/CTA links) is reproduced here - no real
email content.

A handful of tests still use the older direct-URL shape (anchor wraps only
the title, company/location as sibling elements) to cover the parser's
backward-compatible fallback path - see `_direct_link_lines` in the parser.
"""

from __future__ import annotations

from app.domain.enums import JobSourceType
from app.ingestion.seek_email_parser import parse_seek_alert_email


def _resolver(mapping: dict[str, str | None]):
    calls: list[str] = []

    def resolve(url: str) -> str | None:
        calls.append(url)
        return mapping.get(url)

    resolve.calls = calls  # type: ignore[attr-defined]
    return resolve


def _tracked_card(
    href: str,
    title: str,
    company: str,
    location: str | None = None,
    *,
    badges: tuple[str, ...] = (),
    salary: str | None = None,
    bullets: tuple[str, ...] = (),
) -> str:
    """One real-shape SEEK job card: everything inside a single anchor."""
    parts = [f"<div>{title}</div>", f"<div>{company}</div>"]
    parts += [f"<div>{b}</div>" for b in badges]
    if location:
        parts.append(f"<div>{location}</div>")
    if salary:
        parts.append(f"<div>{salary}</div>")
    parts += [f"<div>{b}</div>" for b in bullets]
    return f'<a href="{href}">{"".join(parts)}</a>'


def _nav_link(href: str, text: str) -> str:
    return f'<a href="{href}">{text}</a>'


def _digest_email(*blocks: str) -> str:
    return f"<html><body><table><tr><td>{''.join(blocks)}</td></tr></table></body></html>"


# --- 1. one SEEK alert with one tracked job ---


def test_one_tracked_job_is_extracted():
    href = "https://email.s.seek.com.au/uni/ss/c/u001.abc/4th/msg/h1/h001.xyz"
    html = _digest_email(
        _tracked_card(href, "Graduate Software Engineer", "Acme Pty Ltd", "Melbourne VIC")
    )
    resolve = _resolver({href: "https://au.seek.com/job/111111?token=abc&tracking=x"})

    postings = parse_seek_alert_email(html, message_id="msg-1", resolve_link=resolve)

    assert len(postings) == 1
    posting = postings[0]
    assert posting.title == "Graduate Software Engineer"
    assert posting.company == "Acme Pty Ltd"
    assert posting.location == "Melbourne VIC"
    assert posting.source_type == JobSourceType.SEEK
    assert posting.external_id == "111111"
    assert posting.source_metadata["gmail_message_id"] == "msg-1"
    assert posting.source_metadata["seek_tracking_url"] == href


# --- 2. one alert with multiple jobs ---


def test_multiple_jobs_in_one_alert_become_separate_postings():
    href1 = "https://email.s.seek.com.au/uni/ss/c/u001.aaa/4th/m/h1/h001.a"
    href2 = "https://email.s.seek.com.au/uni/ss/c/u001.bbb/4th/m/h3/h001.b"
    href3 = "https://email.s.seek.com.au/uni/ss/c/u001.ccc/4th/m/h5/h001.c"
    html = _digest_email(
        _tracked_card(href1, "Graduate Software Engineer", "Acme Pty Ltd", "Melbourne VIC"),
        _tracked_card(href2, "Junior Data Analyst", "DataCo", "Sydney NSW"),
        _tracked_card(href3, "Graduate AI Engineer", "AI Labs", "Hobart TAS"),
    )
    resolve = _resolver(
        {
            href1: "https://au.seek.com/job/111111?token=a",
            href2: "https://au.seek.com/job/222222?token=b",
            href3: "https://au.seek.com/job/333333?token=c",
        }
    )

    postings = parse_seek_alert_email(html, message_id="msg-2", resolve_link=resolve)

    assert len(postings) == 3
    titles = {p.title for p in postings}
    assert titles == {"Graduate Software Engineer", "Junior Data Analyst", "Graduate AI Engineer"}
    assert {p.external_id for p in postings} == {"111111", "222222", "333333"}


# --- 3. duplicate title + View Job links ---


def test_duplicate_link_to_same_tracked_job_is_not_double_counted():
    href = "https://email.s.seek.com.au/uni/ss/c/u001.dup/4th/m/h1/h001.d"
    html = _digest_email(
        _tracked_card(href, "Graduate Developer", "Acme", "Melbourne VIC"),
        _nav_link(href, "View job"),
    )
    resolve = _resolver({href: "https://au.seek.com/job/444444?token=d"})

    postings = parse_seek_alert_email(html, message_id="msg-3", resolve_link=resolve)

    assert len(postings) == 1
    # The shared href must only ever be resolved once.
    assert resolve.calls.count(href) == 1


def test_direct_url_title_link_and_view_job_link_do_not_duplicate():
    """Backward-compatible direct-URL shape (anchor wraps only the title)."""
    html = (
        "<table><tr><td>"
        '<a href="https://www.seek.com.au/job/999?type=standard">Graduate Developer</a>'
        "<div>Acme</div><div>Melbourne VIC</div>"
        '<a href="https://www.seek.com.au/job/999?type=standard">View job</a>'
        "</td></tr></table>"
    )
    postings = parse_seek_alert_email(html, message_id="msg-3b")
    assert len(postings) == 1


# --- 4. non-job tracking links ignored ---


def test_nav_and_feedback_links_are_ignored_without_resolving():
    href_job = "https://email.s.seek.com.au/uni/ss/c/u001.job/4th/m/h1/h001.j"
    html = _digest_email(
        _nav_link(
            "https://email.s.seek.com.au/uni/ss/c/u001.img/4th/m/h0/h001.i", ""
        ),  # empty-text image link
        _tracked_card(href_job, "Graduate Developer", "Acme", "Melbourne VIC"),
        _nav_link(
            "https://email.s.seek.com.au/uni/ss/c/u001.vmj/4th/m/h25/h001.v", "View more jobs"
        ),
        _nav_link("https://email.s.seek.com.au/ss/c/u001.yes/4th/m/h29/h001.y", "Yes"),
        _nav_link("https://email.s.seek.com.au/ss/c/u001.no/4th/m/h31/h001.n", "No"),
        _nav_link("https://email.s.seek.com.au/ss/c/u001.unsub/4th/m", "Unsubscribe"),
    )
    resolve = _resolver({href_job: "https://au.seek.com/job/555555?token=e"})

    postings = parse_seek_alert_email(html, message_id="msg-4", resolve_link=resolve)

    assert len(postings) == 1
    assert postings[0].external_id == "555555"
    # None of the single-line nav/CTA links should ever hit the resolver.
    assert resolve.calls == [href_job]


def test_link_that_resolves_to_a_non_job_page_is_dropped():
    """A structurally job-card-like anchor (>= 2 lines) whose tracking link
    turns out to redirect somewhere that isn't a job page (e.g. a logo
    click landing on the SEEK homepage) must not become a posting."""
    href = "https://email.s.seek.com.au/uni/ss/c/u001.logo/4th/m/h0/h001.l"
    html = _digest_email(_tracked_card(href, "Acme Pty Ltd", "Sponsored"))
    resolve = _resolver({href: "https://au.seek.com/?tracking=PAC-JobRecs-anz-1-logo"})

    postings = parse_seek_alert_email(html, message_id="msg-5", resolve_link=resolve)

    assert postings == []


# --- 5. canonical SEEK URL extraction ---


def test_canonical_url_is_reconstructed_from_the_resolved_job_id():
    href = "https://email.s.seek.com.au/uni/ss/c/u001.can/4th/m/h1/h001.c"
    html = _digest_email(_tracked_card(href, "Graduate Developer", "Acme", "Melbourne VIC"))
    resolve = _resolver(
        {href: "https://au.seek.com/job/666666?token=1~abc-def&tracking=PAC-JobRecs-anz-1"}
    )

    postings = parse_seek_alert_email(html, message_id="msg-6", resolve_link=resolve)

    assert len(postings) == 1
    assert postings[0].source_url == "https://www.seek.com.au/job/666666"


# --- 6. malformed tracking URL ---


def test_malformed_href_is_ignored_without_crashing():
    html = _digest_email(
        '<a href="ht tp://broken url with spaces">Graduate Developer<div>Acme</div></a>',
        '<a href="javascript:void(0)">Graduate Developer<div>Acme</div></a>',
    )
    resolve = _resolver({})

    postings = parse_seek_alert_email(html, message_id="msg-7", resolve_link=resolve)

    assert postings == []
    assert resolve.calls == []


# --- 7. unresolved redirect fallback ---


def test_unresolved_redirect_still_yields_a_degraded_posting():
    href = "https://email.s.seek.com.au/uni/ss/c/u001.timeout/4th/m/h1/h001.t"
    html = _digest_email(_tracked_card(href, "Graduate Developer", "Acme", "Melbourne VIC"))
    resolve = _resolver({href: None})  # simulates a timeout/network failure

    postings = parse_seek_alert_email(html, message_id="msg-8", resolve_link=resolve)

    assert len(postings) == 1
    posting = postings[0]
    assert posting.title == "Graduate Developer"
    assert posting.source_url == href
    assert posting.external_id is None
    assert posting.source_metadata["seek_resolution_failed"] is True


def test_no_resolver_configured_yields_no_tracked_job_postings():
    """Without a resolver there is no way to recover the destination job
    id from an opaque tracking link - the parser must not fabricate one."""
    href = "https://email.s.seek.com.au/uni/ss/c/u001.abc/4th/m/h1/h001.x"
    html = _digest_email(_tracked_card(href, "Graduate Developer", "Acme", "Melbourne VIC"))

    postings = parse_seek_alert_email(html, message_id="msg-9")

    assert postings == []


# --- 8. duplicate same job across two emails ---


def test_same_job_across_two_emails_carries_matching_identifiers():
    """The parser has no cross-email state (each email gets its own
    personalised tracking tokens) - cross-email dedup happens downstream via
    `deduplication_service` matching on (source, external_id). What this
    parser must guarantee is that both emails resolve to the *same*
    external_id/canonical URL so that downstream match can happen."""
    href_a = "https://email.s.seek.com.au/uni/ss/c/u001.emailA/4th/m/h1/h001.a"
    href_b = "https://email.s.seek.com.au/uni/ss/c/u001.emailB/4th/m/h1/h001.b"
    resolve = _resolver(
        {
            href_a: "https://au.seek.com/job/777777?token=fromA",
            href_b: "https://au.seek.com/job/777777?token=fromB",
        }
    )

    postings_a = parse_seek_alert_email(
        _digest_email(_tracked_card(href_a, "Graduate Developer", "Acme", "Melbourne VIC")),
        message_id="msg-10a",
        resolve_link=resolve,
    )
    postings_b = parse_seek_alert_email(
        _digest_email(_tracked_card(href_b, "Graduate Developer", "Acme", "Melbourne VIC")),
        message_id="msg-10b",
        resolve_link=resolve,
    )

    assert len(postings_a) == 1 and len(postings_b) == 1
    assert postings_a[0].external_id == postings_b[0].external_id == "777777"
    assert postings_a[0].source_url == postings_b[0].source_url


# --- 10. title/company/location remain scoped to the correct card ---


def test_fields_do_not_bleed_between_adjacent_job_cards():
    href_a = "https://email.s.seek.com.au/uni/ss/c/u001.jobA/4th/m/h1/h001.a"
    href_b = "https://email.s.seek.com.au/uni/ss/c/u001.jobB/4th/m/h3/h001.b"
    html = _digest_email(
        _tracked_card(href_a, "Job A", "Company A", "Melbourne VIC"),
        _tracked_card(href_b, "Job B", "Company B", "Sydney NSW"),
    )
    resolve = _resolver(
        {
            href_a: "https://au.seek.com/job/888881?token=a",
            href_b: "https://au.seek.com/job/888882?token=b",
        }
    )

    postings = parse_seek_alert_email(html, message_id="msg-11", resolve_link=resolve)

    assert len(postings) == 2
    by_title = {p.title: p for p in postings}
    assert by_title["Job A"].company == "Company A"
    assert by_title["Job A"].location == "Melbourne VIC"
    assert by_title["Job B"].company == "Company B"
    assert by_title["Job B"].location == "Sydney NSW"


# --- field extraction detail: badges/salary/bullets don't corrupt company/location ---


def test_badge_and_salary_lines_do_not_displace_location():
    href = "https://email.s.seek.com.au/uni/ss/c/u001.badge/4th/m/h1/h001.b"
    html = _digest_email(
        _tracked_card(
            href,
            "Junior Software Engineer",
            "AE Capital",
            "South Yarra, Melbourne VIC (Hybrid)",
            badges=("Strong applicant",),
            salary="$90,000 – $110,000 per year",
            bullets=("Join a growing team",),
        )
    )
    resolve = _resolver({href: "https://au.seek.com/job/999999?token=g"})

    postings = parse_seek_alert_email(html, message_id="msg-12", resolve_link=resolve)

    assert len(postings) == 1
    posting = postings[0]
    assert posting.company == "AE Capital"
    assert posting.location == "South Yarra, Melbourne VIC (Hybrid)"
    assert posting.source_metadata["salary_text"] == "$90,000 – $110,000 per year"
    assert "Join a growing team" in posting.raw_description
    assert "Strong applicant" not in posting.raw_description


# --- existing coverage retained ---


def test_malformed_html_does_not_raise():
    postings = parse_seek_alert_email("<html><body><div>not a job alert</div>", message_id="msg-13")
    assert postings == []


def test_empty_or_none_body_returns_empty_list():
    assert parse_seek_alert_email("", message_id="msg-14") == []
    assert parse_seek_alert_email("   ", message_id="msg-15") == []
