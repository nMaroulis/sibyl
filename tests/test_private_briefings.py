"""Native research reports handed to checked private clients, with no live sends.

The full investigation/model snapshot, calendar, outbox and native serializers
run. Provider identities and writes use controlled HTTP/TLS SMTP responses.
"""

import asyncio
import json
import time
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from protolink import Task
from test_briefing_schedules import definition, finish, model
from test_private_alert_delivery import ACI, BOT, OWNER, SLACK_ID, TARGET
from test_whatsapp_email import MAIL, WA
from test_whatsapp_email import mail_servers as mail_servers

from sibyl.investigations.scheduling.contracts import BriefingAction, EditBriefing, RunBriefing
from sibyl.investigations.scheduling.service import BriefingScheduler
from sibyl.messaging.channels.contracts import ChannelAction


@pytest.fixture
def private_workflow(manual_client, monkeypatch, mail_servers):
    client = manual_client
    services = client.app.state.services
    scheduler = services.briefings
    scheduler.clock = lambda: datetime.now(UTC)
    state = {"calls": [], "mode": None}

    async def transport(request):
        state["calls"].append(request)
        body = json.loads(request.content) if request.content else {}
        path = request.url.path
        writing = any(key in body for key in ("content", "text")) or body.get("method") == "send"
        if writing and state["mode"]:
            return await state["mode"](request, body)
        if path == "/api/v10/users/@me":
            value = {"id": BOT, "bot": True, "username": "Controlled Discord"}
        elif path == "/api/v10/oauth2/applications/@me":
            value = {"id": BOT}
        elif path == "/api/v10/users/@me/channels":
            value = {"id": TARGET, "type": 1, "recipients": [{"id": OWNER}]}
        elif path.endswith("/messages") and request.url.host == "discord.com":
            value = {"id": "777777777777777777", "channel_id": TARGET}
        elif path.endswith("auth.test"):
            value = {
                "ok": True,
                "bot_id": "B123456789",
                "user_id": "U123456789",
                "team_id": "T123456789",
                "user": "Controlled Slack",
            }
        elif path.endswith("apps.connections.open"):
            value = {"ok": True, "url": "wss://wss-primary.slack.com/controlled"}
        elif path.endswith("conversations.open"):
            value = {"ok": True, "channel": {"id": "D123456789"}}
        elif path.endswith("chat.postMessage"):
            value = {"ok": True, "channel": "D123456789", "ts": SLACK_ID}
        elif path.endswith("rpc"):
            value = {
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": [{"number": "+15551230000"}]
                if body["method"] == "listAccounts"
                else {"timestamp": 1799999999123},
            }
        elif path.endswith("/messages"):
            value = {"messages": [{"id": "wamid.controlled-briefing"}]}
        else:
            value = {"id": WA["phone_number_id"], "verified_name": "Controlled phone"}
        return httpx.Response(200, json=value)

    profiles = {
        "discord": dict(bot_token="PRIVATE-WORKFLOW-DISCORD", application_id=BOT, allowed_user_id=OWNER),
        "slack": dict(
            bot_token="PRIVATE-WORKFLOW-SLACK", app_token="PRIVATE-WORKFLOW-APP", allowed_user_id="U987654321"
        ),
        "signal": dict(account="+15551230000", allowed_sender_aci=ACI),
        "whatsapp": WA,
        "email": MAIL,
    }
    channels = services.private_channels

    async def connect():
        await channels.http.aclose()
        channels.http = httpx.AsyncClient(transport=httpx.MockTransport(transport))
        for channel, values in profiles.items():
            channels.save(channel, values)
            await channels.action(
                channel, ChannelAction(revision=channels.profile(channel)["revision"], action="enable")
            )
        channels._update("whatsapp", channels.profile("whatsapp")["revision"], last_inbound_at=time.time())

    client.portal.call(connect)
    model(client, monkeypatch)
    return client, scheduler, channels, state, mail_servers, profiles


