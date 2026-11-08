"""Small normalized envelopes; transports authenticate native identities before routing."""

from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator

from sibyl.models import Request


@dataclass(frozen=True)
class Envelope:
    id: str
    sender: str
    target: str
    text: str
    timestamp: float
    private: bool = True


@dataclass(frozen=True)
class Batch:
    messages: list[Envelope] = field(default_factory=list)
    cursor: str | None = None
    acknowledgement: str | None = None


class ChannelError(Exception):
    """Sanitized delivery outcome: only explicit rejections may be retried."""

    def __init__(self, message, *, ambiguous=False, retry_after=0):
        super().__init__(message)
        self.ambiguous, self.retry_after = ambiguous, retry_after


class DiscordSettings(Request):
    bot_token: SecretStr
    application_id: str = Field(pattern=r"^[0-9]{15,22}$")
    allowed_user_id: str = Field(pattern=r"^[0-9]{15,22}$")


class SlackSettings(Request):
    bot_token: SecretStr
    app_token: SecretStr
    allowed_user_id: str = Field(pattern=r"^[UW][A-Z0-9]{8,30}$")


class SignalSettings(Request):
    bridge_url: str = Field(default="http://127.0.0.1:8080", max_length=200)
    account: str = Field(min_length=3, max_length=100, pattern=r"^(?:\+[0-9]{7,15}|[a-f0-9-]{36})$")
    allowed_sender_aci: str = Field(pattern=r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")

    @field_validator("bridge_url")
    @classmethod
    def local_bridge(cls, value):
        parsed = urlsplit(value)
        try:
            port = parsed.port or 8080
        except ValueError:
            raise ValueError("Use a plain loopback signal-cli origin.") from None
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Use a plain loopback signal-cli origin.")
        host = "[::1]" if parsed.hostname == "::1" else "127.0.0.1"
        return f"http://{host}:{port}"


class WhatsAppSettings(Request):
    access_token: SecretStr
    api_version: str = Field(pattern=r"^v[0-9]{2,3}\.0$")
    phone_number_id: str = Field(pattern=r"^[0-9]{5,30}$")
    app_secret: SecretStr
    verify_token: SecretStr
    allowed_phone_number: str = Field(pattern=r"^\+?[1-9][0-9]{6,14}$")

    @field_validator("allowed_phone_number")
    @classmethod
    def canonical_phone(cls, value):
        return value.removeprefix("+")


class EmailSettings(Request):
    email_address: str = Field(min_length=3, max_length=200)
    allowed_sender: str = Field(min_length=3, max_length=200)
    reply_code: SecretStr
    imap_host: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9.-]+$")
    imap_port: int = Field(default=993, ge=1, le=65535, strict=True)
    imap_security: Literal["TLS", "STARTTLS"] = "TLS"
    imap_username: str = Field(min_length=1, max_length=200)
    imap_password: SecretStr
    imap_folder: str = Field(default="INBOX", min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_./ -]+$")
    smtp_host: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9.-]+$")
    smtp_port: int = Field(default=587, ge=1, le=65535, strict=True)
    smtp_security: Literal["TLS", "STARTTLS"] = "STARTTLS"
    smtp_username: str = Field(min_length=1, max_length=200)
    smtp_password: SecretStr

    @field_validator("email_address", "allowed_sender")
    @classmethod
    def address(cls, value):
        import re

        if not re.fullmatch(
            r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", value
        ):
            raise ValueError("Enter one plain email address without a display name.")
        return value.casefold()

    @field_validator("reply_code")
    @classmethod
    def paired_phrase(cls, value):
        import re

        if not re.fullmatch(r"[A-Za-z0-9_-]{24,100}", value.get_secret_value()):
            raise ValueError(
                "Use a private pairing phrase with 24–100 letters, digits, hyphens or underscores."
            )
        return value

    @model_validator(mode="after")
    def distinct_mailboxes(self):
        if self.email_address == self.allowed_sender:
            raise ValueError("Use a dedicated Sibyl mailbox separate from your personal sender.")
        return self


class ChannelAction(Request):
    revision: str = Field(pattern=r"^[a-f0-9]{32}$")
    action: Literal["check", "enable", "pause", "disconnect"]


SETTINGS = {
    "discord": DiscordSettings,
    "slack": SlackSettings,
    "signal": SignalSettings,
    "whatsapp": WhatsAppSettings,
    "email": EmailSettings,
}
SENDER_FIELD = {
    "discord": "allowed_user_id",
    "slack": "allowed_user_id",
    "signal": "allowed_sender_aci",
    "whatsapp": "allowed_phone_number",
    "email": "allowed_sender",
}


def private_values(body):
    """Unwrap secrets only for the encrypted profile writer, never HTTP responses."""
    return {name: value.get_secret_value() if isinstance(value, SecretStr) else value for name, value in body}
