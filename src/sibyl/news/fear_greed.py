"""Attributed Alternative.me Bitcoin Fear & Greed observations with an offline demo."""

import json
import threading
from datetime import UTC, datetime, timedelta

import httpx

from sibyl.news.providers import read_public
from sibyl.news.repository import NewsRepository

SOURCE_URL = "https://alternative.me/crypto/fear-and-greed-index/"
LABELS = {"Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"}


class FearGreed:
    """Cache daily publisher values; failures retain explicit stale data, never invented values."""

    def __init__(self, repository: NewsRepository, transport: httpx.BaseTransport | None = None):
        self.repository, self.transport = repository, transport
        self._lock = threading.Lock()

    @staticmethod
    def _now():
        return datetime.now(UTC)

    def read(self, mode: str, *, refresh: bool = True) -> dict:
        """Read 30 dated observations, attribution, and a clear sample/fresh/stale status."""
        now = self._now()
        if mode == "demo":
            values = [
                42,
                39,
                41,
                44,
                47,
                45,
                48,
                51,
                50,
                49,
                46,
                48,
                52,
                54,
                55,
                53,
                50,
                48,
                46,
                44,
                42,
                43,
                45,
                48,
                49,
                51,
                52,
                54,
                55,
                56,
            ]
            history = [
                {
                    "value": value,
                    "classification": "Fear" if value < 45 else "Neutral" if value < 56 else "Greed",
                    "timestamp": (
                        now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=i)
                    ).isoformat(),
                }
                for i, value in enumerate(values)
            ]
            return self._response(history, "demo", now.isoformat(), None, mode)
        cached = self.repository.observation("fear_greed")
        elapsed = (
            (now - datetime.fromisoformat(cached["attempted_at"])).total_seconds() if cached else float("inf")
        )
        if refresh and elapsed >= 3600 and self._lock.acquire(blocking=False):
            try:
                cached = {**cached, "attempted_at": now.isoformat(), "error": None}
                try:
                    data = json.loads(
                        read_public(
                            "https://api.alternative.me/fng/", params={"limit": 30}, transport=self.transport
                        )
                    )
                    if (
                        not isinstance(data, dict)
                        or not isinstance(data.get("data"), list)
                        or not isinstance(data.get("metadata") or {}, dict)
                        or (data.get("metadata") or {}).get("error")
                    ):
                        raise ValueError("Invalid index response.")
                    history = []
                    for point in data["data"][:30]:
                        if not isinstance(point, dict) or isinstance(point.get("value"), bool):
                            raise ValueError("Invalid index observation.")
                        value = int(point["value"])
                        if value != float(point["value"]):
                            raise ValueError("Invalid index value.")
                        timestamp = datetime.fromtimestamp(int(point["timestamp"]), UTC)
                        if (
                            not 0 <= value <= 100
                            or point["value_classification"] not in LABELS
                            or timestamp > now + timedelta(minutes=10)
                        ):
                            raise ValueError("Invalid index observation.")
                        history.append(
                            {
                                "value": value,
                                "classification": point["value_classification"],
                                "timestamp": timestamp.isoformat(),
                            }
                        )
                    history.sort(key=lambda p: p["timestamp"], reverse=True)
                    if not history or len({p["timestamp"][:10] for p in history}) != len(history):
                        raise ValueError("Index history is empty or repeats dates.")
                    cached.update(history=history, fetched_at=now.isoformat())
                except (httpx.HTTPError, ValueError, TypeError, KeyError, OverflowError, OSError):
                    cached["error"] = "Alternative.me could not provide a valid index update."
                self.repository.save_observation("fear_greed", cached)
            finally:
                self._lock.release()
        history = cached.get("history", [])
        old = bool(
            history and (now - datetime.fromisoformat(history[0]["timestamp"])).total_seconds() > 172800
        )
        if (
            cached.get("fetched_at")
            and (now - datetime.fromisoformat(cached["fetched_at"])).total_seconds() > 7200
        ):
            old = True
        status = "unavailable" if not history else "stale" if cached.get("error") or old else "fresh"
        return self._response(history, status, cached.get("fetched_at"), cached.get("error"), mode)

    @staticmethod
    def _response(
        history: list[dict], status: str, fetched_at: str | None, error: str | None, mode: str
    ) -> dict:
        current = history[0] if history else None
        comparisons = {}
        if current:
            day = datetime.fromisoformat(current["timestamp"]).date()
            by_date = {datetime.fromisoformat(p["timestamp"]).date(): p for p in history}
            comparisons = {
                name: by_date.get(day - timedelta(days=days))
                for name, days in (("yesterday", 1), ("last_week", 7), ("last_month", 29))
            }
        return {
            "source": "Sibyl demo" if mode == "demo" else "Alternative.me",
            "source_url": SOURCE_URL,
            "mode": mode,
            "status": status,
            "current": current,
            "history": history,
            "comparisons": comparisons,
            "fetched_at": fetched_at,
            "error": error,
            "note": "Illustrative index values and dates."
            if mode == "demo"
            else "Alternative.me's Bitcoin-focused market index, separate from Sibyl's headline text polarity.",
        }
