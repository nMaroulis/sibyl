"""Bounded document extraction; PDF parsing runs in a disposable child process."""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TEXT_CHARS = 1_000_000


def extract(filename: str, content: bytes) -> list[dict]:
    """Extract numbered pages from UTF-8 text/Markdown or a text-bearing PDF.

    Reject encrypted PDFs, image-only documents and excessive extraction rather
    than inventing text or silently cutting off a document. No URL is fetched.
    """
    if not content or len(content) > MAX_FILE_BYTES:
        raise ValueError("Choose a nonempty document up to 8 MiB.")
    suffix = Path(filename).suffix.lower()
    if suffix in {".md", ".markdown", ".txt"}:
        try:
            pages = [{"page": 1, "text": content.decode("utf-8-sig")}]
        except UnicodeDecodeError:
            raise ValueError("Text and Markdown documents must use UTF-8.") from None
    elif suffix == ".pdf":
        with tempfile.TemporaryDirectory(prefix="sibyl-pdf-") as directory:
            path = Path(directory) / "document.pdf"
            path.write_bytes(content)
            path.chmod(0o600)
            try:
                result = subprocess.run(
                    [sys.executable, str(Path(__file__).with_name("pdf_worker.py")), str(path)],
                    capture_output=True,
                    timeout=20,
                    check=False,
                )
                if result.returncode or len(result.stdout) > 6 * MAX_TEXT_CHARS:
                    raise ValueError(
                        "PDF extraction failed. Use an unencrypted text PDF with at most 100 pages."
                    )
                pages = json.loads(result.stdout)
            except (subprocess.TimeoutExpired, json.JSONDecodeError):
                raise ValueError("PDF extraction exceeded its limit. Try a smaller text PDF.") from None
    else:
        raise ValueError("Supported documents are PDF, UTF-8 text and Markdown.")
    total = sum(len(page["text"]) for page in pages)
    if total > MAX_TEXT_CHARS:
        raise ValueError("Extracted text exceeds one million characters. Split the document.")
    for page in pages:
        page["text"] = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", page["text"]).strip()
    if not any(page["text"] for page in pages):
        raise ValueError("No readable text was found. Scanned PDFs need OCR before import.")
    return pages


def passages(pages: list[dict]):
    """Yield overlapping, page-bounded exact text slices with stable passage numbers."""
    ordinal = 0
    for page in pages:
        text = page["text"]
        start = 0
        while start < len(text):
            end = min(start + 1600, len(text))
            if end < len(text):
                boundary = text.rfind(" ", start + 1100, end)
                if boundary > start:
                    end = boundary
            yield ordinal, page["page"], start, end, text[start:end]
            ordinal += 1
            if end == len(text):
                break
            start = end - 160
