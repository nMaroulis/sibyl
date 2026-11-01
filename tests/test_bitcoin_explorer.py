"""Read-only Bitcoin acceptance using actual HTTP adapters and native ProtoLink routing.

Public HTTP responses are controlled; no developer accounts, addresses or secrets
are used. Identifier vectors include BIP 350's mainnet witness cases.
"""

import copy
import json

import httpx
import pytest

from sibyl.blockchain import demo, normalize
from sibyl.blockchain.bitcoin import BitcoinExplorer, BitcoinUnavailable
from sibyl.blockchain.identifiers import address, txid
from sibyl.models import AgentContext

VALID = [
    demo.ADDRESS,
    demo.PEER,
    "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
    "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy",
    "BC1QW508D6QEJXTDG4Y5R3ZARVARY0C5XW7KV8F3T4",
    "bc1pw508d6qejxtdg4y5r3zarvary0c5xw7kw508d6qejxtdg4y5r3zarvary0c5xw7kt5nd6y",
    "BC1SW50QGDZ25J",
    "bc1zw508d6qejxtdg4y5r3zarvaryvaxxpcs",
    "bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqzk5jj0",
]
INVALID = [
    "",
    "http://localhost/secret",
    "../" + demo.ADDRESS,
    demo.ADDRESS[:-1] + "1",
    demo.ADDRESS.lower(),
    "mipcBbFg9gMiCh81Kj8tqqdgoZub1ZJRfn",  # testnet Base58
    "tb1qrp33g0q5c5txsp9arysrx4k6zdkfs4nce4xj0gdcccefvpysxf3q0sl5k7",
    "bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqh2y7hd",  # wrong checksum family
    "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kemeawh",
    "BC130XLXVLHEMJA6C4DQV22UAPCTQUPFHLXM9H8Z3K2E72Q4K9HCZ7VQ7ZWS8R",
    "bc1pw5dgrnzv",
    "BC1QR508D6QEJXTDG4Y5R3ZARVARYV98GJ9P",
    "bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7v07qwwzcrf",
    "bC1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4",
    "bc1gmk9yu",
    "x" * 91,
]


@pytest.mark.parametrize("value", VALID)
def test_supported_mainnet_checksum_vectors(value):
    assert address(" " + value + "\n") == (value.lower() if value.lower().startswith("bc1") else value)


@pytest.mark.parametrize("value", INVALID)
def test_invalid_identifiers_cannot_contact_the_indexer(value):
    service = BitcoinExplorer(lambda: pytest.fail("Invalid reference contacted a provider"))
    with pytest.raises(ValueError):
        service.address(value)


def transport(handler=None):
    calls = []

    def respond(request):
        calls.append(request)
        assert request.method == "GET" and request.url.host == "mempool.space"
        assert not request.headers.get("authorization") and not request.url.query
        if handler:
            response = handler(request)
            if response is not None:
                return response
        value = demo.read(request.url.path.removeprefix("/api"))
        return httpx.Response(200, text=value) if isinstance(value, str) else httpx.Response(200, json=value)

    return BitcoinExplorer(lambda: httpx.Client(transport=httpx.MockTransport(respond))), calls


def test_transaction_fee_totals_virtual_size_and_attribution_are_real_provider_observations():
    service, calls = transport()
    report = service.transaction(demo.TXID.upper())
    row = report["transaction"]
    assert report["source"] == "mempool.space" and report["network"] == "bitcoin-mainnet"
    assert row["fee_sats"] == row["input_total_sats"] - row["output_total_sats"] == 1000
    assert row["vsize"] == 225 and row["fee_rate_sat_vb"] == pytest.approx(1000 / 225)
    assert row["status"]["confirmations"] == 7
    assert report["observed_at"] and report["tip_height"] == demo.TIP
    assert [str(c.url) for c in calls] == [
        f"https://mempool.space/api/tx/{demo.TXID}",
        "https://mempool.space/api/blocks/tip/height",
    ]
    assert "scriptpubkey" not in json.dumps(report) and "witness" not in json.dumps(report)


