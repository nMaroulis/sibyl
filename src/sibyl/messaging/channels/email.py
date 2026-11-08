"""IMAP/SMTP private text through standard-library clients and verified TLS.

A shared subject pairing phrase supplements the fixed sender/recipient binding:
From headers alone do not authenticate a human. No incoming Reply-To, CC, remote
content, attachments or model-selected recipients can redirect a reply.
"""

import asyncio
import email.policy
import hmac
import imaplib
import re
import smtplib
import ssl
import time
from contextlib import contextmanager
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, make_msgid

from sibyl.messaging.channels.contracts import Batch, ChannelError, Envelope

MAX_MAIL = 128 * 1024


class EmailClient:
    chunk_units = 12000

    def __init__(self, profile, http):
        self.profile = profile
        self.inflight = set()

    async def _thread(self, method, *args):
        task = asyncio.create_task(asyncio.to_thread(method, *args))
        self.inflight.add(task)
        task.add_done_callback(self.inflight.discard)
        return await asyncio.shield(task)

    @contextmanager
    def imap(self):
        p = self.profile
        server = None
        try:
            if p["imap_security"] == "TLS":
                server = imaplib.IMAP4_SSL(
                    p["imap_host"], p["imap_port"], ssl_context=ssl.create_default_context(), timeout=15
                )
            else:
                server = imaplib.IMAP4(p["imap_host"], p["imap_port"], timeout=15)
                server.starttls(ssl_context=ssl.create_default_context())
            server.login(p["imap_username"], p["imap_password"])
            status, _ = server.select('"' + p["imap_folder"] + '"', readonly=True)
            if status != "OK":
                raise ChannelError("The configured IMAP folder could not be opened read-only.")
            yield server
        finally:
            if server:
                try:
                    server.logout()
                except (imaplib.IMAP4.error, OSError):
                    pass

    @contextmanager
    def smtp(self):
        p = self.profile
        server = None
        try:
            if p["smtp_security"] == "TLS":
                server = smtplib.SMTP_SSL(
                    p["smtp_host"], p["smtp_port"], context=ssl.create_default_context(), timeout=15
                )
            else:
                server = smtplib.SMTP(p["smtp_host"], p["smtp_port"], timeout=15)
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            server.login(p["smtp_username"], p["smtp_password"])
            yield server
        finally:
            if server:
                try:
                    server.quit()
                except (smtplib.SMTPException, OSError):
                    server.close()

    @staticmethod
    def numbers(server):
        values = []
        for field in ("UIDVALIDITY", "UIDNEXT"):
            _, data = server.response(field)
            value = data[0].decode("ascii") if data and isinstance(data[0], bytes) else ""
            if not value.isdecimal() or int(value) < 1:
                raise ChannelError("The mailbox did not provide stable IMAP UID validity and next identity.")
            values.append(value)
        return values

    def _identity(self):
        try:
            with self.imap() as server:
                validity, following = self.numbers(server)
                if server.noop()[0] != "OK":
                    raise ChannelError("IMAP did not confirm mailbox access.")
            with self.smtp() as server:
                if server.noop()[0] != 250:
                    raise ChannelError("SMTP did not confirm mailbox access.")
            return dict(
                bot_id=self.profile["email_address"],
                bot_username=self.profile["email_address"],
                target=self.profile["allowed_sender"],
                cursor=f"{validity}:{following}",
            )
        except (imaplib.IMAP4.error, smtplib.SMTPException, OSError, ValueError):
            raise ChannelError(
                "Mailbox authentication or TLS access failed. Check the saved hosts, ports and app passwords."
            ) from None

    async def identity(self):
        """Authenticate both servers without reading message bodies or sending mail."""
        return await self._thread(self._identity)

    def _receive(self, cursor):
        try:
            with self.imap() as server:
                validity, _ = self.numbers(server)
                if (
                    not cursor
                    or not re.fullmatch(r"[0-9]+:[0-9]+", cursor)
                    or cursor.split(":")[0] != validity
                ):
                    raise ChannelError(
                        "Mailbox UID validity changed. Pause, review the mailbox and check/enable a fresh receive boundary."
                    )
                following = int(cursor.split(":")[1])
                status, data = server.uid("SEARCH", None, f"UID {following}:*")
                if status != "OK" or not data or len(data[0]) > 32768:
                    raise ChannelError("The IMAP pending identity page is unavailable or saturated.")
                identities = sorted(
                    {int(value) for value in data[0].split() if value.isdigit() and int(value) >= following}
                )[:10]
                messages = []
                for identity in identities:
                    status, rows = server.uid("FETCH", str(identity), "(UID RFC822.SIZE)")
                    metadata = (
                        b" ".join(row for row in rows if isinstance(row, bytes)) if status == "OK" else b""
                    )
                    size = re.search(rb"RFC822.SIZE ([0-9]+)", metadata)
                    native_uid = re.search(rb"UID ([0-9]+)", metadata)
                    if not size or not native_uid or int(native_uid[1]) != identity:
                        raise ChannelError("IMAP did not confirm the exact message identity and size.")
                    if int(size[1]) > MAX_MAIL:
                        following = identity + 1
                        continue
                    status, rows = server.uid(
                        "FETCH", str(identity), f"(UID INTERNALDATE BODY.PEEK[]<0.{MAX_MAIL}>)"
                    )
                    literals = [row for row in rows if isinstance(row, tuple)] if status == "OK" else []
                    if len(literals) != 1 or len(literals[0][1]) > MAX_MAIL:
                        raise ChannelError("IMAP did not return one bounded message body.")
                    facts, raw = literals[0]
                    native_uid = re.search(rb"UID ([0-9]+)", facts)
                    if not native_uid or int(native_uid[1]) != identity:
                        raise ChannelError("IMAP returned a different message identity.")
                    dates = imaplib.Internaldate2tuple(facts)
                    if dates is None:
                        raise ChannelError("IMAP did not confirm the message delivery time.")
                    stamp = time.mktime(dates)
                    message = BytesParser(policy=email.policy.default).parsebytes(raw)
                    senders = getaddresses(message.get_all("from", []))
                    subject = str(message.get("subject", ""))
                    expected = "[Sibyl:" + self.profile["reply_code"] + "]"
                    # Compare the full fixed authorization prefix; never pass it to the LLM.
                    authorized = (
                        len(senders) == 1
                        and senders[0][1].casefold() == self.profile["allowed_sender"]
                        and hmac.compare_digest(subject[: len(expected)].encode(), expected.encode())
                        and str(message.get("Auto-Submitted", "no")).casefold() == "no"
                        and not message.get("List-Id")
                    )
                    if authorized:
                        part = (
                            message.get_body(preferencelist=("plain",)) if message.is_multipart() else message
                        )
                        if (
                            part
                            and part.get_content_type() == "text/plain"
                            and part.get_content_disposition() != "attachment"
                        ):
                            try:
                                text = part.get_content()
                            except (LookupError, UnicodeError):
                                text = ""
                            if isinstance(text, str):
                                messages.append(
                                    Envelope(
                                        f"{validity}:{identity}",
                                        self.profile["allowed_sender"],
                                        self.profile["allowed_sender"],
                                        text.strip(),
                                        stamp,
                                    )
                                )
                    following = identity + 1
                return Batch(messages, f"{validity}:{following}")
        except (imaplib.IMAP4.error, OSError, ValueError):
            raise ChannelError(
                "IMAP could not confirm this read. The local cursor was not advanced."
            ) from None

    async def receive(self, cursor):
        return await self._thread(self._receive, cursor)

    async def acknowledge(self, batch):
        """Only local UID progression is committed; no mailbox flags or messages are changed."""

    def _send(self, target, text):
        if target != self.profile["allowed_sender"]:
            raise ChannelError("The saved private recipient changed.")
        message = EmailMessage()
        message["From"] = self.profile["email_address"]
        message["To"] = target
        message["Subject"] = "Sibyl reply"
        message["Message-ID"] = make_msgid(domain=self.profile["email_address"].split("@")[1])
        message["Auto-Submitted"] = "auto-replied"
        message.set_content(text)
        try:
            with self.smtp() as server:
                refused = server.send_message(
                    message, from_addr=self.profile["email_address"], to_addrs=[target]
                )
                if refused:
                    raise ChannelError("SMTP rejected the configured recipient.")
            return str(message["Message-ID"])
        except (
            smtplib.SMTPRecipientsRefused,
            smtplib.SMTPSenderRefused,
            smtplib.SMTPDataError,
            smtplib.SMTPAuthenticationError,
        ):
            raise ChannelError(
                "SMTP explicitly rejected the reply. Check the mailbox and private recipient."
            ) from None
        except (smtplib.SMTPException, OSError):
            raise ChannelError(
                "SMTP did not confirm reply acceptance. Check the mailbox before resending.", ambiguous=True
            ) from None

    async def send(self, target, text):
        return await self._thread(self._send, target, text)

    async def close(self):
        """Drain standard-library calls; cancellation cannot kill an admitted SMTP thread."""
        if self.inflight:
            await asyncio.gather(*list(self.inflight), return_exceptions=True)
