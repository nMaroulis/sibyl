"""Fixed-origin JSON calls shared by reviewed provider clients; no write retries."""

import math

import httpx

from sibyl.messaging.channels.contracts import ChannelError


async def call(http, method, url, *, headers=None, payload=None, params=None, write=False):
    """Bound native responses and discard raw API errors, headers and credential diagnostics."""
    try:
        async with http.stream(
            method, url, headers=headers, json=payload, params=params, timeout=20
        ) as response:
            data = bytearray()
            async for chunk in response.aiter_bytes():
                if len(data) + len(chunk) > 256 * 1024:
                    raise ChannelError("The messaging response exceeded its size limit.", ambiguous=write)
                data.extend(chunk)
            if response.status_code == 429:
                try:
                    delay = float(response.headers.get("retry-after", "30"))
                    if not math.isfinite(delay):
                        raise ValueError
                except ValueError:
                    delay = 30
                raise ChannelError(
                    "The messaging provider rate limited this connection.",
                    retry_after=min(3600, max(1, delay)),
                )
            if response.status_code >= 500:
                raise ChannelError("The messaging provider is unavailable.", ambiguous=write)
            if not response.is_success:
                raise ChannelError(
                    "Messaging access was rejected. Check the saved identity, credentials and permissions."
                )
            import json

            try:
                body = json.loads(data)
            except (ValueError, UnicodeError):
                raise ChannelError(
                    "The messaging provider returned unreadable data.", ambiguous=write
                ) from None
            return body
    except httpx.HTTPError:
        raise ChannelError("The messaging request was not confirmed.", ambiguous=write) from None