def test_address_balance_pending_change_and_stable_cursor_pages():
    service, calls = transport()
    report = service.address(demo.ADDRESS)
    row = report["address"]
    assert row["confirmed_balance_sats"] == 2_600_000
    assert row["pending_delta_sats"] == -100_000 and row["projected_balance_sats"] == 2_500_000
    first = report["history"]
    assert len(first["items"]) == 25 and first["items"][0]["net_sats"] == -200_000
    second = service.history(demo.ADDRESS, cursor=first["next_cursor"])
    assert len(second["items"]) == 4 and second["next_cursor"] is None
    assert not {r["txid"] for r in first["items"]} & {r["txid"] for r in second["items"]}
    pending = service.history(demo.ADDRESS, pending=True)
    assert pending["items"][0]["net_sats"] == -100_000
    assert not pending["items"][0]["status"]["confirmed"] and pending["next_cursor"] is None
    assert len(calls) == 7


def test_turnover_above_javascript_integer_precision_is_exported_exactly():
    raw = demo.read(f"/address/{demo.ADDRESS}")
    huge = 2**53 + 101
    raw["chain_stats"]["funded_txo_sum"] = huge + 123
    raw["chain_stats"]["spent_txo_sum"] = huge
    result = normalize.address_stats(raw)
    assert result["chain_stats"]["funded_txo_sum"] == str(huge + 123)
    assert result["confirmed_balance_sats"] == 123
    assert result["projected_balance_sats"] is None


def test_missing_previous_output_remains_unknown_in_totals_and_address_net():
    raw = copy.deepcopy(demo.transactions()[0][0])
    raw["vin"][0]["prevout"] = None
    row = normalize.transaction(raw, demo.TIP)
    assert row["missing_prevouts"] == 1 and row["input_total_sats"] is None
    assert normalize.history_row(raw, demo.ADDRESS, demo.TIP)["net_sats"] is None


def test_coinbase_has_no_previous_input_total_and_never_infers_a_sender():
    raw = copy.deepcopy(demo.transactions()[0][0])
    raw["vin"] = [{"is_coinbase": True, "prevout": None}]
    raw["fee"] = 0
    row = normalize.transaction(raw, demo.TIP)
    assert row["coinbase"] and row["input_total_sats"] is None
    assert row["inputs"][0]["txid"] is None
    raw["vin"][0]["prevout"] = {"value": 5}
    with pytest.raises(ValueError):
        normalize.transaction(raw, demo.TIP)


def test_transaction_lists_page_without_changing_totals_or_returning_raw_scripts():
    raw = copy.deepcopy(demo.transactions()[0][0])
    raw["vout"] = [{"value": 100, "scriptpubkey_type": "op_return"} for _ in range(45)]
    raw["vin"] = [{"is_coinbase": True, "prevout": None}]
    raw["fee"] = 0
    first, second, last = [normalize.transaction(raw, demo.TIP, output_offset=n) for n in (0, 20, 40)]
    assert [len(r["outputs"]) for r in (first, second, last)] == [20, 20, 5]
    assert first["output_total_sats"] == last["output_total_sats"] == 4500
    assert second["outputs"][0]["index"] == 20 and last["next_output_offset"] is None
    assert all(item["address"] is None for item in first["outputs"])


@pytest.mark.parametrize(
    "field,value", [("fee", True), ("fee", -1), ("size", 0), ("weight", float("nan")), ("fee", 900)]
)
def test_malformed_or_inconsistent_provider_amounts_fail_without_invented_values(field, value):
    def respond(request):
        if "/tx/" in request.url.path:
            raw = copy.deepcopy(demo.transactions()[0][0])
            raw[field] = value
            return (
                httpx.Response(200, json=raw) if value == value else httpx.Response(200, text=json.dumps(raw))
            )

    service, _ = transport(respond)
    with pytest.raises(BitcoinUnavailable, match="inconsistent"):
        service.transaction(demo.TXID)


