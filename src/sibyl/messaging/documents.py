"""Bounded text attachments only; never read local paths or fetch remote file URLs."""

import re

MAX_BYTES = 64 * 1024


def document_bytes(text, filename):
    """Validate a backend-generated basename and a complete UTF-8 text attachment."""
    if not re.fullmatch(r"sibyl-(?:reply|briefing)-[a-z0-9-]{1,64}\.txt", filename):
        raise ValueError("Unsupported Sibyl text attachment name.")
    try:
        data = text.encode("utf-8")
    except UnicodeError:
        raise ValueError("The text attachment contains invalid Unicode.") from None
    if not data or len(data) > MAX_BYTES:
        raise ValueError(
            "Text attachments must contain 1–65,536 UTF-8 bytes. Read the complete answer or report in Sibyl."
        )
    return data


def add_document_columns(db, table):
    """Upgrade either owned outbox in place; older queued text remains ordinary text."""
    if table not in {"telegram_outbox", "message_delivery_parts"}:
        raise ValueError("Unsupported outbox.")
    columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
    for name, declaration in (("format", "TEXT NOT NULL DEFAULT 'text'"), ("filename", "TEXT")):
        if name not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
