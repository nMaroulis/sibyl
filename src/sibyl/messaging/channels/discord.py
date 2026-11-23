"""Discord bot DM polling through its HTTP API; no user token or Gateway required."""

import time
from datetime import datetime

from sibyl.messaging.channels.contracts import Batch, ChannelError, Envelope
from sibyl.messaging.channels.http import call

ORIGIN = "https://discord.com/api/v10"


class DiscordClient:
    """Only inspect/reply in the one checked bot-to-owner private channel."""

    chunk_units = 1900

    def __init__(self, profile, http):
        self.profile, self.http = profile, http

    async def api(self, method, path, **kwargs):
        return await call(
            self.http,
            method,
            ORIGIN + path,
            headers={"Authorization": "Bot " + self.profile["bot_token"]},
            **kwargs,
        )

    async def identity(self):
        user = await self.api("GET", "/users/@me")
        application = await self.api("GET", "/oauth2/applications/@me")
        if (
            not isinstance(user, dict)
            or user.get("bot") is not True
            or str(application.get("id")) != self.profile["application_id"]
        ):
            raise ChannelError("This credential did not identify the configured Discord bot application.")
        target = await self.api(
            "POST",
            "/users/@me/channels",
            payload={"recipient_id": self.profile["allowed_user_id"]},
            write=True,
        )
        if (
            target.get("type") != 1
            or not str(target.get("id", "")).isdigit()
            or [str(r.get("id")) for r in target.get("recipients", [])] != [self.profile["allowed_user_id"]]
        ):
            raise ChannelError("Discord did not confirm the configured private recipient.")
        return dict(bot_id=str(user["id"]), bot_username=user.get("username", ""), target=str(target["id"]))

    @staticmethod
    def initial_cursor(now=None):
        return str(max(0, int((time.time() if now is None else now) * 1000 - 1420070400000)) << 22)

    async def receive(self, cursor):
        rows = await self.api(
            "GET",
            f"/channels/{self.profile['target']}/messages",
            params={"after": cursor or self.initial_cursor(), "limit": 100},
        )
        if not isinstance(rows, list) or len(rows) > 100:
            raise ChannelError("Discord returned an invalid message page.")
        if len(rows) >= 100:
            raise ChannelError(
                "Discord's pending page is saturated. Pause and review its DM history before enabling a fresh receive boundary; no cursor was advanced."
            )
        valid = []
        for row in rows:
            identity = str(row.get("id", ""))
            if not identity.isdigit() or int(identity) <= int(cursor or "0"):
                continue
            valid.append(row)
        # Discord's after query returns the closest newer page, reverse chronological.
        valid.sort(key=lambda row: int(row["id"]))
        messages = []
        for row in valid:
            author = row.get("author") or {}
            if (
                author.get("bot")
                or row.get("webhook_id")
                or row.get("guild_id")
                or row.get("type", 0) != 0
                or row.get("message_snapshots")
            ):
                continue
            try:
                stamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")).timestamp()
            except (ValueError, KeyError, TypeError):
                continue
            messages.append(
                Envelope(
                    str(row["id"]),
                    str(author.get("id", "")),
                    str(row.get("channel_id", "")),
                    row.get("content", ""),
                    stamp,
                )
            )
        return Batch(messages, str(valid[-1]["id"]) if valid else cursor)

    async def acknowledge(self, batch):
        """REST reads need no additional provider acknowledgment."""

    async def send(self, target, text):
        if target != self.profile["target"]:
            raise ChannelError("The saved private recipient changed.")
        result = await self.api(
            "POST",
            f"/channels/{target}/messages",
            payload={"content": text, "allowed_mentions": {"parse": []}, "flags": 4},
            write=True,
        )
        if (
            not isinstance(result, dict)
            or not str(result.get("id", "")).isdigit()
            or str(result.get("channel_id")) != target
        ):
            raise ChannelError("Discord did not confirm message acceptance.", ambiguous=True)
        return str(result["id"])

    async def close(self):
        """The application owns the shared HTTP pool."""