@pytest.mark.parametrize("code", [404, 429, 500, 302])
def test_failures_are_sanitized_not_followed_or_retried_and_never_use_demo(code):
    service, calls = transport(
        lambda _: httpx.Response(
            code, text="PRIVATE-UPSTREAM-BODY", headers={"Location": "http://localhost/private"}
        )
    )
    with pytest.raises((LookupError, BitcoinUnavailable)) as error:
        service.transaction(demo.TXID)
    assert "PRIVATE" not in str(error.value) and len(calls) == 1
    if code == 429:
        assert error.value.status == 429


def test_unavailable_tip_retains_detail_but_never_fabricates_confirmation_depth():
    service, _ = transport(lambda r: httpx.Response(503) if r.url.path.endswith("/height") else None)
    result = service.transaction(demo.TXID)
    assert result["transaction"]["status"]["confirmed"]
    assert result["transaction"]["status"]["confirmations"] is None
    assert result["tip_height"] is None and result["warnings"]


def test_tip_behind_inclusion_is_not_clamped_to_a_false_confirmation_count():
    service, _ = transport(
        lambda r: httpx.Response(200, text="1") if r.url.path.endswith("/height") else None
    )
    result = service.transaction(demo.TXID)
    assert result["transaction"]["status"]["confirmations"] is None and result["warnings"]


def test_tip_rate_limit_stops_before_reading_address_history():
    service, calls = transport(lambda r: httpx.Response(429) if r.url.path.endswith("/height") else None)
    with pytest.raises(BitcoinUnavailable) as result:
        service.address(demo.ADDRESS)
    assert result.value.status == 429 and len(calls) == 2


def test_response_size_and_local_capacity_are_bounded_and_release_after_failure(monkeypatch):
    service, _ = transport(lambda _: httpx.Response(200, content=b"x" * 100))
    monkeypatch.setattr("sibyl.blockchain.bitcoin.MAX_RESPONSE", 50)
    for _ in range(3):
        with pytest.raises(BitcoinUnavailable, match="size"):
            service.transaction(demo.TXID)
    service._capacity.acquire()
    service._capacity.acquire()
    try:
        with pytest.raises(BitcoinUnavailable, match="already running"):
            service.transaction(demo.TXID)
    finally:
        service._capacity.release()
        service._capacity.release()


@pytest.mark.parametrize(
    "kind", ["repeat", "duplicate", "wrong-status", "unrelated", "wrong-id", "malformed"]
)
def test_invalid_identity_or_history_pages_fail_closed(kind):
    def respond(request):
        if kind == "wrong-id" and "/tx/" in request.url.path:
            return httpx.Response(200, json=demo.transactions()[0][1])
        if kind == "malformed":
            return httpx.Response(200, json=[])
        if "/txs/chain" in request.url.path:
            rows = copy.deepcopy(demo.transactions()[0][:25])
            if kind == "repeat":
                rows[0]["txid"] = "f" * 64
            elif kind == "duplicate":
                rows[1] = rows[0]
            elif kind == "wrong-status":
                rows[0]["status"] = {"confirmed": False}
            elif kind == "unrelated":
                rows[0]["vin"][0]["prevout"]["scriptpubkey_address"] = demo.PEER
                rows[0]["vin"][1]["prevout"]["scriptpubkey_address"] = demo.PEER
            return httpx.Response(200, json=rows)

    service, _ = transport(respond)
    with pytest.raises(BitcoinUnavailable):
        if kind in {"wrong-id", "malformed"}:
            service.transaction(demo.TXID)
        else:
            service.history(demo.ADDRESS, cursor="f" * 64)


