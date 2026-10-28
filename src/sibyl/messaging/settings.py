"""Encrypted Telegram connection profiles; other channels remain unavailable previews."""

import re
import time
from uuid import uuid4

from pydantic import Field, SecretStr, field_validator

from sibyl.messaging.catalog import CHANNELS
from sibyl.models import Request


class TelegramSettingsRequest(Request):
    """A token is write-only; omitting it preserves the encrypted saved credential."""

    bot_token: SecretStr | None = None
    allowed_user_id: int = Field(gt=0, le=2**52, strict=True)

    @field_validator("bot_token")
    @classmethod
    def valid_token(cls, value):
        if value is not None and not re.fullmatch(
            r"[0-9]{5,20}:[A-Za-z0-9_-]{20,200}", value.get_secret_value().strip()
        ):
            raise ValueError("Enter the bot token supplied by BotFather.")
        return value


class MessagingSettings:
    """Store a dedicated encrypted profile, never a token in public metadata or messages."""

    def __init__(self, store):
        self.store = store

    def profile(self) -> dict:
        """Decrypt only for the messaging worker and explicit connection checks."""
        return self.store.data_profile("messaging:telegram")

    def save(self, body: TelegramSettingsRequest) -> dict:
        """Save a disabled connection; enabling it is an explicit separate action."""
        old = self.profile()
        if old.get("enabled"):
            raise ValueError("Pause Telegram before changing its connection.")
        token = body.bot_token.get_secret_value().strip() if body.bot_token else old.get("bot_token", "")
        if not token:
            raise ValueError("Add a Telegram bot token first.")
        same = token == old.get("bot_token") and body.allowed_user_id == old.get("allowed_user_id")
        self.store.save_data_profile(
            "messaging:telegram",
            {
                **(old if same else {}),
                "bot_token": token,
                "allowed_user_id": body.allowed_user_id,
                "enabled": False,
                "revision": old.get("revision") if same else uuid4().hex,
                "configured_at": old.get("configured_at", time.time()) if same else time.time(),
            },
        )
        return self.public()

    def public(self) -> dict:
        """Expose actual configuration alongside disabled fields for future transports."""
        profile = self.profile()
        channels = []
        for channel in CHANNELS:
            available = channel["id"] == "telegram"
            channels.append(
                {
                    **channel,
                    "status": "available" if available else "unavailable",
                    "connected": bool(profile.get("verified")) if available else False,
                    **(
                        {
                            "enabled": profile.get("enabled", False),
                            "has_started": bool(profile.get("enabled_at")),
                            "has_token": bool(profile.get("bot_token")),
                            "allowed_user_id": profile.get("allowed_user_id"),
                            "bot_username": profile.get("bot_username"),
                            "last_checked_at": profile.get("last_checked_at"),
                            "last_poll_at": profile.get("last_poll_at"),
                            "error": profile.get("error"),
                            "next_attempt": profile.get("next_attempt"),
                            "setup_note": "Private chats only, restricted to your numeric user ID. Runs while Sibyl’s Python backend is open; no public webhook is required.",
                        }
                        if available
                        else {}
                    ),
                }
            )
        return {"channels": channels}
