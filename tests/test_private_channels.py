"""Isolated direct-HTTP channel contracts and native-runtime routing boundaries."""

import asyncio
import json
import time
from types import SimpleNamespace

import aiohttp
import httpx
import pytest
from test_telegram import FakeNetwork

from sibyl.messaging.channels.contracts import Batch, ChannelAction, ChannelError, Envelope, SignalSettings
from sibyl.messaging.channels.service import PrivateChannels
from sibyl.messaging.channels.signal import SignalClient
from sibyl.operations.recovery import prepare_recovery

OWNER = "987654321012345678"
BOT = "123456789012345678"
TARGET = "456789012345678901"
TOKEN = "PRIVATE-DISCORD-TOKEN"


@pytest.fixture
async def channels(store):
    requests = []

    def transport(request):
        requests.append(request)
        path = request.url.path
        payload = {
            "/api/v10/users/@me": {"id": BOT, "username": "Sibyl test bot", "bot": True},
            "/api/v10/oauth2/applications/@me": {"id": BOT},
            "/api/v10/users/@me/channels": {"id": TARGET, "type": 1, "recipients": [{"id": OWNER}]},
        }.get(path)
        if path.endswith("/messages"):
            payload = {"id": "777777777777777777", "channel_id": TARGET} if request.method == "POST" else []
        return httpx.Response(200, json=payload)

    http = httpx.AsyncClient(transport=httpx.MockTransport(transport))
    with store.db() as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS sibyl_turns(id TEXT, session_id TEXT,payload TEXT,created_at TEXT)"
        )
    service = PrivateChannels(store, FakeNetwork(), http)
    service.requests = requests
    service.save("discord", dict(bot_token=TOKEN, application_id=BOT, allowed_user_id=OWNER))
    yield service
    await service.close()


async def enable(service):
    revision = service.public("discord")["revision"]
    await service.action("discord", ChannelAction(revision=revision, action="enable"))
    return service.profile("discord")


def envelope(identity="one", **overrides):
    values = dict(
        id=identity,
        sender=OWNER,
        target=TARGET,
        text="Explain my portfolio",
        timestamp=time.time() + 0.01,
        private=True,
    )
    return Envelope(**(values | overrides))


async def test_private_routing_deduplicates_events_and_retains_provider_acceptance(channels, store):
    profile = await enable(channels)
    channels.ingest("discord", profile, Batch([envelope()], cursor="111"))
    channels.ingest("discord", profile, Batch([envelope()], cursor="111"))
    await channels.tick("discord")
    await channels.tick("discord")
    assert len(channels.network.calls) == 1
    assert channels.public("discord")["delivery"] == {"sent": 1}
    sent = [r for r in channels.requests if r.url.path.endswith("/messages") and r.method == "POST"]
    assert len(sent) == 1
    assert json.loads(sent[0].content)["allowed_mentions"] == {"parse": []}
    assert channels.profile("discord")["cursor"] == "111"
    public = json.dumps(channels.public("discord"))
    assert TOKEN not in public and "text" not in public
    with store.db() as db:
        raw = db.execute(
            "SELECT value FROM workspace_settings WHERE key='data:messaging:discord'"
        ).fetchone()[0]
    assert TOKEN.encode() not in raw


async def test_groups_wrong_senders_targets_old_dates_and_empty_content_are_ignored(channels):
    profile = await enable(channels)
    rows = [
        envelope("group", private=False),
        envelope("intruder", sender="0000"),
        envelope("other", target="0000"),
        envelope("old", timestamp=1),
        envelope("blank", text=""),
        envelope("long", text="a" * 4001),
    ]
    assert channels.ingest("discord", profile, Batch(rows, cursor="123"))
    assert channels.public("discord")["updates"] == {}
    assert channels.profile("discord")["cursor"] == "123"


