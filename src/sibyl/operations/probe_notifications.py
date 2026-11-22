"""Optional content-free webhook delivery from the independent readiness watcher."""

from urllib.parse import urlsplit
from uuid import uuid4

import httpx


class WatchNotifications:
    """Send each observed outage/recovery transition once from the watching process."""

    def __init__(self, url, token="", *, transport=None):
        try:
            parts = urlsplit(url)
            if (
                parts.scheme != "https"
                or not parts.hostname
                or parts.username is not None
                or parts.query
                or parts.fragment
                or parts.port == 0
                or any(ord(char) <= 32 or ord(char) == 127 for char in url)
            ):
                raise ValueError
        except ValueError:
            raise ValueError(
                "Set SIBYL_PROBE_WEBHOOK to an HTTPS URL without credentials, query or fragment."
            ) from None
        if len(token) > 4096 or any(not 33 <= ord(char) <= 126 for char in token):
            raise ValueError("SIBYL_PROBE_WEBHOOK_TOKEN must be a single printable ASCII bearer token.")
        self.url, self.token, self.transport = url, token, transport

    def send(self, event, observation):
        """Return a safe delivery outcome without retrying an ambiguous POST."""
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        payload = {
            "schema": 1,
            "id": uuid4().hex,
            "service": "sibyl",
            "event": event,
            "status": observation["status"],
            "observed_at": observation["observed_at"],
        }
        try:
            with (
                httpx.Client(
                    timeout=3, trust_env=False, follow_redirects=False, transport=self.transport
                ) as client,
                client.stream("POST", self.url, headers=headers, json=payload) as response,
            ):
                outcome = "accepted" if response.is_success else "rejected"
        except (httpx.HTTPError, httpx.InvalidURL):
            outcome = "unconfirmed"
        return {"id": payload["id"], "event": event, "delivery": outcome}
