"""Authenticated webhook and TLS mailbox contracts, entirely offline."""

import hashlib
import hmac
import json
import ssl
import time
from email.message import EmailMessage
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from test_telegram import FakeNetwork

from sibyl.api.app import create_app
from sibyl.messaging.channels.contracts import ChannelAction, ChannelError, EmailSettings
from sibyl.messaging.channels.email import EmailClient
from sibyl.messaging.channels.service import PrivateChannels
from sibyl.messaging.channels.whatsapp import WhatsAppClient

WA = dict(
    api_version="v24.0",
    access_token="PRIVATE-META-TOKEN",
    phone_number_id="1234567890",
    app_secret="PRIVATE-META-APP-SECRET",
    verify_token="PRIVATE-META-VERIFY",
    allowed_phone_number="15551234567",
)
MAIL = dict(
    email_address="sibyl@example.org",
    allowed_sender="owner@example.org",
    reply_code="Private_Pairing_Phrase_123456",
    imap_host="imap.example.org",
    imap_port=993,
    imap_security="TLS",
    imap_username="sibyl@example.org",
    imap_password="PRIVATE-IMAP-SECRET",
    imap_folder="INBOX",
    smtp_host="smtp.example.org",
    smtp_port=587,
    smtp_security="STARTTLS",
    smtp_username="sibyl@example.org",
    smtp_password="PRIVATE-SMTP-SECRET",
)


def webhook(**overrides):
    row = dict(
        id="wamid.one",
        type="text",
        timestamp=str(int(time.time())),
        **{"from": WA["allowed_phone_number"]},
        text={"body": "Explain my account"},
    )
    row.update(overrides)
    return dict(
        object="whatsapp_business_account",
        entry=[
            dict(
                changes=[
                    dict(
                        field="messages",
                        value=dict(metadata={"phone_number_id": WA["phone_number_id"]}, messages=[row]),
                    )
                ]
            )
        ],
    )


def signature(raw):
    return "sha256=" + hmac.new(WA["app_secret"].encode(), raw, hashlib.sha256).hexdigest()


def configure(service, channel, values):
    service.save(channel, values)
    profile = service.profile(channel)
    service._update(
        channel,
        profile["revision"],
        enabled=True,
        verified=True,
        enabled_at=time.time() - 2,
        target=values["allowed_phone_number"] if channel == "whatsapp" else values["allowed_sender"],
    )
    return service.profile(channel)


def test_only_the_exact_webhook_bypasses_workspace_auth_and_requires_signature(settings):
    config = settings.model_copy(update={"api_token": SecretStr("WORKSPACE-PRIVATE")})
    with TestClient(create_app(config)) as client:
        channels = client.app.state.services.private_channels
        configure(channels, "whatsapp", WA)
        assert client.get("/api/v1/settings/messaging").status_code == 401
        assert client.get("/api/v1/webhooks/whatsapp/").status_code == 401
        assert client.put("/api/v1/webhooks/whatsapp").status_code == 401
        assert (
            client.get(
                "/api/v1/webhooks/whatsapp",
                params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "123"},
            ).status_code
            == 403
        )
        verified = client.get(
            "/api/v1/webhooks/whatsapp",
            params={"hub.mode": "subscribe", "hub.verify_token": WA["verify_token"], "hub.challenge": "123"},
        )
        assert verified.status_code == 200 and verified.text == "123"
        raw = json.dumps(webhook()).encode()
        assert client.post("/api/v1/webhooks/whatsapp", content=raw).status_code == 403
        assert (
            client.post(
                "/api/v1/webhooks/whatsapp", content=raw, headers={"x-hub-signature-256": signature(raw)}
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/webhooks/whatsapp", content=raw, headers={"x-hub-signature-256": signature(raw)}
            ).status_code
            == 200
        )
        assert channels.public("whatsapp")["updates"] == {"queued": 1}
        altered = raw.replace(b"Explain", b"Rewrite")
        assert (
            client.post(
                "/api/v1/webhooks/whatsapp", content=altered, headers={"x-hub-signature-256": signature(raw)}
            ).status_code
            == 403
        )
        assert client.post("/api/v1/webhooks/whatsapp", content=b"x" * (128 * 1024 + 1)).status_code == 413
        foreign = json.dumps(webhook(**{"from": "19999999999"})).encode()
        assert (
            client.post(
                "/api/v1/webhooks/whatsapp",
                content=foreign,
                headers={"x-hub-signature-256": signature(foreign)},
            ).status_code
            == 200
        )
        assert channels.public("whatsapp")["updates"] == {"queued": 1}


