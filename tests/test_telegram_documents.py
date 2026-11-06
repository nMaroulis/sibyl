"""Direct multipart document contracts and existing durable delivery protections."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from test_telegram import TOKEN, USER, FakeNetwork, message

from sibyl.messaging.documents import MAX_BYTES, document_bytes
from sibyl.messaging.outbound import NotificationOutbox
from sibyl.messaging.review import DeliveryDecision
from sibyl.messaging.service import TelegramService
from sibyl.messaging.settings import TelegramSettingsRequest


@pytest.fixture
async def documents(store):
    calls, response = [], [200]

    def transport(request):
        method = request.url.path.rsplit("/", 1)[-1]
        calls.append(request)
        if method == "sendDocument" and response[0] != 200:
            if response[0] == -1:
                raise httpx.ReadTimeout("private token URL", request=request)
            return httpx.Response(response[0], json={"ok": False, "parameters": {"retry_after": 1}})
        result = {
            "getMe": {"id": 12345, "is_bot": True, "username": "document_test"},
            "getWebhookInfo": {"url": ""},
            "sendMessage": {"message_id": 9},
            "sendDocument": {"message_id": 88},
            "getUpdates": [],
        }[method]
        return httpx.Response(200, json={"ok": True, "result": result})

    with store.db() as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS sibyl_turns(id TEXT,session_id TEXT,payload TEXT,created_at TEXT)"
        )
    owner = TelegramService(store, FakeNetwork(), httpx.AsyncClient(transport=httpx.MockTransport(transport)))
    owner.save(TelegramSettingsRequest(bot_token=TOKEN, allowed_user_id=USER, long_reply_document=True))
    await owner.enable()
    owner.notifications.authorize = lambda _: True
    yield owner, calls, response
    await owner.close()


def queue(owner, text, origin=None):
    p = owner.settings.profile()
    return owner.notifications.enqueue(
        origin or uuid4().hex,
        {
            "id": "c" * 32,
            "revision": 1,
            "telegram_format": "document",
            "telegram_binding": {"bot_id": p["bot_id"], "recipient_id": USER},
        },
        {"id": "b" * 32, "investigation_id": "a" * 32, "finished_at": datetime.now(UTC).isoformat()},
        text,
        datetime.now(UTC),
    )


def sent(calls):
    return [r for r in calls if r.url.path.endswith("/sendDocument")]


async def test_full_utf8_document_is_uploaded_once_and_reviewed(documents, caplog):
    owner, calls, _ = documents
    caplog.set_level("INFO", logger="httpx")
    text = "😀 analyst observation\n" * 1200
    origin = uuid4().hex
    item = queue(owner, text, origin)
    assert (
        item["format"] == "document" and item["total_parts"] == 1 and item["file_bytes"] == len(text.encode())
    )
    assert queue(owner, "changed", origin)["id"] == item["id"]
    await owner.notifications.deliver(owner.settings.profile())
    final = owner.notifications.review.get(item["id"])
    assert final["status"] == "sent" and final["parts"][0]["native_id"] == 88
    assert final["text_parts"][0]["text"] == text and final["text_parts"][0]["filename"].endswith(".txt")
    request = sent(calls)[0]
    assert request.headers["content-type"].startswith("multipart/form-data; boundary=")
    assert (
        text.encode() in request.content and b'name="document"; filename="sibyl-briefing-' in request.content
    )
    assert b'name="chat_id"\r\n\r\n' + str(USER).encode() in request.content
    assert b'name="protect_content"\r\n\r\ntrue' in request.content
    assert len(sent(calls)) == 1 and not await owner.notifications.deliver(owner.settings.profile())
    assert TOKEN not in json.dumps(final) + caplog.text


@pytest.mark.parametrize("code,expected", [(500, "uncertain"), (-1, "uncertain"), (403, "failed")])
async def test_ambiguous_or_denied_document_is_never_automatically_resent(documents, code, expected):
    owner, calls, response = documents
    response[0] = code
    item = queue(owner, "Complete report")
    await owner.notifications.deliver(owner.settings.profile())
    assert owner.notifications.get(item["id"])["status"] == expected
    assert not await owner.notifications.deliver(owner.settings.profile())
    assert len(sent(calls)) == 1
    if expected == "uncertain":
        restored = NotificationOutbox(owner.store, owner.settings, owner.client, lambda *a: None)
        assert restored.get(item["id"])["status"] == "uncertain"


async def test_explicit_rate_limit_and_user_withdrawal_prevent_late_retry(documents):
    owner, calls, response = documents
    response[0] = 429
    item = queue(owner, "Complete report")
    await owner.notifications.deliver(owner.settings.profile())
    detail = owner.notifications.review.get(item["id"])
    assert detail["status"] == "retrying" and detail["can_withdraw"]
    owner.notifications.review.decide(
        item["id"], DeliveryDecision(token=detail["review_token"], decision="withdraw")
    )
    response[0] = 200
    assert not await owner.notifications.deliver(owner.settings.profile())
    assert len(sent(calls)) == 1


async def test_oversized_briefing_stays_local_without_partial_attachment(documents):
    owner, calls, _ = documents
    item = queue(owner, "😀" * (MAX_BYTES // 4 + 1))
    assert item["status"] == "skipped" and "65,536" in item["error"]
    assert item["total_parts"] == 0
    assert not await owner.notifications.deliver(owner.settings.profile())
    assert not sent(calls)


async def test_reply_format_frozen_at_ingestion_short_replies_remain_text(documents):
    owner, calls, _ = documents
    profile = owner.settings.profile()
    owner.ingest(profile, [message(1)])
    # A private dependency snapshot is persisted with the accepted question.
    owner.settings.store.save_data_profile("messaging:telegram", profile | {"long_reply_document": False})

    async def answer(_):
        return {"answer": "完整回答😀" * 1500}

    owner.network.ask = answer
    await owner.process(profile)
    receipt = owner.replies.history()["items"][0]
    assert receipt["parts"][0]["format"] == "document" and receipt["total_parts"] == 1
    await owner.deliver(profile)
    assert owner.replies.get(receipt["id"])["parts"][0]["native_id"] == 88
    assert len(sent(calls)) == 1
    owner.ingest(owner.settings.profile(), [message(2)])

    async def short(_):
        return {"answer": "Short answer"}

    owner.network.ask = short
    await owner.process(owner.settings.profile())
    assert owner.replies.history()["items"][0]["parts"][0]["format"] == "text"


async def test_reply_document_withdraw_and_oversize_notice_preserve_answer(documents):
    owner, calls, _ = documents
    p = owner.settings.profile()
    owner.ingest(p, [message(1)])
    with owner.store.db() as db:
        owner._complete(db, p["revision"], 1, USER, "x" * 5000)
    item = owner.replies.history()["items"][0]
    detail = owner.replies.get(item["id"])
    owner.replies.decide(item["id"], DeliveryDecision(token=detail["review_token"], decision="withdraw"))
    assert not await owner.deliver(p) and not sent(calls)
    owner.ingest(p, [message(2)])
    with owner.store.db() as db:
        owner._complete(db, p["revision"], 2, USER, "x" * (MAX_BYTES + 1))
    detail = owner.replies.get(owner.replies.history()["items"][0]["id"])
    assert detail["text_parts"][0]["format"] == "text"
    assert "No attachment was sent" in detail["text_parts"][0]["text"]


@pytest.mark.parametrize(
    "filename", ["/tmp/secret.txt", "../sibyl-reply-1.txt", "https://private/file", "sibyl-reply-1.html"]
)
def test_documents_cannot_reference_paths_or_urls(filename):
    with pytest.raises(ValueError):
        document_bytes("body", filename)


def test_document_limit_counts_utf8_bytes():
    assert len(document_bytes("😀" * (MAX_BYTES // 4), "sibyl-reply-1.txt")) == MAX_BYTES
    with pytest.raises(ValueError):
        document_bytes("😀" * (MAX_BYTES // 4 + 1), "sibyl-reply-1.txt")


def test_document_briefing_rendering_does_not_silently_truncate():
    from sibyl.investigations.scheduling.delivery import briefing_text

    run = dict(
        version=1,
        finished_at=datetime.now(UTC).isoformat(),
        models={"sibyl": {"provider": "mock"}},
        context={"market_source": "demo"},
        sources=[],
        report={"summary": "x" * 20000, "findings": [], "uncertainties": []},
    )
    assert "x" * 20000 in briefing_text("Review", run, "full", document=True)
    assert "Briefing shortened" in briefing_text("Review", run, "full")
