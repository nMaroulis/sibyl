"""Conversation receipts preserve native outcomes, old targets and no-replay semantics."""

import json

import pytest
from test_telegram import TOKEN, message
from test_telegram import service as service

from sibyl.messaging.reply_review import ReplyReview, reply_evidence
from sibyl.messaging.review import DeliveryDecision


def queue(service, text="A long answer " + "x" * 8000):
    profile = service.settings.profile()
    service.ingest(profile, [message()])
    with service.store.db() as db:
        service._complete(db, profile["revision"], 1, profile["allowed_user_id"], text)
    return profile, service.replies.history()["items"][0]


async def test_reply_receipts_show_exact_text_but_agent_metadata_keeps_it_private(service):
    owner, calls = service, service.calls
    await owner.enable()
    profile, row = queue(owner)
    detail = owner.replies.get(row["id"])
    assert detail["bot_username"] == "sibyl_test_bot"
    assert len(detail["text_parts"]) == 3 and "A long answer" in detail["text_parts"][0]["text"]
    assert TOKEN not in json.dumps(detail)
    assert "A long answer" not in json.dumps(reply_evidence(owner.store))
    token = DeliveryDecision(token=detail["review_token"], decision="withdraw")
    await owner.deliver(profile)
    with pytest.raises(ValueError, match="changed"):
        owner.replies.decide(row["id"], token)
    latest = owner.replies.get(row["id"])
    final = owner.replies.decide(
        row["id"], DeliveryDecision(token=latest["review_token"], decision="withdraw")
    )
    assert final["status"] == "partial" and final["sent_parts"] == 1
    assert not await owner.deliver(profile)
    assert len([c for c in calls if c[0] == "sendMessage"]) == 1


async def test_reply_uncertainty_and_user_acknowledgment_survive_restart_without_resend(service):
    owner, calls = service, service.calls
    await owner.enable()
    profile, row = queue(owner)
    with owner.store.db() as db:
        db.execute(
            "UPDATE telegram_outbox SET state='uncertain' WHERE revision=? AND part=0", (profile["revision"],)
        )
        db.execute(
            "UPDATE telegram_outbox SET state='blocked' WHERE revision=? AND part>0", (profile["revision"],)
        )
    before = owner.replies.get(row["id"])
    owner.replies.decide(
        row["id"], DeliveryDecision(token=before["review_token"], decision="received", note="Checked chat")
    )
    saved = ReplyReview(owner.store).get(row["id"])
    assert saved["status"] == "uncertain" and saved["parts"] == before["parts"]
    assert saved["reviews"][-1]["native_confirmation"] is False
    assert not await owner.deliver(profile)
    assert not [c for c in calls if c[0] == "sendMessage"]


async def test_reply_chunking_respects_utf16_and_preserves_all_text(service):
    owner = service
    await owner.enable()
    _, row = queue(owner, "🪄" * 5000)
    parts = owner.replies.get(row["id"])["text_parts"]
    assert "".join(p["text"] for p in parts) == "🪄" * 5000
    assert all(len(p["text"].encode("utf-16-le")) // 2 <= 4000 for p in parts)


async def test_admitted_reply_cannot_be_reviewed_until_native_outcome(service, monkeypatch):
    import asyncio
    from types import SimpleNamespace

    owner = service
    await owner.enable()
    profile, row = queue(owner, "One private reply")
    entered, release = asyncio.Event(), asyncio.Event()

    async def send(*args):
        entered.set()
        await release.wait()
        return 999

    monkeypatch.setattr(owner, "client", lambda *a: SimpleNamespace(send=send))
    task = asyncio.create_task(owner.deliver(profile))
    await asyncio.wait_for(entered.wait(), 5)
    detail = owner.replies.get(row["id"])
    assert not detail["can_withdraw"] and not detail["can_acknowledge"]
    with pytest.raises(ValueError):
        owner.replies.decide(row["id"], DeliveryDecision(token=detail["review_token"], decision="withdraw"))
    release.set()
    await task
    final = owner.replies.get(row["id"])
    assert final["status"] == "sent" and final["parts"][0]["native_id"] == 999


async def test_legacy_identity_does_not_inherit_a_replacement_bot(service):
    owner = service
    await owner.enable()
    profile, row = queue(owner)
    with owner.store.db() as db:
        payload = json.loads(
            db.execute(
                "SELECT payload FROM telegram_updates WHERE revision=? AND update_id=1",
                (profile["revision"],),
            ).fetchone()[0]
        )
        payload.pop("bot_username", None)
        payload.pop("bot_id", None)
        db.execute(
            "UPDATE telegram_updates SET payload=? WHERE revision=? AND update_id=1",
            (json.dumps(payload), profile["revision"]),
        )
        db.execute("DELETE FROM telegram_reply_receipts WHERE id=?", (row["id"],))
    old = ReplyReview(owner.store).get(row["id"])
    assert old["bot_username"] is None and old["recipient_id"] == profile["allowed_user_id"]
