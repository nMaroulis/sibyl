"""Curated instructions for the implemented UI, retrieved by native agent tools.

Each specialist declares its own typed help tool. These records are documentation,
not a tool router, model prompt, or a replacement for live workspace evidence.
Keep them aligned with the corresponding page and user guide when features change.
"""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Guide:
    """One bounded answer with concrete steps, a destination and relevant limits."""

    title: str
    url: str
    steps: tuple[str, ...]
    notes: tuple[str, ...] = ()


def read_guide(guides: dict[str, Guide], topic: str) -> dict:
    """Return the chosen instructions and a short index for follow-up questions."""
    return {
        "kind": "page_help",
        "topic": topic,
        **asdict(guides[topic]),
        "topics": [{"id": key, "title": guide.title} for key, guide in guides.items()],
    }