async def test_pending_budget_never_acknowledges_an_unstored_event(channels):
    profile = await enable(channels)
    rows = [envelope(str(i)) for i in range(100)]
    channels.ingest("discord", profile, Batch(rows, cursor="100"))
    with pytest.raises(ChannelError, match="pending budget"):
        channels.ingest("discord", profile, Batch([envelope("overflow")], cursor="101"))
    assert channels.profile("discord")["cursor"] == "100"


async def test_pause_during_model_call_is_responsive_and_discards_late_answer(channels):
    profile = await enable(channels)
    channels.ingest("discord", profile, Batch([envelope()]))
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow(request):
        entered.set()
        await release.wait()
        return {"answer": "A late answer must not send."}

    channels.network.ask = slow
    work = asyncio.create_task(channels.tick("discord"))
    await entered.wait()
    await asyncio.wait_for(
        channels.action("discord", ChannelAction(revision=profile["revision"], action="pause")), 1
    )
    release.set()
    await work
    assert channels.public("discord")["delivery"] == {}
    assert channels.public("discord")["updates"] == {"interrupted": 1}


async def test_pause_during_enable_cannot_be_overwritten(channels):
    initial = channels.profile("discord")
    client = await channels.client("discord", initial)
    entered, release = asyncio.Event(), asyncio.Event()

    async def identity():
        entered.set()
        await release.wait()
        return dict(bot_id=BOT, target=TARGET)

    client.identity = identity
    work = asyncio.create_task(
        channels.action("discord", ChannelAction(revision=initial["revision"], action="enable"))
    )
    await entered.wait()
    await channels.action("discord", ChannelAction(revision=initial["revision"], action="pause"))
    release.set()
    with pytest.raises(ValueError, match="pause controls changed"):
        await work
    assert not channels.public("discord")["enabled"]


async def test_unknown_send_never_retries_and_blocks_remaining_parts(channels):
    profile = await enable(channels)

    async def ask(request):
        return {"answer": "x" * 5000}

    channels.network.ask = ask
    channels.ingest("discord", profile, Batch([envelope()]))
    await channels.tick("discord")
    client = await channels.client("discord", profile)
    calls = []

    async def uncertain(target, text):
        calls.append(1)
        raise ChannelError("Provider did not confirm.", ambiguous=True)

    client.send = uncertain
    await channels.tick("discord")
    await channels.tick("discord")
    assert len(calls) == 1
    assert channels.public("discord")["delivery"] == {"blocked": 2, "uncertain": 1}


async def test_only_definitive_rate_limit_is_retried(channels):
    profile = await enable(channels)
    channels.ingest("discord", profile, Batch([envelope()]))
    await channels.tick("discord")
    client = await channels.client("discord", profile)

    async def limited(target, text):
        raise ChannelError("Rate limited.", retry_after=20)

    client.send = limited
    await channels.tick("discord")
    assert channels.public("discord")["delivery"] == {"pending": 1}
    assert channels.receipts("discord")["items"][0]["attempts"] == 1


async def test_credentials_cannot_change_enabled_recipient_and_restore_quarantines(channels):
    profile = await enable(channels)
    with pytest.raises(ValueError, match="Pause"):
        channels.save(
            "discord", dict(bot_token=TOKEN, application_id=BOT, allowed_user_id=OWNER), profile["revision"]
        )
    channels.ingest("discord", profile, Batch([envelope()]))
    await channels.tick("discord")
    prepare_recovery(channels.store, "isolated-backup")
    assert not channels.public("discord")["enabled"]
    assert channels.public("discord")["delivery"] == {"uncertain": 1}


async def test_saved_channel_can_enable_without_a_model(channels):
    channels.network.status = lambda: {"ready": False}
    profile = await enable(channels)
    channels.ingest("discord", profile, Batch([envelope()]))
    await channels.tick("discord")
    await channels.tick("discord")
    assert not channels.network.calls
    sent = [r for r in channels.requests if r.url.path.endswith("/messages") and r.method == "POST"]
    assert "Configure an AI model" in json.loads(sent[0].content)["content"]