def create(workflow, channel="discord", **values):
    client, _, _, _, _, _ = workflow
    entry = definition(client)
    target = next(
        row["target"]
        for row in client.get("/api/v1/message-deliveries/targets").json()["items"]
        if row["channel"] == channel
    )
    response = client.post(
        f"/api/v1/investigations/{entry['id']}/schedules",
        json={"channel": channel, "private_target": target, **values},
    )
    assert response.status_code == 201, response.text
    return entry, response.json()


def run(workflow, policy):
    client, service, _, _, _, _ = workflow
    return client.portal.call(
        service.run_now, policy["id"], RunBriefing(revision=policy["revision"], request_id=uuid4().hex)
    )


def deliver(workflow, channel):
    client, service, channels, _, _, _ = workflow

    async def send():
        async with channels.locks[channel]:
            return await service.messaging.notifications.deliver(
                service.messaging.notifications.routes.profile(channel), channel=channel
            )

    return client.portal.call(send)


def native_sends(state):
    return [
        request
        for request in state["calls"]
        if any(key in (json.loads(request.content) if request.content else {}) for key in ("content", "text"))
        or (request.content and json.loads(request.content).get("method") == "send")
    ]


@pytest.mark.parametrize("channel", ["discord", "slack", "signal", "whatsapp", "email"])
def test_native_completed_report_delivers_once_with_actual_private_receipts(private_workflow, channel):
    client, scheduler, channels, state, mail, _ = private_workflow
    entry, policy = create(private_workflow, channel)
    assert policy["channel"] == channel and not policy["telegram"]
    assert policy["telegram_binding"] is None and policy["delivery_binding"]
    queued = run(private_workflow, policy)
    completed = finish(client, scheduler, policy)
    assert completed["delivery_requested"] and completed["delivery_channel"] == channel
    assert completed["status"] == "completed" and completed["delivery"]["status"] == "pending"
    assert "delivery_snapshot" not in completed
    for _ in range(completed["delivery"]["total_parts"]):
        deliver(private_workflow, channel)
    deliver(private_workflow, channel)
    latest = scheduler.detail(policy["id"])["occurrences"][0]
    assert latest["delivery"]["status"] == "sent" and latest["report_available"]
    assert latest["delivery"]["channel"] == channel
    assert latest["run_id"] == queued["id"]
    part = latest["delivery"]["parts"][0]
    assert part["native_id"] is None and isinstance(part["provider_id"], str)
    assert channels.public(channel)["briefings"] == {"sent": 1}
    if channel == "slack":
        assert part["provider_id"] == SLACK_ID
    if channel == "email":
        assert len(mail.sent) == 1 and "Simulated model" in mail.sent[0].get_content()
        assert mail.sent[0]["Subject"] == "Sibyl notification"
        assert MAIL["reply_code"] not in mail.sent[0].as_string()
    else:
        assert len(native_sends(state)) == latest["delivery"]["total_parts"]
        assert "Simulated model" in json.dumps(json.loads(native_sends(state)[0].content))
    network = client.app.state.services.agents.network
    result = client.portal.call(
        network.client.send_task,
        network.cards["sibyl"].url,
        Task.create_tool_call("briefing_schedules", {"schedule_id": policy["id"]}),
    )
    result.raise_for_status()
    evidence = result.get_last_item().parts[-1].as_tool_output().result
    assert evidence["schedules"][0]["delivery_channel"] == channel
    assert evidence["schedules"][0]["recent_occurrences"][0]["delivery"]["channel"] == channel
    private = json.dumps(evidence)
    for key in (
        "recipient_id",
        "delivery_binding",
        "delivery_snapshot",
        "control_id",
        "private_target",
        "PRIVATE-WORKFLOW",
        MAIL["reply_code"],
    ):
        assert key not in private
    assert "private_target" not in json.dumps(client.get(f"/api/v1/briefing-schedules/{policy['id']}").json())


