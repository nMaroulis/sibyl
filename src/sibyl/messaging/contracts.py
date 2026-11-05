"""Shared identity contracts for explicitly reviewed private Telegram recipients."""

from pydantic import Field

from sibyl.models import Request


class TelegramTarget(Request):
    """The checked bot and human private-chat user shown in a delivery editor."""

    bot_id: int = Field(gt=0, le=2**52, strict=True)
    user_id: int = Field(gt=0, le=2**52, strict=True)
