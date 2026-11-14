"""Historical block pages use exact hashes and separate indexer chain status."""

import httpx
import pytest
from test_bitcoin_explorer import transport

from sibyl.blockchain import demo
from sibyl.blockchain.bitcoin import BitcoinExplorer, BitcoinUnavailable

PATH = f"/block/{demo.BLOCK_HASH}"


def test_height_resolves_once_and_following_page_is_hash_pinned():
    explorer, calls = transport()
    first = explorer.block(height=demo.BLOCK_HEIGHT)
    second = explorer.block(block_hash=first["block"]["id"], offset=first["next_offset"])
    assert first["source"] == "mempool.space" and first["in_best_chain"] is True
    assert first["block"]["tx_count"] == 29 and first["next_offset"] == 25
    assert first["items"][0]["coinbase"] is True and first["items"][0]["fee_sats"] == 0
    assert [row["index"] for row in second["items"]] == [25, 26, 27, 28]
    assert second["block"]["id"] == first["block"]["id"] and second["next_offset"] is None
    assert [request.url.path for request in calls] == [
        f"/api/block-height/{demo.BLOCK_HEIGHT}",
        f"/api{PATH}",
        f"/api{PATH}/txs",
        f"/api{PATH}/status",
        f"/api{PATH}",
        f"/api{PATH}/txs/25",
        f"/api{PATH}/status",
    ]


@pytest.mark.parametrize(
    "status,expected",
    [
        (httpx.Response(404), None),
        (httpx.Response(503), None),
        (httpx.Response(200, json={"in_best_chain": False, "height": None}), False),
    ],
)
def test_status_uncertainty_does_not_erase_pinned_members(status, expected):
    explorer, _ = transport(lambda request: status if request.url.path.endswith("/status") else None)
    report = explorer.block(block_hash=demo.BLOCK_HASH)
    assert report["in_best_chain"] is expected
    assert len(report["items"]) == 25
    assert "status" not in report["items"][0]


@pytest.mark.parametrize(
    "suffix,make_payload",
    [
        ("", lambda: {**demo.read(PATH), "height": demo.BLOCK_HEIGHT + 1}),
        ("", lambda: {**demo.read(PATH), "id": "a" * 64}),
        ("/txs", lambda: demo.block_transactions()[:24]),
        ("/txs", lambda: [*demo.block_transactions()[:24], demo.block_transactions()[1]]),
        ("/txs", lambda: list(reversed(demo.block_transactions()[:25]))),
        ("/status", lambda: {"in_best_chain": "false", "height": demo.BLOCK_HEIGHT}),
        ("/status", lambda: {"in_best_chain": True, "height": demo.BLOCK_HEIGHT + 1}),
    ],
)
def test_rejects_inconsistent_block_identity_membership_page_or_status(suffix, make_payload):
    def override(request):
        if request.url.path == "/api" + PATH + suffix:
            return httpx.Response(200, json=make_payload())

    explorer, _ = transport(override)
    with pytest.raises(BitcoinUnavailable):
        explorer.block(height=demo.BLOCK_HEIGHT)


@pytest.mark.parametrize(
    "selection",
    [{}, {"height": True}, {"height": -1}, {"block_hash": "../unsafe"}, {"height": 1, "offset": 24}],
)
def test_invalid_block_selection_never_sends_http(selection):
    explorer = BitcoinExplorer(lambda: pytest.fail("Invalid block request used HTTP"))
    with pytest.raises(ValueError):
        explorer.block(**selection)


def test_demo_block_drills_into_existing_inspector_and_native_agent(client, monkeypatch):
    explorer = client.app.state.services.research.bitcoin
    monkeypatch.setattr(explorer, "_client_factory", lambda: pytest.fail("Demo used HTTP"))
    request = {"height": demo.BLOCK_HEIGHT, "demo": True}
    response = client.post("/api/v1/bitcoin/block", json=request)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    report = response.json()
    assert report["source"] == "demo" and report["url"] is None
    tail = client.post(
        "/api/v1/bitcoin/block", json={"block_hash": demo.BLOCK_HASH, "demo": True, "offset": 25}
    ).json()
    transaction = tail["items"][0]["txid"]
    inspected = client.post(
        "/api/v1/bitcoin/inspect", json={"kind": "transaction", "value": transaction, "demo": True}
    )
    assert inspected.status_code == 200
    assert inspected.json()["transaction"]["status"]["block_hash"] == demo.BLOCK_HASH
    assert client.post("/api/v1/bitcoin/block", json={**request, "offset": 50}).status_code == 404
    assert client.post("/api/v1/bitcoin/block", json={**request, "offset": 1}).status_code == 422
    reply = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "explorer",
            "message": "Which transactions are in the current block page?",
            "context": {
                "bitcoin_block_hash": demo.BLOCK_HASH,
                "bitcoin_block_offset": 25,
                "bitcoin_demo": True,
            },
        },
    )
    assert reply.status_code == 200, reply.text
    assert reply.json()["evidence"]["items"] == tail["items"]
    assert reply.json()["evidence"]["transaction_offset"] == 25