def test_save_is_lazy_and_rejects_unchecked_stale_conflicting_or_unsupported_targets(
    private_workflow, monkeypatch
):
    client, _, _, state, _, _ = private_workflow
    entry = definition(client)
    monkeypatch.setattr(
        "sibyl.agents.utils.registry.create_llm",
        lambda *a, **kw: pytest.fail("Saving a schedule instantiated a model"),
    )
    target = next(
        row["target"]
        for row in client.get("/api/v1/message-deliveries/targets").json()["items"]
        if row["channel"] == "discord"
    )
    calls = len(state["calls"])
    bad = [
        {"channel": "discord"},
        {"channel": "discord", "private_target": target, "message_format": "document"},
        {"channel": "discord", "private_target": target, "telegram": True},
        {"channel": "telegram", "telegram": False, "telegram_target": {"bot_id": 1, "user_id": 1}},
        {"channel": None, "private_target": target},
    ]
    for values in bad:
        response = client.post(f"/api/v1/investigations/{entry['id']}/schedules", json=values)
        assert response.status_code == 422, response.text
    stale = client.post(
        f"/api/v1/investigations/{entry['id']}/schedules",
        json={"channel": "discord", "private_target": {**target, "revision": "f" * 32}},
    )
    assert stale.status_code == 409
    saved = client.post(
        f"/api/v1/investigations/{entry['id']}/schedules",
        json={"channel": "discord", "private_target": target, "enabled": False},
    )
    assert saved.status_code == 201 and saved.json()["status"] == "paused"
    assert len(state["calls"]) == calls


@pytest.mark.parametrize("transition", ["pause_resume", "replace", "paused_at_acceptance"])
def test_queued_binding_cannot_cross_a_connection_generation(private_workflow, transition):
    client, scheduler, channels, state, _, profiles = private_workflow
    _, policy = create(private_workflow)
    initial = channels.profile("discord")
    if transition == "paused_at_acceptance":
        client.portal.call(
            channels.action, "discord", ChannelAction(revision=initial["revision"], action="pause")
        )
    run(private_workflow, policy)
    if transition != "paused_at_acceptance":
        client.portal.call(
            channels.action, "discord", ChannelAction(revision=initial["revision"], action="pause")
        )
    if transition == "replace":
        channels.save(
            "discord",
            {**profiles["discord"], "bot_token": "REPLACED-PRIVATE-TOKEN"},
            revision=initial["revision"],
        )
    current = channels.profile("discord")
    client.portal.call(
        channels.action, "discord", ChannelAction(revision=current["revision"], action="enable")
    )
    completed = finish(client, scheduler, policy)
    assert completed["status"] == "completed" and completed["delivery"]["status"] == "skipped"
    assert "after this briefing was accepted" in completed["delivery"]["error"]
    deliver(private_workflow, "discord")
    assert native_sends(state) == []


def test_pause_during_an_actual_investigation_keeps_its_finished_report_local(private_workflow, monkeypatch):
    client, scheduler, channels, state, _, _ = private_workflow
    _, policy = create(private_workflow)
    original = scheduler.investigations.network.ask

    async def exercise():
        entered, release = asyncio.Event(), asyncio.Event()

        async def delayed(request, **kwargs):
            entered.set()
            await release.wait()
            return await original(request, **kwargs)

        monkeypatch.setattr(scheduler.investigations.network, "ask", delayed)
        await scheduler.run_now(policy["id"], RunBriefing(revision=1, request_id=uuid4().hex))
        await scheduler.tick()
        await asyncio.wait_for(entered.wait(), 2)
        current = channels.profile("discord")
        await channels.action("discord", ChannelAction(revision=current["revision"], action="pause"))
        await channels.action("discord", ChannelAction(revision=current["revision"], action="enable"))
        release.set()

    client.portal.call(exercise)
    completed = finish(client, scheduler, policy)
    assert completed["report_available"] and completed["delivery"]["status"] == "skipped"
    assert native_sends(state) == []


