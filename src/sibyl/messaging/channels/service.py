"""Shared durable private-chat routing; ProtoLink owns inference and conversations.

Provider clients normalize authenticated events. This service validates the
configured sender/target again, commits before ACK, and owns local delivery
receipts. It never exposes a send tool or grants financial action permissions.
"""

import asyncio
import json
import threading
import time
from uuid import uuid4

import aiohttp
import httpx
from pydantic import SecretStr, ValidationError

from sibyl.agents.utils.conversations import SibylRequest
from sibyl.messaging.channels.contracts import SENDER_FIELD, SETTINGS, ChannelError, private_values
from sibyl.messaging.channels.discord import DiscordClient
from sibyl.messaging.channels.email import EmailClient
from sibyl.messaging.channels.signal import SignalClient
from sibyl.messaging.channels.slack import SlackClient
from sibyl.messaging.channels.whatsapp import WhatsAppClient
from sibyl.messaging.outbound import chunks

CLIENTS = {
    "discord": DiscordClient,
    "slack": SlackClient,
    "signal": SignalClient,
    "whatsapp": WhatsAppClient,
    "email": EmailClient,
}
MAX_QUEUED = 100


class PrivateChannels:
    """One local receiver per explicitly enabled connection, independent of model setup."""

    def __init__(self, store, network, http=None):
        self.store, self.network = store, network
        self.http = http or httpx.AsyncClient(follow_redirects=False, trust_env=False)
        self.lock = threading.RLock()
        self.clients = {}
        self.locks = {key: asyncio.Lock() for key in CLIENTS}
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS channel_messages(channel TEXT NOT NULL,revision TEXT NOT NULL,native_id TEXT NOT NULL,state TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(channel,revision,native_id));
                CREATE TABLE IF NOT EXISTS channel_outbox(id TEXT PRIMARY KEY,channel TEXT NOT NULL,revision TEXT NOT NULL,native_id TEXT NOT NULL,part INTEGER NOT NULL,state TEXT NOT NULL,target TEXT NOT NULL,text TEXT NOT NULL,provider_id TEXT,error TEXT,attempts INTEGER NOT NULL DEFAULT 0,next_attempt REAL NOT NULL DEFAULT 0,created_at REAL NOT NULL,UNIQUE(channel,revision,native_id,part));
            """)
            db.execute(
                "UPDATE channel_outbox SET state='uncertain',error='Delivery was interrupted. Check the recipient app before deciding what to do.' WHERE state='sending'"
            )
            db.execute(
                "UPDATE channel_outbox SET state='blocked',error='An earlier part was not confirmed.' WHERE state='pending' AND EXISTS(SELECT 1 FROM channel_outbox uncertain WHERE uncertain.channel=channel_outbox.channel AND uncertain.revision=channel_outbox.revision AND uncertain.native_id=channel_outbox.native_id AND uncertain.state='uncertain')"
            )
            for row in db.execute("SELECT * FROM channel_messages WHERE state='processing'").fetchall():
                message = json.loads(row["payload"])
                saved = db.execute(
                    "SELECT payload FROM sibyl_turns WHERE json_extract(payload,'$.request_id')=?",
                    (message["request_id"],),
                ).fetchone()
                if saved:
                    self._complete(db, dict(row), json.loads(saved[0])["answer"])
                else:
                    db.execute(
                        "UPDATE channel_messages SET state='interrupted' WHERE channel=? AND revision=? AND native_id=?",
                        (row["channel"], row["revision"], row["native_id"]),
                    )

    def profile(self, channel):
        if channel not in CLIENTS:
            raise LookupError("Messaging channel not implemented.")
        return self.store.data_profile("messaging:" + channel)

    def public(self, channel):
        profile = self.profile(channel)
        with self.store.db() as db:
            counts = {
                r[0]: r[1]
                for r in db.execute(
                    "SELECT state,COUNT(*) FROM channel_messages WHERE channel=? AND revision=? GROUP BY state",
                    (channel, profile.get("revision", "")),
                )
            }
            delivery = {
                r[0]: r[1]
                for r in db.execute(
                    "SELECT state,COUNT(*) FROM channel_outbox WHERE channel=? AND revision=? GROUP BY state",
                    (channel, profile.get("revision", "")),
                )
            }
        return dict(
            id=channel,
            status="available",
            connected=bool(profile.get("verified")),
            configured=bool(profile.get("revision")),
            enabled=bool(profile.get("enabled")),
            revision=profile.get("revision"),
            bot_username=profile.get("bot_username"),
            last_checked_at=profile.get("last_checked_at"),
            last_poll_at=profile.get("last_poll_at"),
            last_message_at=profile.get("last_message_at"),
            error=profile.get("error"),
            updates=counts,
            delivery=delivery,
            settings={
                key: profile[key]
                for key, field in SETTINGS[channel].model_fields.items()
                if key in profile and field.annotation is not SecretStr
            },
            has_credentials=bool(profile.get("revision")),
        )

    def _update(self, channel, revision, **changes):
        with self.lock:
            current = self.profile(channel)
            if current.get("revision") != revision:
                return False
            self.store.save_data_profile("messaging:" + channel, {**current, **changes})
            return True

    def save(self, channel, values, revision=None):
        if channel not in SETTINGS:
            raise LookupError("Messaging channel not implemented.")
        try:
            body = SETTINGS[channel].model_validate(values)
        except ValidationError:
            raise ValueError(
                "Enter the required channel credentials and a valid private recipient."
            ) from None
        values = private_values(body)
        if any(
            isinstance(value, str)
            and (not value.strip() or len(value) > 4096 or any(ord(c) < 32 for c in value))
            for value in values.values()
        ):
            raise ValueError("Use non-empty messaging fields without control characters.")
        with self.lock:
            current = self.profile(channel)
            if current.get("enabled"):
                raise ValueError("Pause this channel before changing credentials or recipient.")
            if current.get("revision") != revision:
                raise ValueError("This connection changed. Refresh before editing.")
            self._invalidate(channel, current.get("revision"))
            self.store.save_data_profile(
                "messaging:" + channel,
                {
                    **values,
                    "revision": uuid4().hex,
                    "control": uuid4().hex,
                    "enabled": False,
                    "verified": False,
                    "configured_at": time.time(),
                },
            )
        return self.public(channel)

    def _invalidate(self, channel, revision):
        with self.store.db() as db:
            db.execute(
                "UPDATE channel_outbox SET state='withdrawn',error='The saved connection was paused or replaced before sending.' WHERE channel=? AND revision=? AND state='pending'",
                (channel, revision),
            )
            db.execute(
                "UPDATE channel_messages SET state='interrupted' WHERE channel=? AND revision=? AND state='queued'",
                (channel, revision),
            )

    async def client(self, channel, profile):
        key = (channel, profile["revision"])
        if key not in self.clients:
            for old in [key for key in self.clients if key[0] == channel]:
                await self.clients.pop(old).close()
            self.clients[key] = CLIENTS[channel](profile, self.http)
        else:
            self.clients[key].profile = profile
        return self.clients[key]

    async def action(self, channel, action):
        if channel not in CLIENTS:
            raise LookupError("Messaging channel not implemented.")
        # Pause remains responsive while a receiver/model is awaiting I/O. It changes
        # the control generation first; late model output cannot queue a reply.
        if action.action in {"pause", "disconnect"}:
            with self.lock:
                current = self.profile(channel)
                if current.get("revision") != action.revision:
                    raise ValueError("This connection changed. Refresh its current state.")
                self._invalidate(channel, current["revision"])
                if action.action == "disconnect":
                    self.store.save_data_profile("messaging:" + channel, {})
                else:
                    self._update(channel, current["revision"], enabled=False, control=uuid4().hex)
            return self.public(channel)
        async with self.locks[channel]:
            initial = self.profile(channel)
            if initial.get("revision") != action.revision:
                raise ValueError("This connection changed. Refresh its current state.")
            if initial.get("enabled"):
                if action.action == "enable":
                    return self.public(channel)
                raise ValueError("Pause this channel before checking its connection.")
            try:
                client = await self.client(channel, initial)
                facts = await client.identity()
            except ChannelError as error:
                self._update(channel, initial["revision"], error=str(error), verified=False, enabled=False)
                raise ValueError(str(error)) from None
            with self.lock:
                current = self.profile(channel)
                if current.get("revision") != initial["revision"] or current.get("control") != initial.get(
                    "control"
                ):
                    raise ValueError("The connection or pause controls changed during its identity check.")
                # A different bot/team/target cannot inherit the old conversation or queue.
                if current.get("verified") and any(
                    current.get(key) != facts.get(key) for key in ("bot_id", "target", "team_id")
                ):
                    self._invalidate(channel, current["revision"])
                    self._update(
                        channel,
                        current["revision"],
                        enabled=False,
                        verified=False,
                        error="The native bot or recipient changed. Save the connection again.",
                    )
                    raise ValueError("The native bot or target changed. Save the connection again.")
                enabled = action.action == "enable"
                changes = {
                    **facts,
                    "verified": True,
                    "last_checked_at": time.time(),
                    "error": None,
                    "enabled": enabled,
                    "control": uuid4().hex,
                    "next_attempt": 0,
                }
                if enabled:
                    changes["enabled_at"] = time.time()
                    if channel == "discord":
                        changes["cursor"] = client.initial_cursor(changes["enabled_at"])
                self._update(channel, initial["revision"], **changes)
            return self.public(channel)

    def ingest(self, channel, profile, batch):
        """Store only authorized normalized text; commit before returning to the native ACK."""
        with self.lock:
            current = self.profile(channel)
            if (
                not current.get("enabled")
                or current.get("revision") != profile["revision"]
                or current.get("control") != profile.get("control")
            ):
                return False
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                pending = db.execute(
                    "SELECT COUNT(*) FROM channel_messages WHERE channel=? AND state IN ('queued','processing')",
                    (channel,),
                ).fetchone()[0]
                accepted = []
                for envelope in batch.messages:
                    if (
                        not envelope.private
                        or envelope.sender != profile[SENDER_FIELD[channel]]
                        or envelope.target != profile["target"]
                        or not isinstance(envelope.text, str)
                        or not envelope.text.strip()
                        or len(envelope.text) > 4000
                        or not int(profile.get("enabled_at", time.time()))
                        <= envelope.timestamp
                        <= time.time() + 60
                    ):
                        continue
                    if not isinstance(envelope.id, str) or not 1 <= len(envelope.id) <= 200:
                        raise ChannelError("Invalid native message identity.")
                    exists = db.execute(
                        "SELECT 1 FROM channel_messages WHERE channel=? AND revision=? AND native_id=?",
                        (channel, profile["revision"], envelope.id),
                    ).fetchone()
                    if not exists:
                        accepted.append(envelope)
                if pending + len(accepted) > MAX_QUEUED:
                    raise ChannelError(
                        "This channel reached its 100-message pending budget. No new receive cursor was acknowledged."
                    )
                for envelope in accepted:
                    message = dict(
                        text=envelope.text.strip(),
                        target=envelope.target,
                        sender=envelope.sender,
                        received_at=time.time(),
                        request_id=uuid4().hex,
                        chunk_units=CLIENTS[channel].chunk_units,
                        bot_id=profile.get("bot_id"),
                    )
                    db.execute(
                        "INSERT OR IGNORE INTO channel_messages VALUES(?,?,?,?,?)",
                        (
                            channel,
                            profile["revision"],
                            envelope.id,
                            "queued",
                            json.dumps(message, allow_nan=False),
                        ),
                    )
            self._update(
                channel,
                profile["revision"],
                cursor=batch.cursor,
                last_poll_at=time.time(),
                last_message_at=time.time() if accepted else current.get("last_message_at"),
                last_inbound_at=max(row.timestamp for row in accepted)
                if accepted
                else current.get("last_inbound_at"),
            )
            return True

    @staticmethod
    def _complete(db, row, answer):
        message = json.loads(row["payload"])
        # Bound stored replies, keeping uncertainty/partial outcomes inspectable.
        text = (
            answer
            if isinstance(answer, str) and answer.strip()
            else "Sibyl did not finish this answer. Open the conversation in the app."
        )
        if len(text) > 60000:
            text = text[:59000] + "\nRead the complete retained answer in Sibyl."
        for index, part in enumerate(chunks(text, message["chunk_units"])):
            db.execute(
                "INSERT OR IGNORE INTO channel_outbox(id,channel,revision,native_id,part,state,target,text,created_at) VALUES(?,?,?,?,?,'pending',?,?,?)",
                (
                    uuid4().hex,
                    row["channel"],
                    row["revision"],
                    row["native_id"],
                    index,
                    message["target"],
                    part,
                    time.time(),
                ),
            )
        db.execute(
            "UPDATE channel_messages SET state='completed' WHERE channel=? AND revision=? AND native_id=?",
            (row["channel"], row["revision"], row["native_id"]),
        )

    async def process(self, channel, profile):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM channel_messages WHERE channel=? AND revision=? AND state='queued' ORDER BY rowid LIMIT 1",
                (channel, profile["revision"]),
            ).fetchone()
            if not row:
                return False
            db.execute(
                "UPDATE channel_messages SET state='processing' WHERE channel=? AND revision=? AND native_id=?",
                (channel, profile["revision"], row["native_id"]),
            )
        message = json.loads(row["payload"])
        try:
            text = message["text"]
            session = profile.get("session_id")
            if text in {"/help", "/start"}:
                answer = "I’m Sibyl. Ask about your workspace, markets or strategies. /new starts a new conversation; /status checks model readiness. This is a private read-only agent connection."
            elif text == "/new":
                session = self.network.conversations.create()["id"]
                self._update(channel, profile["revision"], session_id=session)
                answer = "Started a new Sibyl conversation."
            elif text == "/status":
                answer = (
                    "Sibyl is ready."
                    if self.network.status()["ready"]
                    else "Configure an AI model in Sibyl → Settings → AI models."
                )
            elif not self.network.status()["ready"]:
                answer = (
                    "Configure an AI model in Sibyl → Settings → AI models, then send your question again."
                )
            else:
                if not session:
                    session = self.network.conversations.create()["id"]
                    self._update(channel, profile["revision"], session_id=session)
                result = await self.network.ask(
                    SibylRequest(message=text, session_id=session, request_id=message["request_id"])
                )
                answer = (
                    result.get("answer") or "This request did not finish. Open the conversation in Sibyl."
                )
            with self.lock, self.store.db() as db:
                current = self.profile(channel)
                if (
                    current.get("enabled")
                    and current.get("revision") == profile["revision"]
                    and current.get("control") == profile.get("control")
                ):
                    self._complete(db, dict(row), answer)
                else:
                    db.execute(
                        "UPDATE channel_messages SET state='interrupted' WHERE channel=? AND revision=? AND native_id=?",
                        (channel, profile["revision"], row["native_id"]),
                    )
        except BaseException as error:
            with self.store.db() as db:
                db.execute(
                    "UPDATE channel_messages SET state=? WHERE channel=? AND revision=? AND native_id=?",
                    (
                        "interrupted" if isinstance(error, asyncio.CancelledError) else "failed",
                        channel,
                        profile["revision"],
                        row["native_id"],
                    ),
                )
            if isinstance(error, asyncio.CancelledError):
                raise
            self._update(
                channel,
                profile["revision"],
                error="Sibyl could not finish an answer. Check the model and resend your question deliberately.",
            )
        return True

    async def deliver(self, channel, profile):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM channel_outbox WHERE channel=? AND revision=? AND state='pending' ORDER BY created_at,part LIMIT 1",
                (channel, profile["revision"]),
            ).fetchone()
            if not row:
                return False
            if row["next_attempt"] > time.time():
                return True
            db.execute(
                "UPDATE channel_outbox SET state='sending',attempts=attempts+1 WHERE id=?", (row["id"],)
            )
        try:
            client = await self.client(channel, profile)
            native = await client.send(row["target"], row["text"])
            with self.store.db() as db:
                db.execute(
                    "UPDATE channel_outbox SET state='sent',provider_id=?,error=NULL WHERE id=?",
                    (native, row["id"]),
                )
        except ChannelError as error:
            retry = bool(error.retry_after) and row["attempts"] < 4
            outcome = "pending" if retry else "uncertain" if error.ambiguous else "failed"
            with self.store.db() as db:
                db.execute(
                    "UPDATE channel_outbox SET state=?,next_attempt=?,error=? WHERE id=?",
                    (outcome, time.time() + error.retry_after, str(error), row["id"]),
                )
                if not retry:
                    db.execute(
                        "UPDATE channel_outbox SET state='blocked',error='An earlier part was not confirmed.' WHERE channel=? AND revision=? AND native_id=? AND state='pending'",
                        (channel, profile["revision"], row["native_id"]),
                    )
            self._update(channel, profile["revision"], error=str(error))
        except BaseException:
            with self.store.db() as db:
                db.execute(
                    "UPDATE channel_outbox SET state='uncertain',error='The send was interrupted. Check the recipient app.' WHERE id=?",
                    (row["id"],),
                )
                db.execute(
                    "UPDATE channel_outbox SET state='blocked' WHERE channel=? AND revision=? AND native_id=? AND state='pending'",
                    (channel, profile["revision"], row["native_id"]),
                )
            raise
        return True

    async def tick(self, channel):
        async with self.locks[channel]:
            profile = self.profile(channel)
            if not profile.get("enabled") or profile.get("next_attempt", 0) > time.time():
                return
            try:
                if await self.deliver(channel, profile) or await self.process(channel, profile):
                    return
                if channel == "whatsapp":
                    return  # Webhooks own actual receive timing; idle ticks are not fake polls.
                client = await self.client(channel, profile)
                batch = await client.receive(profile.get("cursor"))
                if self.ingest(channel, profile, batch):
                    await client.acknowledge(batch)
            except ChannelError as error:
                self._update(
                    channel,
                    profile["revision"],
                    error=str(error),
                    next_attempt=time.time() + (error.retry_after or 30),
                )
            except (aiohttp.ClientError, ConnectionError, TimeoutError, ValueError):
                self._update(
                    channel,
                    profile["revision"],
                    error="The channel receiver disconnected. Check its settings and provider history.",
                    next_attempt=time.time() + 30,
                )
                if client := self.clients.pop((channel, profile["revision"]), None):
                    await client.close()

    def receipts(self, channel, offset=0):
        self.profile(channel)
        with self.store.db() as db:
            rows = [
                dict(row)
                for row in db.execute(
                    "SELECT id,revision,native_id,part,state,target,provider_id,error,attempts,created_at FROM channel_outbox WHERE channel=? ORDER BY rowid DESC LIMIT 50 OFFSET ?",
                    (channel, offset),
                )
            ]
        return dict(
            items=rows,
            offset=offset,
            limit=50,
            note="Sent means accepted by the provider, not confirmed read by the human. Uncertain writes are never resent automatically.",
        )

    async def close(self):
        for client in self.clients.values():
            await client.close()
        self.clients.clear()
        await self.http.aclose()
