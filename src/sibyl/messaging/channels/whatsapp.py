"""Meta Cloud API text replies and authenticated webhook envelope normalization."""

import hashlib
import hmac
import re
import time

from sibyl.messaging.channels.contracts import Batch, ChannelError, Envelope
from sibyl.messaging.channels.http import call


class WhatsAppClient:
    chunk_units = 3500

    def __init__(self, profile, http):
        self.profile, self.http = profile, http

    async def api(self, method, path, **kwargs):
        return await call(
            self.http,
            method,
            f"https://graph.facebook.com/{self.profile['api_version']}/{self.profile['phone_number_id']}{path}",
            headers={"Authorization": "Bearer " + self.profile["access_token"]},
            **kwargs,
        )

    async def identity(self):
        body = await self.api("GET", "", params={"fields": "id,display_phone_number,verified_name"})
        if not isinstance(body, dict) or str(body.get("id", "")) != self.profile["phone_number_id"]:
            raise ChannelError("Meta did not identify the configured WhatsApp business phone.")
        return dict(
            bot_id=str(body["id"]),
            bot_username=body.get("verified_name")
            or body.get("display_phone_number")
            or "WhatsApp business number",
            target=self.profile["allowed_phone_number"],
        )

    def verify(self, raw, signature):
        """Authenticate raw bytes before JSON parsing, using the Meta app secret."""
        if not isinstance(signature, str) or not re.fullmatch(r"sha256=[a-fA-F0-9]{64}", signature):
            return False
        expected = hmac.new(self.profile["app_secret"].encode(), raw, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature[7:].lower())

    def messages(self, body):
        """Keep exact phone binding and native IDs; ignore unsupported events and media."""
        result = []
        if not isinstance(body, dict) or body.get("object") != "whatsapp_business_account":
            return Batch()
        entries = body.get("entry", [])
        if not isinstance(entries, list) or len(entries) > 100:
            raise ChannelError("The WhatsApp event batch exceeds the bounded intake contract.")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ChannelError("Invalid WhatsApp event entry.")
            changes = entry.get("changes", [])
            if not isinstance(changes, list) or len(changes) > 100:
                raise ChannelError("Invalid WhatsApp event changes.")
            for change in changes:
                if not isinstance(change, dict):
                    raise ChannelError("Invalid WhatsApp event change.")
                value = change.get("value") or {}
                if not isinstance(value, dict):
                    raise ChannelError("Invalid WhatsApp event value.")
                metadata = value.get("metadata") or {}
                if (
                    not isinstance(metadata, dict)
                    or change.get("field") != "messages"
                    or str(metadata.get("phone_number_id")) != self.profile["phone_number_id"]
                ):
                    continue
                rows = value.get("messages", [])
                if not isinstance(rows, list) or len(rows) > 100:
                    raise ChannelError("The WhatsApp message batch exceeds the intake contract.")
                for row in rows:
                    if not isinstance(row, dict):
                        raise ChannelError("Invalid WhatsApp message.")
                    if row.get("type") != "text" or row.get("group_id"):
                        continue
                    try:
                        stamp = int(row["timestamp"])
                    except (ValueError, TypeError, KeyError):
                        continue
                    sender = str(row.get("from", ""))
                    text = row.get("text") or {}
                    if not isinstance(text, dict):
                        continue
                    result.append(
                        Envelope(str(row.get("id", "")), sender, sender, text.get("body", ""), stamp)
                    )
        if len(result) > 100:
            raise ChannelError("The WhatsApp webhook exceeds the bounded message budget.")
        return Batch(result)

    async def receive(self, cursor):
        """Incoming messages use the separately HMAC-authenticated webhook route."""
        return Batch(cursor=cursor)

    async def acknowledge(self, batch):
        """The webhook response acknowledges only already committed local receipts."""

    async def send(self, target, text):
        if target != self.profile["allowed_phone_number"]:
            raise ChannelError("The saved private recipient changed.")
        last = self.profile.get("last_inbound_at")
        if not last or time.time() - last >= 24 * 3600 - 60:
            raise ChannelError(
                "The WhatsApp reply window expired. Send a new private message; Sibyl does not send templates."
            )
        result = await self.api(
            "POST",
            "/messages",
            payload={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": target,
                "type": "text",
                "text": {"preview_url": False, "body": text},
            },
            write=True,
        )
        identities = result.get("messages") if isinstance(result, dict) else None
        if (
            not isinstance(identities, list)
            or len(identities) != 1
            or not isinstance(identities[0].get("id"), str)
        ):
            raise ChannelError("Meta did not confirm message acceptance.", ambiguous=True)
        return identities[0]["id"]

    async def close(self):
        """The application owns the shared HTTP pool."""
