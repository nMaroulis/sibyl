"""A checked private target is an identity binding, never arbitrary send parameters."""

from typing import Literal

from pydantic import Field

from sibyl.models import Request

PrivateChannel = Literal["discord", "slack", "signal", "whatsapp", "email"]
NotificationChannel = Literal["telegram", "discord", "slack", "signal", "whatsapp", "email"]


class PrivateTarget(Request):
    """Bind consent to one checked connection revision and its exact private recipient."""

    channel: PrivateChannel
    revision: str = Field(pattern=r"^[a-f0-9]{32}$")
    bot_id: str = Field(min_length=1, max_length=200)
    recipient_id: str = Field(min_length=1, max_length=200)
    target_id: str = Field(min_length=1, max_length=200)