def test_whatsapp_closed_at_acceptance_or_send_never_delays_or_uses_templates(private_workflow):
    client, scheduler, channels, state, _, _ = private_workflow
    _, policy = create(private_workflow, "whatsapp")
    revision = channels.profile("whatsapp")["revision"]
    channels._update("whatsapp", revision, last_inbound_at=time.time() - 86400)
    run(private_workflow, policy)
    channels._update("whatsapp", revision, last_inbound_at=time.time())
    first = finish(client, scheduler, policy)
    assert first["delivery"]["status"] == "skipped"
    run(private_workflow, policy)
    second = finish(client, scheduler, policy)
    assert second["delivery"]["status"] == "pending"
    channels._update("whatsapp", revision, last_inbound_at=time.time() - 86400)
    deliver(private_workflow, "whatsapp")
    assert scheduler.detail(policy["id"])["occurrences"][0]["delivery"]["status"] == "skipped"
    assert native_sends(state) == []


def test_old_revision_withdrawal_preserves_new_occurrence_cache_and_delivery(private_workflow):
    client, scheduler, _, _, _, _ = private_workflow
    _, policy = create(private_workflow)
    run(private_workflow, policy)
    old = finish(client, scheduler, policy)
    target = next(
        row["target"]
        for row in client.get("/api/v1/message-deliveries/targets").json()["items"]
        if row["channel"] == "discord"
    )
    body = EditBriefing(revision=1, channel="discord", private_target=target)
    # Simulate a new revision completing in the real commit-to-withdrawal window.
    newer = scheduler.repository.edit(policy["id"], body, scheduler._binding(body), scheduler.clock())
    run(private_workflow, newer)
    latest = finish(client, scheduler, newer)
    waiting = run(private_workflow, newer)
    scheduler._withdraw(policy["id"], newer["revision"])
    assert waiting["id"] in scheduler._models
    assert scheduler.messaging.notifications.get(old["delivery_id"])["status"] == "skipped"
    assert scheduler.messaging.notifications.get(latest["delivery_id"])["status"] == "pending"
    deliver(private_workflow, "discord")
    assert scheduler.messaging.notifications.get(latest["delivery_id"])["status"] == "sent"


def test_committed_handoff_is_recovered_without_another_model_run_or_native_send(
    private_workflow, monkeypatch
):
    client, scheduler, _, state, _, _ = private_workflow
    entry, policy = create(private_workflow)
    run(private_workflow, policy)
    original = scheduler.messaging.notifications.enqueue
    failed = [False]

    def interrupted(*args, **kwargs):
        result = original(*args, **kwargs)
        if not failed[0]:
            failed[0] = True
            raise RuntimeError("Controlled post-commit interruption")
        return result

    monkeypatch.setattr(scheduler.messaging.notifications, "enqueue", interrupted)
    deadline = time.monotonic() + 5
    while not failed[0] and time.monotonic() < deadline:
        try:
            client.portal.call(scheduler.tick)
        except RuntimeError as exc:
            assert "Controlled post-commit" in str(exc)
        time.sleep(0.01)
    assert failed[0]
    monkeypatch.setattr(scheduler.messaging.notifications, "enqueue", original)
    deliver(private_workflow, "discord")
    sends = len(native_sends(state))
    restored = BriefingScheduler(scheduler.investigations, scheduler.messaging)
    client.portal.call(restored.tick)
    latest = restored.detail(policy["id"])["occurrences"][0]
    assert latest["delivery"]["status"] == "sent" and latest["status"] == "completed"
    deliver(private_workflow, "discord")
    with scheduler.store.db() as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM investigation_runs WHERE investigation_id=?", (entry["id"],)
            ).fetchone()[0]
            == 1
        )
    assert len(native_sends(state)) == sends


def test_private_resume_requires_the_current_checked_identity(private_workflow):
    client, scheduler, channels, _, _, profiles = private_workflow
    _, policy = create(private_workflow)
    scheduler.change(policy["id"], BriefingAction(revision=1, action="pause"))
    initial = channels.profile("discord")
    client.portal.call(
        channels.action, "discord", ChannelAction(revision=initial["revision"], action="pause")
    )
    channels.save("discord", profiles["discord"], revision=initial["revision"])
    client.portal.call(
        channels.action,
        "discord",
        ChannelAction(revision=channels.profile("discord")["revision"], action="check"),
    )
    response = client.post(
        f"/api/v1/briefing-schedules/{policy['id']}/actions", json={"revision": 2, "action": "resume"}
    )
    assert response.status_code == 409 and "review" in response.text
