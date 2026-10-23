"""Telegram Bot API over HTTPX; no Telegram SDK, webhooks or arbitrary endpoints."""

import logging
import re

import httpx

from sibyl.messaging.base import MessagingClient


class _TokenFilter(logging.Filter):
    """Telegram puts credentials in paths; redact HTTP-client request logging too."""

    def filter(self, record):
        record.msg = re.sub(r"bot[0-9]{5,20}:[A-Za-z0-9_-]{20,200}", "bot[redacted]", record.getMessage())
        record.args = ()
        return True


class TelegramError(Exception):
    """A sanitized transport outcome; ambiguous writes must not retry automatically."""

    def __init__(self, message: str, *, retry_after: int = 0, ambiguous: bool = False):
        super().__init__(message)
        self.retry_after, self.ambiguous = retry_after, ambiguous


class TelegramClient(MessagingClient):
    """Use Telegram's fixed HTTPS origin and omit native errors containing token URLs."""

    def __init__(self, token: str, http: httpx.AsyncClient):
        self._token, self.http = token, http
        for name in ("httpx", "httpcore.http11", "httpcore.http2"):
            logger = logging.getLogger(name)
            if not any(isinstance(item, _TokenFilter) for item in logger.filters):
                logger.addFilter(_TokenFilter())

    async def call(self, method: str, payload: dict, *, write: bool = False):
        """Bound requests and normalize API rejections without reflecting tokens or raw text."""
        try:
            response = await self.http.post(
                f"https://api.telegram.org/bot{self._token}/{method}", json=payload, timeout=25
            )
        except httpx.HTTPError:
            raise TelegramError("Telegram did not confirm the request.", ambiguous=write) from None
        try:
            body = response.json()
        except ValueError:
            raise TelegramError("Telegram returned an unreadable response.", ambiguous=write) from None
        if not isinstance(body, dict):
            raise TelegramError("Telegram returned an invalid response.", ambiguous=write)
        if response.status_code == 429 or body.get("error_code") == 429:
            delay = body.get("parameters", {}).get("retry_after", 30)
            delay = min(3600, max(1, delay)) if type(delay) is int else 30
            raise TelegramError("Telegram rate limited this connection.", retry_after=delay)
        if response.status_code == 409:
            raise TelegramError(
                "Another bot poller or webhook is active. Stop it before enabling polling here."
            )
        if response.status_code in {401, 403}:
            raise TelegramError(
                "Telegram access was denied. Check the token and start a private chat with your bot."
            )
        if response.status_code >= 500:
            raise TelegramError("Telegram is temporarily unavailable.", ambiguous=write)
        if not response.is_success or body.get("ok") is not True:
            raise TelegramError(
                "Telegram rejected the request. Check this bot and its private-chat permissions."
            )
        if "result" not in body:
            raise TelegramError("Telegram did not confirm the result.", ambiguous=write)
        return body["result"]

    async def identity(self) -> dict:
        """Check the bot and refuse a webhook conflict without deleting provider configuration."""
        bot = await self.call("getMe", {})
        webhook = await self.call("getWebhookInfo", {})
        if (
            not isinstance(bot, dict)
            or not isinstance(webhook, dict)
            or bot.get("is_bot") is not True
            or type(bot.get("id")) is not int
        ):
            raise TelegramError("This token did not identify a Telegram bot.")
        if webhook.get("url"):
            raise TelegramError(
                "This bot already has a webhook. Remove it in your bot setup before using Sibyl polling."
            )
        return {"id": bot["id"], "username": bot.get("username", "")}

    async def receive(self, offset: int | None) -> list[dict]:
        """Long-poll only new ordinary messages; offset advances after durable local ingestion."""
        payload = {"timeout": 15, "limit": 20, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        result = await self.call("getUpdates", payload)
        if not isinstance(result, list) or len(result) > 20:
            raise TelegramError("Telegram returned invalid updates.")
        return result

    async def send(self, chat_id: int, text: str) -> int:
        """Send plain text, without previews, forwarding permissions or model-generated markup."""
        result = await self.call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "protect_content": True,
                "link_preview_options": {"is_disabled": True},
            },
            write=True,
        )
        if (
            not isinstance(result, dict)
            or type(result.get("message_id")) is not int
            or result["message_id"] <= 0
        ):
            raise TelegramError("Telegram did not confirm message delivery.", ambiguous=True)
        return result["message_id"]
