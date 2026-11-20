"""Bounded local AI drafts and exact-content observation for uncertain write recovery."""

from hashlib import sha256


class ResearchNotes:
    """Reuse document deduplication; finding a note never creates or replays one."""

    def __init__(self, library):
        self.library = library

    @staticmethod
    def content(title, text):
        if (
            not isinstance(title, str)
            or not isinstance(text, str)
            or not 1 <= len(title) <= 120
            or not 1 <= len(text) <= 8000
            or not title.strip()
            or not text.strip()
            or any(ord(char) < 32 for char in title)
        ):
            raise ValueError("Use a plain non-empty title and bounded research note.")
        return (title.strip() + "\n\n" + text.strip()).encode("utf-8")

    @staticmethod
    def public(document, *, observed=False):
        return dict(
            document_id=document["id"],
            title=document["title"],
            fingerprint=document["fingerprint"],
            duplicate=True if observed else document["duplicate"],
            url="/research?tab=library",
            note="Exact matching local content observed; the original tool return was not retained."
            if observed
            else "User-approved local AI draft, not independent factual evidence.",
        )

    def save(self, title, text):
        content = self.content(title, text)
        digest = sha256(content).hexdigest()
        document = self.library.import_document(
            "sibyl-note-" + digest[:16] + ".txt", content, title=title, publisher="Sibyl · AI research draft"
        )
        return self.public(document)

    def observed(self, title, text):
        digest = sha256(self.content(title, text)).hexdigest()
        with self.library.db() as db:
            row = db.execute(
                "SELECT id FROM documents WHERE kind='document' AND fingerprint=?", (digest,)
            ).fetchone()
        if row is None:
            return None
        return self.public(self.library.document(row[0]), observed=True)
