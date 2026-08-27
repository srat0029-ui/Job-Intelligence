"""Tests for app/ingestion/job_page_enrichment.py, focused on the LinkedIn
login-wall regression: every unauthenticated `linkedin.com/.../jobs/view/
<id>` fetch resolves to the same generic "Sign in / We're signing you in"
page, which was silently overwriting a real (if short) alert-email
description with useless chrome text for every LinkedIn posting enriched -
see the module's `_LOGIN_WALL_HINTS`/`_SITE_CHROME_HINTS` docstring.
"""

from __future__ import annotations

import httpx

from app.domain.enums import JobSourceType
from app.ingestion.job_page_enrichment import enrich_posting
from app.ingestion.job_source import RawJobPosting


def _posting(raw_description: str = "Graduate Software Engineer") -> RawJobPosting:
    return RawJobPosting(
        title="Graduate Software Engineer",
        company="Acme",
        location="Melbourne, VIC",
        source_url="https://www.linkedin.com/comm/jobs/view/123456/",
        source_type=JobSourceType.LINKEDIN,
        raw_description=raw_description,
    )


def _client_returning(html: str, *, status_code: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text=html)

    return httpx.Client(transport=httpx.MockTransport(handler))


# The real LinkedIn unauthenticated-redirect page's structure (not the
# actual scraped content, just the same real chrome phrases) - long enough
# to clear MIN_ENRICHED_TEXT_LENGTH on its own, which is exactly why this
# regressed silently: the page is "real" content, just not a job.
_LINKEDIN_LOGIN_WALL_HTML = """
<html><body>
<div>Sign in</div>
<div>LinkedIn</div>
<div>We're signing you in</div>
<div>Discover people, jobs, and more.</div>
<div>Sam Rathore</div>
<div>If you remain on this page, you'll be signed in. Learn more</div>
<footer>
<a>About</a><a>Accessibility</a><a>User Agreement</a><a>Privacy Policy</a>
<a>Cookie Policy</a><a>Copyright Policy</a><a>Brand Policy</a><a>Guest Controls</a>
<a>Community Guidelines</a>
</footer>
</body></html>
"""


def test_linkedin_login_wall_does_not_overwrite_the_alert_description():
    posting = _posting("Graduate Software Engineer at Acme, Melbourne VIC")
    client = _client_returning(_LINKEDIN_LOGIN_WALL_HTML)

    result = enrich_posting(posting, client=client)

    assert result.raw_description == "Graduate Software Engineer at Acme, Melbourne VIC"
    assert result.source_metadata.get("description_partial") is True


def test_site_chrome_heavy_page_is_blocked_even_without_a_login_phrase():
    """Defence in depth: a page dominated by footer/chrome links is blocked
    on chrome-density alone, even if none of the exact login-wall phrases
    match (e.g. a slightly different unauthenticated redirect page)."""
    html = """
    <html><body>
    <div>Some heading that is not a login prompt at all really</div>
    <footer>
    <a>Accessibility</a><a>User Agreement</a><a>Cookie Policy</a>
    <a>Copyright Policy</a><a>Guest Controls</a><a>Community Guidelines</a>
    </footer>
    </body></html>
    """
    posting = _posting("Graduate Software Engineer")
    client = _client_returning(html)

    result = enrich_posting(posting, client=client)

    assert result.raw_description == "Graduate Software Engineer"
    assert result.source_metadata.get("description_partial") is True


def test_real_looking_job_description_is_accepted():
    html = """
    <html><body>
    <h1>Graduate Software Engineer</h1>
    <p>We are looking for a graduate software engineer to join our Melbourne team.
    You will work on backend services using Python and FastAPI, collaborate with
    senior engineers, and contribute to production systems from day one. Requirements:
    a degree in computer science or related field, strong Python fundamentals, and a
    willingness to learn. This is a fantastic opportunity for a graduate looking to
    start their career in software engineering with a supportive, collaborative team
    that values mentorship and continuous learning.</p>
    </body></html>
    """
    posting = _posting("Graduate Software Engineer")
    client = _client_returning(html)

    result = enrich_posting(posting, client=client)

    assert "backend services using Python and FastAPI" in result.raw_description
    assert result.source_metadata.get("description_partial") is None