async def test_slack_event_ack_happens_after_durable_ingestion(channels, monkeypatch):
    settings = dict(bot_token="SLACK-SECRET", app_token="APP-SECRET", allowed_user_id="U12345678")
    channels.save("slack", settings)
    profile = channels.profile("slack")
    profile.update(
        enabled=True,
        control="test-control",
        enabled_at=time.time() - 1,
        verified=True,
        target="D12345678",
        team_id="T12345678",
    )
    channels.store.save_data_profile("messaging:slack", profile)
    client = await channels.client("slack", profile)
    frame = dict(
        type="events_api",
        envelope_id="envelope-one",
        payload=dict(
            team_id="T12345678",
            event_id="EvOne",
            event=dict(
                type="message",
                channel_type="im",
                channel="D12345678",
                user="U12345678",
                ts=str(time.time()),
                text="What does Sibyl do?",
            ),
        ),
    )

    class Socket:
        closed = False

        async def receive(self, **kwargs):
            return SimpleNamespace(type=aiohttp.WSMsgType.TEXT, data=json.dumps(frame))

        async def send_json(self, body):
            with channels.store.db() as db:
                assert (
                    db.execute("SELECT COUNT(*) FROM channel_messages WHERE channel='slack'").fetchone()[0]
                    == 1
                )
            assert body == {"envelope_id": "envelope-one"}

        async def close(self):
            self.closed = True

    client.socket = Socket()
    await channels.tick("slack")
    assert channels.public("slack")["updates"] == {"queued": 1}


async def test_signal_native_account_and_private_sender_are_preserved():
    aci = "12345678-1234-1234-1234-123456789abc"
    profile = dict(account="+15551234567", allowed_sender_aci=aci, bridge_url="http://127.0.0.1:8080")
    http = httpx.AsyncClient()
    client = SignalClient(profile, http)
    payload = dict(
        jsonrpc="2.0",
        method="receive",
        params=dict(
            account=profile["account"],
            envelope=dict(
                sourceUuid=aci,
                timestamp=int(time.time() * 1000),
                sourceDevice=1,
                dataMessage=dict(message="Hello"),
            ),
        ),
    )
    lines = iter([b"id: event-one\n", b"data: " + json.dumps(payload).encode() + b"\n", b"\n"])

    class Content:
        async def readline(self):
            return next(lines)

    class Response:
        closed = False
        content = Content()

        def close(self):
            self.closed = True

    client.response = Response()
    batch = await client.receive(None)
    assert batch.cursor == "event-one"
    assert batch.messages[0].sender == aci and batch.messages[0].target == aci
    assert batch.messages[0].text == "Hello"
    await client.close()
    await http.aclose()


@pytest.mark.parametrize(
    "url",
    [
        "https://localhost:8080",
        "http://external.example:8080",
        "http://127.0.0.1:8080/path",
        "http://user:password@127.0.0.1:8080",
    ],
)
def test_signal_bridge_does_not_accept_remote_or_credential_urls(url):
    with pytest.raises(ValueError):
        SignalSettings(
            bridge_url=url, account="+15551234567", allowed_sender_aci="12345678-1234-1234-1234-123456789abc"
        )


def test_http_setup_reports_implemented_channels_and_never_saved_secrets(client):
    channels = client.get("/api/v1/settings/messaging").json()["channels"]
    assert {row["id"] for row in channels if row["status"] == "available"} == {
        "telegram",
        "discord",
        "slack",
        "signal",
        "whatsapp",
        "email",
    }
    response = client.put(
        "/api/v1/settings/messaging/channels/discord",
        json={"settings": dict(bot_token=TOKEN, application_id=BOT, allowed_user_id=OWNER)},
    )
    assert response.status_code == 200 and TOKEN not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert not response.json()["enabled"]
    assert client.get("/api/v1/settings/messaging/channels/not-a-client").status_code == 404
