"""One-off, read-only inspection of real SEEK alert emails already in the
connected Gmail inbox - dumps raw HTML + a structural summary (all `<a href>`
hrefs) to local scratch files so the SEEK parser can be fixed against the
real template instead of a synthetic fixture.

Never writes/labels/deletes anything in Gmail (GmailClient only exposes
search/get). Not part of the app - delete after use.

Usage:
    python scripts/inspect_seek_emails.py <output_dir>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import UTC, datetime, timedelta  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.ingestion.gmail_client import GmailClient  # noqa: E402
from app.ingestion.job_alert_email_source import (  # noqa: E402
    SEEK_SENDER_DOMAINS,
    _gmail_query,
)
from app.repositories.gmail_credential_repository import GmailCredentialRepository  # noqa: E402
from app.services.gmail_auth_service import GmailAuthService  # noqa: E402


def main() -> int:
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "seek_inspect")
    out_dir.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        cred_repo = GmailCredentialRepository()
        auth = GmailAuthService()
        credential = cred_repo.get(db)
        if credential is None:
            print("Gmail not connected.")
            return 1

        refresh_token = auth.decrypt(credential.refresh_token_encrypted)
        access_token, _ = auth.refresh_access_token(refresh_token)
        client = GmailClient(access_token=access_token)

        lookback = datetime.now(UTC) - timedelta(days=90)
        query = _gmail_query(SEEK_SENDER_DOMAINS, after=lookback)
        print(f"Query: {query}")
        message_ids = client.search_message_ids(query, max_results=50)
        print(f"Found {len(message_ids)} SEEK messages")

        for i, mid in enumerate(message_ids):
            msg = client.get_message(mid)
            html_len = len(msg.html_body or "")
            print(f"[{i}] {mid} from={msg.sender!r} subject={msg.subject!r} html_len={html_len}")
            if msg.html_body:
                (out_dir / f"seek_{i}_{mid}.html").write_text(msg.html_body, encoding="utf-8")

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
