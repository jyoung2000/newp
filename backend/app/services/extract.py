"""Plain-text extraction from uploaded documents (for the LLM resume parse).

This is document-to-text conversion for the user's own files — it is not,
and must never become, an OCR path aimed at challenges (CAPTCHA_POLICY.md).
"""
from __future__ import annotations

import io

from app.logging_conf import get_logger

log = get_logger(__name__)

TEXT_TYPES = {"text/plain", "text/markdown"}
PDF_TYPES = {"application/pdf"}
DOCX_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def extract_text(data: bytes, content_type: str, filename: str) -> str | None:
    name = filename.lower()
    try:
        if content_type in TEXT_TYPES or name.endswith((".txt", ".md")):
            return data.decode("utf-8", errors="replace")
        if content_type in PDF_TYPES or name.endswith(".pdf"):
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            pages = [page.extract_text() or "" for page in reader.pages[:30]]
            text = "\n".join(pages).strip()
            return text or None
        if content_type in DOCX_TYPES or name.endswith(".docx"):
            import docx

            document = docx.Document(io.BytesIO(data))
            return "\n".join(p.text for p in document.paragraphs).strip() or None
    except Exception as exc:
        log.warning("extract.failed", filename=filename, error=str(exc))
        return None
    return None
