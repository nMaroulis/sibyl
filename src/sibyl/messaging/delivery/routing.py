"""Reuse owned native clients for notifications without an LLM or send tool.

Channel workers own client access and serialize replies/notifications. Normalized
profiles expose identity/control fields only; credentials stay in native clients.
Every private send rechecks its admitted binding after asynchronous client setup.
"""

import time

from sibyl.messaging.channels.contracts import SENDER_FIELD, ChannelError

NAMES = {
    "telegram": "Telegram",
    "discord": "Discord",
    "slack": "Slack",
    "signal": "Signal",
    "whatsapp": "WhatsApp",
    "email": "Email",
}


class NotificationRoutes:
    """Resolve checked private destinations; never accept a model-supplied recipient."""

    def __init__(self, settings, client, on_error):
        self.settings, self.telegram_client, self.on_error = settings, client, on_error
        self.channels = None

    def profile(self, channel="telegram"):
        """Read a private route's current control generation without returning credentials."""
        if channel == "telegram":
            original = self.settings.profile()
            return {
                key: original.get(key)
                for key in (
                    "enabled",
                    "verified",
                    "revision",
                    "control_id",
                    "bot_id",
                    "allowed_user_id",
                    "bot_username",
                )
            }
        if channel not in SENDER_FIELD or self.channels is None:
            raise ValueError("This notification channel is not available.")
        original = self.channels.profile(channel)
        result = dict(
            enabled=original.get("enabled", False),
            verified=original.get("verified", False),
            revision=original.get("revision"),
            control_id=original.get("control"),
            bot_id=original.get("bot_id"),
            allowed_user_id=original.get(SENDER_FIELD[channel]),
            target_id=original.get("target"),
            bot_username=original.get("bot_username"),
        )
        if channel == "whatsapp":
            result["window_until"] = (original.get("last_inbound_at") or 0) + 24 * 3600 - 60
        return result

    @staticmethod
    def target(channel, profile):
        """Freeze the checked identity shown to the user, excluding mutable runtime controls."""
        if not profile.get("verified") or not all(
            profile.get(key) for key in ("revision", "bot_id", "allowed_user_id", "target_id")
        ):
            return None
        return dict(
            channel=channel,
            revision=profile["revision"],
            bot_id=str(profile["bot_id"]),
            recipient_id=str(profile["allowed_user_id"]),
            target_id=str(profile["target_id"]),
        )

    def targets(self):
        """Describe existing checked connections without probes or outbound messages."""
        rows = []
        for channel, label in NAMES.items():
            if channel != "telegram" and self.channels is None:
                continue
            profile = self.profile(channel)
            if channel == "telegram":
                target = (
                    dict(bot_id=profile["bot_id"], user_id=profile["allowed_user_id"])
                    if profile.get("verified") and profile.get("bot_id") and profile.get("allowed_user_id")
                    else None
                )
            else:
                target = self.target(channel, profile)
            rows.append(
                dict(
                    channel=channel,
                    label=label,
                    checked=bool(target),
                    enabled=bool(profile.get("enabled")),
                    target=target,
                    account_label=profile.get("bot_username") or label,
                    recipient=str(profile.get("allowed_user_id") or ""),
                    window_open=profile.get("window_until", float("inf")) > time.time(),
                    note="Only within the private 24-hour reply window; outside it alerts stay local. No templates are sent."
                    if channel == "whatsapp"
                    else "Uses your checked private connection; no group or arbitrary recipient delivery.",
                )
            )
        return {"items": rows}

    def binding(self, channel, request):
        """Reject stale identity consent before storing an enabled alert policy."""
        profile = self.profile(channel)
        target = self.target(channel, profile)
        if target is None:
            raise ValueError("Save and check this private connection in Settings → Messaging first.")
        if request is None or request.model_dump(mode="json") != target:
            raise ValueError("The checked private connection changed. Review its current recipient again.")
        return dict(
            bot_id=profile["bot_id"],
            recipient_id=profile["allowed_user_id"],
            target_id=profile["target_id"],
            connection_revision=profile["revision"],
            bot_username=profile.get("bot_username", ""),
        )

    def accept(self, channel, binding):
        """Freeze only route identity/control state for a queued long-running report."""
        profile = self.profile(channel)
        intent = {
            "channel": channel,
            "connection_revision": profile.get("revision"),
            "control_id": profile.get("control_id"),
            "bot_id": binding.get("bot_id"),
            "recipient_id": binding.get("recipient_id"),
            "target_id": binding.get("target_id"),
        }
        ready = self.matches(intent, profile)
        if channel != "telegram" and binding.get("connection_revision") != profile.get("revision"):
            ready = False
        return {
            "channel": channel,
            "revision": profile.get("revision"),
            "control_id": profile.get("control_id"),
            "ready": ready,
        }

    def units(self, channel):
        if channel == "telegram":
            return 4000
        from sibyl.messaging.channels.service import CLIENTS

        return CLIENTS[channel].chunk_units

    async def send(self, channel, delivery, part, authorize):
        """Send one admitted part through its owned client, with one final policy fence."""
        if channel == "telegram":
            original = self.settings.profile()
            if not self.matches(delivery, original) or not authorize(delivery):
                from sibyl.messaging.telegram import TelegramError

                raise TelegramError("The Telegram connection or notification policy changed before sending.")
            native = self.telegram_client(original)
            if part["format"] == "document":
                return await native.send_document(delivery["recipient_id"], part["text"], part["filename"])
            return await native.send(delivery["recipient_id"], part["text"])
        original = self.channels.profile(channel)
        if not self.matches(delivery, self.profile(channel)):
            raise ChannelError("The private connection changed before the send was admitted.")
        native = await self.channels.client(channel, original)
        if not self.matches(delivery, self.profile(channel)) or not authorize(delivery):
            raise ChannelError("The private connection or notification policy changed before sending.")
        if channel == "email":
            return await native.send_notification(delivery["target_id"], part["text"])
        return await native.send(delivery["target_id"], part["text"])

    @staticmethod
    def matches(delivery, profile):
        """A pause/resume, key replacement or target change cannot inherit queued consent."""
        return bool(
            profile.get("enabled")
            and profile.get("verified")
            and delivery["connection_revision"] == profile.get("revision")
            and delivery["control_id"] == profile.get("control_id")
            and delivery["bot_id"] == profile.get("bot_id")
            and delivery["recipient_id"] == profile.get("allowed_user_id")
            and (
                delivery.get("channel", "telegram") == "telegram"
                or delivery.get("target_id") == profile.get("target_id")
            )
            and profile.get("window_until", float("inf")) > time.time()
        )

    def rejected(self, channel, revision, error):
        """Retain only sanitized provider failures in the owning connection's status."""
        if channel == "telegram":
            self.on_error(revision, error)
        else:
            changes = {"error": str(error)}
            if error.retry_after:
                changes["next_attempt"] = time.time() + error.retry_after
            self.channels._update(channel, revision, **changes)
