"""Slack Socket Mode with post-commit envelope acknowledgments and bound DMs."""

import json
from urllib.parse import urlsplit

import aiohttp

from sibyl.messaging.channels.contracts import Batch, ChannelError, Envelope
from sibyl.messaging.channels.http import call


class SlackClient:
    """Use bot Web API and app-token sockets, never workspace channels or arbitrary URLs."""

    chunk_units = 3500

    def __init__(self, profile, http):
        self.profile, self.http = profile, http
        self.session, self.socket = None, None

    async def api(self, method, *, app=False, payload=None, write=False):
        token = self.profile["app_token" if app else "bot_token"]
        result = await call(
            self.http,
            "POST",
            "https://slack.com/api/" + method,
            headers={"Authorization": "Bearer " + token},
            payload=payload or {},
            write=write,
        )
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise ChannelError("Slack rejected the request. Check the tokens and required scopes.")
        return result

    async def identity(self):
        bot = await self.api("auth.test")
        # Check the app-level credential separately; do not expose or persist its ticket URL.
        await self.api("apps.connections.open", app=True)
        opened = await self.api(
            "conversations.open",
            payload={"users": self.profile["allowed_user_id"], "return_im": True},
            write=True,
        )
        channel = opened.get("channel") or {}
        if not bot.get("bot_id") or not bot.get("team_id") or not str(channel.get("id", "")).startswith("D"):
            raise ChannelError("Slack did not identify this bot and its private conversation.")
        return dict(
            bot_id=bot["user_id"],
            bot_username=bot.get("user", ""),
            team_id=bot["team_id"],
            target=channel["id"],
        )

    async def _connect(self):
        result = await self.api("apps.connections.open", app=True)
        parsed = urlsplit(result.get("url", ""))
        if (
            parsed.scheme != "wss"
            or parsed.hostname not in {"wss.slack.com", "wss-primary.slack.com", "wss-backup.slack.com"}
            or parsed.username
            or parsed.password
            or parsed.port not in {None, 443}
        ):
            raise ChannelError("Slack returned an unsupported socket origin.")
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, sock_connect=10))
        self.socket = await self.session.ws_connect(
            result["url"], heartbeat=15, max_msg_size=65536, autoping=True
        )

    async def receive(self, cursor):
        if not self.socket or self.socket.closed:
            await self.close()
            await self._connect()
        try:
            frame = await self.socket.receive(timeout=1)
        except TimeoutError:
            return Batch(cursor=cursor)
        if frame.type != aiohttp.WSMsgType.TEXT:
            await self.close()
            raise ChannelError("Slack socket disconnected; reconnecting may leave an event-history gap.")
        try:
            body = json.loads(frame.data)
        except (ValueError, TypeError):
            raise ChannelError("Slack returned an unreadable socket event.") from None
        if body.get("type") == "disconnect":
            await self.close()
            return Batch(cursor=cursor)
        envelope = body.get("envelope_id")
        if not isinstance(envelope, str) or len(envelope) > 200:
            return Batch(cursor=cursor)
        payload = body.get("payload") or {}
        event = payload.get("event") or {}
        messages = []
        if (
            body.get("type") == "events_api"
            and payload.get("team_id") == self.profile["team_id"]
            and event.get("type") == "message"
            and event.get("channel_type") == "im"
            and not event.get("subtype")
            and not event.get("bot_id")
        ):
            try:
                stamp = float(event["ts"])
                messages = [
                    Envelope(
                        str(payload["event_id"]),
                        str(event.get("user", "")),
                        str(event.get("channel", "")),
                        event.get("text", ""),
                        stamp,
                    )
                ]
            except (ValueError, KeyError, TypeError):
                pass
        return Batch(messages, cursor, envelope)

    async def acknowledge(self, batch):
        """Call only after every authorized event has a durable local receipt."""
        if batch.acknowledgement:
            try:
                await self.socket.send_json({"envelope_id": batch.acknowledgement})
            except (aiohttp.ClientError, ConnectionError, AttributeError):
                await self.close()
                raise ChannelError("Slack did not confirm the event acknowledgment.") from None

    async def send(self, target, text):
        if target != self.profile["target"]:
            raise ChannelError("The saved private recipient changed.")
        result = await self.api(
            "chat.postMessage",
            payload={
                "channel": target,
                "text": text,
                "mrkdwn": False,
                "parse": "none",
                "link_names": False,
                "unfurl_links": False,
                "unfurl_media": False,
            },
            write=True,
        )
        if result.get("channel") != target or not result.get("ts"):
            raise ChannelError("Slack did not confirm message acceptance.", ambiguous=True)
        return str(result["ts"])

    async def close(self):
        """Discard expiring socket tickets and release owned resources."""
        if self.socket:
            await self.socket.close()
        if self.session:
            await self.session.close()
        self.socket, self.session = None, None