def test_demo_is_explicit_isolated_and_never_activates_an_account(client, monkeypatch):
    bitcoin = client.app.state.services.research.bitcoin
    monkeypatch.setattr(bitcoin, "_client_factory", lambda: pytest.fail("Demo contacted a provider"))
    capabilities = client.get("/api/v1/bitcoin").json()
    before = [(row.id, row.active) for row in client.app.state.services.store.connections()]
    for kind, value in (
        ("transaction", capabilities["demo"]["txid"]),
        ("address", capabilities["demo"]["address"]),
    ):
        response = client.post("/api/v1/bitcoin/inspect", json={"kind": kind, "value": value, "demo": True})
        assert response.status_code == 200, response.text
        assert response.headers["Cache-Control"] == "no-store"
        assert response.json()["source"] == "demo" and response.json()["url"] is None
    assert [(row.id, row.active) for row in client.app.state.services.store.connections()] == before
    with pytest.raises(LookupError):
        bitcoin.transaction("f" * 64, simulated=True)


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "address", "value": demo.ADDRESS[:-1] + "1"},
        {"kind": "address", "value": demo.ADDRESS, "api_key": "PRIVATE"},
        {"kind": "transaction", "value": "http://localhost/credentials"},
        {"kind": "transaction", "value": demo.TXID, "demo": "true"},
        {"kind": "transaction", "value": demo.TXID, "input_offset": -1},
        {"kind": "address", "value": demo.ADDRESS, "output_offset": 20},
    ],
)
def test_api_rejects_invalid_inputs_before_external_reads_and_redacts_validation(client, monkeypatch, body):
    monkeypatch.setattr(
        client.app.state.services.research.bitcoin, "_client_factory", lambda: pytest.fail("Unexpected HTTP")
    )
    response = client.post("/api/v1/bitcoin/inspect", json=body)
    assert response.status_code == 422 and "PRIVATE" not in response.text


def test_api_real_transport_errors_have_correct_status_and_no_store(client, monkeypatch):
    service, _ = transport(lambda _: httpx.Response(429, text="PRIVATE-TOKEN"))
    monkeypatch.setattr(client.app.state.services.research, "bitcoin", service)
    response = client.post("/api/v1/bitcoin/inspect", json={"kind": "transaction", "value": demo.TXID})
    assert response.status_code == 429 and response.headers["Retry-After"] == "30"
    assert "PRIVATE" not in response.text and response.headers["Cache-Control"] == "no-store"


def test_native_explorer_uses_selected_demo_reference_and_preserves_private_context(client, monkeypatch):
    service = client.app.state.services.research.bitcoin
    monkeypatch.setattr(service, "_client_factory", lambda: pytest.fail("Selected Demo crossed to mainnet"))
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "explorer",
            "message": "Explain this transaction.",
            "context": {"bitcoin_txid": demo.TXID, "bitcoin_demo": True},
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["tool"] == "bitcoin_lookup" and result["evidence"]["transaction"]["txid"] == demo.TXID
    assert "Demo" in result["answer"] and "1,000 sat" in result["answer"]
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "explorer",
            "message": "Explain this address.",
            "context": {"bitcoin_address": demo.ADDRESS, "bitcoin_demo": True},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["evidence"]["kind"] == "address"
    assert client.app.state.services.agents.agents["explorer"].card.capabilities.delegation is False
    with pytest.raises(ValueError):
        AgentContext(bitcoin_txid=demo.TXID, bitcoin_address=demo.ADDRESS)


def test_hash_and_history_cursor_validation_never_accepts_url_components():
    assert txid(" " + demo.TXID.upper()) == demo.TXID
    service = BitcoinExplorer(lambda: pytest.fail("Invalid cursor contacted a provider"))
    with pytest.raises(ValueError):
        service.history(demo.ADDRESS, cursor="../private")
    with pytest.raises(ValueError):
        service.history(demo.ADDRESS, cursor=demo.TXID, pending=True)
