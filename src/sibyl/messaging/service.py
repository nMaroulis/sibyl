"""Durable private-chat routing and conservative Telegram delivery outcomes."""

import asyncio
import json
import threading
import time
from uuid import uuid4

import httpx

from sibyl.agents.conversations import SibylRequest
from sibyl.messaging.settings import MessagingSettings
from sibyl.messaging.telegram import TelegramClient, TelegramError


class TelegramService:
    """Own polling, sender binding, saved chat identity and an explicit delivery outbox.

    One local API worker owns this channel. A native update is durably ingested
    before acknowledging its offset. Uncertain sends never retry automatically,
    since Telegram does not supply an idempotency key for sendMessage.
    """

    def __init__(self, store, network, http=None):
        self.store, self.network = store, network
        self.settings = MessagingSettings(store)
        self.http = http or httpx.AsyncClient(follow_redirects=False)
        self._lock = threading.RLock()
        self._tick_lock = asyncio.Lock()
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS telegram_updates (
                    revision TEXT NOT NULL, update_id INTEGER NOT NULL, state TEXT NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(revision,update_id)
                );
                CREATE TABLE IF NOT EXISTS telegram_outbox (
                    id INTEGER PRIMARY KEY, revision TEXT NOT NULL, update_id INTEGER NOT NULL,
                    part INTEGER NOT NULL, chat_id INTEGER NOT NULL, text TEXT NOT NULL,
                    state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt REAL NOT NULL DEFAULT 0, error TEXT, native_id INTEGER,
                    UNIQUE(revision,update_id,part)
                );
            """)
            db.execute(
                "UPDATE telegram_outbox SET state='uncertain',error='Delivery was interrupted. Check Telegram before deciding to resend.' WHERE state='sending'"
            )
            # Inference is not replayed on restart. Recover an already committed
            # native Sibyl answer when available, otherwise surface interruption.
            for row in db.execute(
                "SELECT revision,update_id,payload FROM telegram_updates WHERE state='processing'"
            ).fetchall():
                message = json.loads(row[2])
                saved = db.execute(
                    "SELECT payload FROM sibyl_turns WHERE json_extract(payload,'$.request_id')=?",
                    (message["request_id"],),
                ).fetchone()
                if saved:
                    self._complete(db, row[0], row[1], message["chat_id"], json.loads(saved[0])["answer"])
                else:
                    db.execute(
                        "UPDATE telegram_updates SET state='interrupted' WHERE revision=? AND update_id=?",
                        (row[0], row[1]),
                    )

    def client(self, profile):
        """Construct a transport bound to exactly one encrypted connection revision."""
        return TelegramClient(profile["bot_token"], self.http)

    def public(self):
        """Return connection/delivery health without message bodies, tokens or native errors."""
        result = self.settings.public()
        profile = self.settings.profile()
        with self.store.db() as db:
            rows = db.execute(
                "SELECT state,COUNT(*) FROM telegram_updates WHERE revision=? GROUP BY state",
                (profile.get("revision", ""),),
            ).fetchall()
            outbox = db.execute(
                "SELECT state,COUNT(*) FROM telegram_outbox WHERE revision=? GROUP BY state",
                (profile.get("revision", ""),),
            ).fetchall()
        result["telegram"] = {
            "updates": dict(rows),
            "delivery": dict(outbox),
            "llm_ready": self.network.status()["ready"],
        }
        return result

    def save(self, body):
        """Serialize connection edits with local ingestion and checkpoint changes."""
        with self._lock:
            self.settings.save(body)
        return self.public()

    def _update(self, revision, **changes):
        with self._lock:
            current = self.settings.profile()
            if current.get("revision") != revision:
                return False
            self.store.save_data_profile("messaging:telegram", {**current, **changes})
            return True

    async def check(self):
        """Validate saved credentials and webhook compatibility without messaging a user."""
        profile = self.settings.profile()
        if not profile.get("bot_token"):
            raise ValueError("Save your bot token and numeric Telegram user ID first.")
        try:
            bot = await self.client(profile).identity()
        except TelegramError as error:
            self._update(profile["revision"], verified=False, error=str(error))
            raise ValueError(str(error)) from None
        if not self._update(
            profile["revision"],
            verified=True,
            bot_username=bot["username"],
            error=None,
            last_checked_at=time.time(),
        ):
            raise ValueError("Connection changed during the check. Check the saved connection again.")
        return self.public()

    async def enable(self):
        """Enable the verified transport independently of model setup.

        Help/status commands work without a model. Ordinary questions receive
        setup guidance until the coordinator is ready; no inference is attempted.
        """
        initial = self.settings.profile()
        await self.check()
        with self._lock:
            profile = self.settings.profile()
            if profile.get("revision") != initial.get("revision") or profile.get("control_id") != initial.get(
                "control_id"
            ):
                raise ValueError("Telegram connection changed while enabling it. Review its current state.")
            self._update(
                profile["revision"],
                enabled=True,
                enabled_at=profile.get("enabled_at", time.time()),
                error=None,
                next_attempt=0,
                control_id=uuid4().hex,
            )
        return self.public()

    def pause(self):
        """Stop future polls and sends; an already submitted HTTP send can still finish."""
        profile = self.settings.profile()
        if profile:
            self._update(profile["revision"], enabled=False, control_id=uuid4().hex)
        return self.public()

    def disconnect(self):
        """Remove the encrypted bot credential and invalidate queued work; chats stay local."""
        with self._lock:
            self.store.save_data_profile("messaging:telegram", {})
        return self.public()

    def _current(self, revision):
        profile = self.settings.profile()
        return profile.get("revision") == revision and profile.get("enabled")

    def ingest(self, profile, updates):
        """Accept only the bound human's ordinary private text; store no ignored content."""
        with self._lock:
            if not self._current(profile["revision"]):
                return
            offset = profile.get("offset", 0)
            with self.store.db() as db:
                for update in updates:
                    identity = update.get("update_id")
                    if type(identity) is not int or identity < 0:
                        raise TelegramError("Telegram returned an invalid update identity.")
                    offset = max(offset, identity + 1)
                    message = update.get("message") or {}
                    sender, chat = message.get("from", {}), message.get("chat", {})
                    allowed = profile["allowed_user_id"]
                    text = message.get("text")
                    authorized = (
                        sender.get("id") == allowed
                        and chat.get("id") == allowed
                        and chat.get("type") == "private"
                        and sender.get("is_bot") is False
                        and not message.get("forward_origin")
                        and not message.get("via_bot")
                    )
                    date = message.get("date")
                    accepted = (
                        authorized
                        and type(date) is int
                        and date >= int(profile.get("enabled_at", time.time()))
                        and isinstance(text, str)
                        and bool(text.strip())
                        and len(text) <= 4000
                    )
                    payload = (
                        {
                            "chat_id": allowed,
                            "text": text.strip(),
                            "request_id": uuid4().hex,
                            "received_at": time.time(),
                        }
                        if accepted
                        else {}
                    )
                    db.execute(
                        "INSERT OR IGNORE INTO telegram_updates VALUES(?,?,?,?)",
                        (
                            profile["revision"],
                            identity,
                            "queued" if accepted else "ignored",
                            json.dumps(payload),
                        ),
                    )
            self._update(profile["revision"], offset=offset, error=None, last_poll_at=time.time())

    @staticmethod
    def _complete(db, revision, identity, chat, answer):
        """Persist response chunks and completion atomically before any provider send."""
        text = str(answer)
        if len(text) > 40_000:
            text = text[:39_900] + "\n[Answer shortened. Read the full answer in Sibyl.]"
        for part, start in enumerate(range(0, len(text), 4000)):
            db.execute(
                "INSERT OR IGNORE INTO telegram_outbox(revision,update_id,part,chat_id,text,state) VALUES(?,?,?,?,?,'pending')",
                (revision, identity, part, chat, text[start : start + 4000]),
            )
        db.execute(
            "UPDATE telegram_updates SET state='completed' WHERE revision=? AND update_id=?",
            (revision, identity),
        )

    async def process(self, profile):
        """Send one queued question to the same ProtoLink coordinator used by the web app."""
        with self.store.db() as db:
            row = db.execute(
                "SELECT update_id,payload FROM telegram_updates WHERE revision=? AND state='queued' ORDER BY update_id LIMIT 1",
                (profile["revision"],),
            ).fetchone()
            if not row:
                return False
            db.execute(
                "UPDATE telegram_updates SET state='processing' WHERE revision=? AND update_id=?",
                (profile["revision"], row[0]),
            )
        message = json.loads(row[1])
        text = message["text"]
        try:
            session = profile.get("session_id")
            if text.split()[0] in {"/start", "/help"}:
                answer = "Hello, I’m Sibyl. Ask about your workspace, markets or strategies. /new starts a fresh conversation; /status shows model readiness. Only your configured private user can talk to me. Replies may contain workspace information and use your selected AI provider."
            elif text == "/new":
                session = self.network.conversations.create()["id"]
                self._update(profile["revision"], session_id=session)
                answer = "Started a new Sibyl conversation."
            elif text == "/status":
                state = self.network.status()
                answer = f"Sibyl is {'ready' if state['ready'] else 'not ready'}. Model: {state.get('provider', 'none')} / {state.get('model', 'not configured')}."
            elif not self.network.status()["ready"]:
                answer = (
                    "Configure an AI model in Sibyl → Settings → AI models, then send your question again."
                )
            else:
                if not session:
                    session = self.network.conversations.create()["id"]
                    self._update(profile["revision"], session_id=session)
                result = await self.network.ask(
                    SibylRequest(message=text, session_id=session, request_id=message["request_id"])
                )
                answer = result.get("answer") or "This request did not finish. Please ask again in Sibyl."
            with self._lock:
                if self._current(profile["revision"]):
                    with self.store.db() as db:
                        self._complete(db, profile["revision"], row[0], message["chat_id"], answer)
                else:
                    with self.store.db() as db:
                        db.execute(
                            "UPDATE telegram_updates SET state='interrupted' WHERE revision=? AND update_id=?",
                            (profile["revision"], row[0]),
                        )
        except asyncio.CancelledError:
            raise
        except Exception:
            with self.store.db() as db:
                db.execute(
                    "UPDATE telegram_updates SET state='failed' WHERE revision=? AND update_id=?",
                    (profile["revision"], row[0]),
                )
            self._update(
                profile["revision"],
                error="Sibyl could not finish a Telegram answer. Check your model and send the question again.",
            )
        return True

    async def deliver(self, profile):
        """Claim one chunk; retry only explicit rate-limit rejections, never ambiguous writes."""
        with self.store.db() as db:
            row = db.execute(
                "SELECT * FROM telegram_outbox WHERE revision=? AND state='pending' ORDER BY update_id,part LIMIT 1",
                (profile["revision"],),
            ).fetchone()
            if not row:
                return False
            if row["next_attempt"] > time.time():
                return True
            db.execute(
                "UPDATE telegram_outbox SET state='sending',attempts=attempts+1 WHERE id=?", (row["id"],)
            )
        try:
            native = await self.client(profile).send(row["chat_id"], row["text"])
            with self.store.db() as db:
                db.execute(
                    "UPDATE telegram_outbox SET state='sent',native_id=? WHERE id=?", (native, row["id"])
                )
        except TelegramError as error:
            retry = error.retry_after and row["attempts"] < 5
            state = "pending" if retry else "uncertain" if error.ambiguous else "failed"
            with self.store.db() as db:
                db.execute(
                    "UPDATE telegram_outbox SET state=?,next_attempt=?,error=? WHERE id=?",
                    (state, time.time() + error.retry_after, str(error), row["id"]),
                )
                if state != "pending":
                    db.execute(
                        "UPDATE telegram_outbox SET state='blocked',error='An earlier chunk was not confirmed.' WHERE revision=? AND update_id=? AND state='pending'",
                        (profile["revision"], row["update_id"]),
                    )
            self._update(
                profile["revision"],
                error="Delivery is uncertain. Check your Telegram chat; this reply will not be resent automatically."
                if error.ambiguous
                else str(error),
            )
        return True

    async def tick(self):
        """Process one bounded step; a slow LLM never blocks other application workers."""
        async with self._tick_lock:
            profile = self.settings.profile()
            if not profile.get("enabled") or profile.get("next_attempt", 0) > time.time():
                return
            try:
                if await self.deliver(profile) or await self.process(profile):
                    return
                updates = await self.client(profile).receive(profile.get("offset"))
                self.ingest(profile, updates)
            except TelegramError as error:
                self._update(
                    profile["revision"],
                    error=str(error),
                    next_attempt=time.time() + (error.retry_after or 30),
                )

    async def run(self):
        """Poll until application shutdown; disabled connections perform no HTTP calls."""
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                profile = self.settings.profile()
                if profile:
                    self._update(
                        profile["revision"],
                        error="Telegram worker needs attention. Check the saved connection.",
                        next_attempt=time.time() + 30,
                    )
            await asyncio.sleep(0.5)

    async def close(self):
        """Release the HTTP pool after the owner has cancelled its worker task."""
        await self.http.aclose()
