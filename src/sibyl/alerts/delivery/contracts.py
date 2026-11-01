"""Reviewed rule/recipient selections, independent of alert evaluation and AI."""

from typing import Literal

from pydantic import Field, model_validator

from sibyl.messaging.contracts import TelegramTarget
from sibyl.models import Request

AlertKind = Literal["price", "risk", "strategy", "connection"]


class DeliverySettings(Request):
    """Authorize future alerts only; every save resets the cursor past existing notices."""

    revision: int = Field(default=0, ge=0, strict=True)
    rule_revision: int = Field(ge=1, strict=True)
    enabled: bool = Field(default=False, strict=True)
    telegram_target: TelegramTarget | None = None
    cooldown_seconds: int = Field(default=300, ge=60, le=86400, strict=True)
    expiry_seconds: int = Field(default=600, ge=60, le=3600, strict=True)

    @model_validator(mode="after")
    def recipient(self):
        if self.enabled and self.telegram_target is None:
            raise ValueError("Select the checked bot and private Telegram user before enabling delivery.")
        return self