async def test_whatsapp_native_identity_base_origin_recipient_and_reply_window():
    requests = []

    def transport(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"id": WA["phone_number_id"], "verified_name": "Test business"})
        return httpx.Response(200, json={"messages": [{"id": "wamid.sent"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        profile = WA | dict(last_inbound_at=time.time())
        client = WhatsAppClient(profile, http)
        assert (await client.identity())["target"] == WA["allowed_phone_number"]
        assert await client.send(WA["allowed_phone_number"], "A reply") == "wamid.sent"
        assert str(requests[-1].url) == f"https://graph.facebook.com/v24.0/{WA['phone_number_id']}/messages"
        assert requests[-1].headers["authorization"] == "Bearer " + WA["access_token"]
        sent = json.loads(requests[-1].content)
        assert sent["to"] == WA["allowed_phone_number"] and sent["text"]["preview_url"] is False
        with pytest.raises(ChannelError, match="recipient changed"):
            await client.send("other", "No")
        profile["last_inbound_at"] = time.time() - 24 * 3600
        with pytest.raises(ChannelError, match="window expired"):
            await client.send(WA["allowed_phone_number"], "No")
        assert len(requests) == 2


def test_whatsapp_oversized_nested_batches_are_rejected_not_silently_truncated():
    client = WhatsAppClient(WA, None)
    body = webhook()
    body["entry"][0]["changes"][0]["value"]["messages"] *= 101
    with pytest.raises(ChannelError, match="batch exceeds"):
        client.messages(body)
    assert client.messages(webhook(type="image")).messages == []


@pytest.fixture
def mail_servers(monkeypatch):
    incoming = []
    sent = []
    calls = []
    validity = ["777"]
    internal = time.strftime("%d-%b-%Y %H:%M:%S +0000", time.gmtime())

    class IMAP:
        def __init__(self, host, port, **kwargs):
            calls.append(("imap", host, port, kwargs))
            if "ssl_context" in kwargs:
                assert (
                    kwargs["ssl_context"].verify_mode == ssl.CERT_REQUIRED
                    and kwargs["ssl_context"].check_hostname
                )

        def login(self, user, password):
            assert (user, password) == (MAIL["imap_username"], MAIL["imap_password"])

        def select(self, folder, readonly):
            assert folder == '"INBOX"' and readonly is True
            return "OK", [b"3"]

        def response(self, field):
            return field, [validity[0].encode() if field == "UIDVALIDITY" else b"10"]

        def noop(self):
            return "OK", [b"healthy"]

        def logout(self):
            pass

        def uid(self, command, *args):
            calls.append((command, args))
            if command == "SEARCH":
                return "OK", [b" ".join(str(i + 10).encode() for i in range(len(incoming)))]
            index = int(args[0])
            raw = incoming[index - 10]
            if args[1] == "(UID RFC822.SIZE)":
                return "OK", [f"1 (UID {index} RFC822.SIZE {len(raw)})".encode()]
            metadata = f'1 (UID {index} INTERNALDATE "{internal}" BODY[] {{{len(raw)}}})'.encode()
            return "OK", [(metadata, raw), b")"]

    class SMTP:
        def __init__(self, host, port, **kwargs):
            calls.append(("smtp", host, port, kwargs))

        def ehlo(self):
            return 250, b"hello"

        def starttls(self, context):
            assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname

        def login(self, user, password):
            assert (user, password) == (MAIL["smtp_username"], MAIL["smtp_password"])

        def noop(self):
            return 250, b"healthy"

        def quit(self):
            pass

        def close(self):
            pass

        def send_message(self, message, *, from_addr, to_addrs):
            assert from_addr == MAIL["email_address"] and to_addrs == [MAIL["allowed_sender"]]
            assert "cc" not in message and "bcc" not in message and "reply-to" not in message
            sent.append(message)
            return {}

    monkeypatch.setattr("sibyl.messaging.channels.email.imaplib.IMAP4_SSL", IMAP)
    monkeypatch.setattr("sibyl.messaging.channels.email.smtplib.SMTP", SMTP)
    return SimpleNamespace(incoming=incoming, sent=sent, calls=calls, validity=validity)


def mail(sender="owner@example.org", code=None, body="Explain my portfolio", **headers):
    message = EmailMessage()
    message["From"] = sender
    message["To"] = MAIL["email_address"]
    message["Subject"] = "[Sibyl:" + (MAIL["reply_code"] if code is None else code) + "] My question"
    message["Reply-To"] = "attacker@example.net"
    for key, value in headers.items():
        message[key] = value
    message.set_content(body)
    return message.as_bytes()


async def test_mailbox_tls_read_only_uid_binding_pairing_and_fixed_smtp_recipient(mail_servers):
    mail_servers.incoming[:] = [mail(code="wrong"), mail(sender="foreign@example.org"), mail()]
    client = EmailClient(MAIL, None)
    checked = await client.identity()
    assert checked["cursor"] == "777:10" and checked["target"] == MAIL["allowed_sender"]
    batch = await client.receive(checked["cursor"])
    assert batch.cursor == "777:13"
    assert [row.id for row in batch.messages] == ["777:12"]
    assert batch.messages[0].text == "Explain my portfolio"
    assert MAIL["reply_code"] not in batch.messages[0].text
    accepted = await client.send(MAIL["allowed_sender"], "A grounded reply")
    assert accepted.startswith("<") and len(mail_servers.sent) == 1
    assert mail_servers.sent[0]["To"] == MAIL["allowed_sender"]
    assert mail_servers.sent[0]["Auto-Submitted"] == "auto-replied"
    with pytest.raises(ChannelError, match="recipient changed"):
        await client.send("attacker@example.net", "No")
    mail_servers.validity[0] = "778"
    with pytest.raises(ChannelError, match="UID validity changed"):
        await client.receive(batch.cursor)
    await client.close()


async def test_email_pairing_secret_is_encrypted_and_never_in_public_projection(store, mail_servers):
    with store.db() as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS sibyl_turns(id TEXT, session_id TEXT,payload TEXT,created_at TEXT)"
        )
    http = httpx.AsyncClient()
    channels = PrivateChannels(store, FakeNetwork(), http)
    channels.save("email", MAIL)
    public = json.dumps(channels.public("email"))
    for secret in (MAIL["reply_code"], MAIL["imap_password"], MAIL["smtp_password"]):
        assert secret not in public
    profile = channels.profile("email")
    await channels.action("email", ChannelAction(revision=profile["revision"], action="enable"))
    mail_servers.incoming.append(mail())
    await channels.tick("email")
    await channels.tick("email")
    await channels.tick("email")
    assert len(channels.network.calls) == 1
    assert MAIL["reply_code"] not in channels.network.calls[0].message
    assert channels.public("email")["delivery"] == {"sent": 1}
    await channels.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"reply_code": "short"},
        {"allowed_sender": "Owner <owner@example.org>"},
        {"email_address": "same@example.org", "allowed_sender": "same@example.org"},
        {"imap_host": "imap.example.org/path"},
    ],
)
def test_email_settings_reject_ambiguous_identity_and_control_injection(changes):
    with pytest.raises(ValueError):
        EmailSettings(**(MAIL | changes))
