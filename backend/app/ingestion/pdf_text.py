"""Plain-text extraction from an uploaded PDF.

Deliberately minimal: pypdf's text layer extraction, concatenated page by
page. No OCR (a scanned/image-only PDF will yield empty/near-empty text -
callers should treat that as "couldn't read this file" rather than
guessing). No layout/table reconstruction - CV extraction downstream is an
LLM call that tolerates reasonably messy plain text.
"""

from __future__ import annotations

import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class UnreadablePdfError(Exception):
    pass


def extract_text_from_pdf(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
    except PdfReadError as exc:
        raise UnreadablePdfError(f"Could not open PDF: {exc}") from exc

    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - a single bad page shouldn't fail the whole document
            continue

    text = "\n".join(pages).strip()
    if not text:
        raise UnreadablePdfError(
            "No extractable text found - this may be a scanned/image-only PDF, which isn't "
            "supported yet (would need OCR)."
        )
    return text
