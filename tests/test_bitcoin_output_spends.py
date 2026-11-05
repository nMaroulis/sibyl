"""Output-spend evidence through bounded HTTP, the API and native ProtoLink clients."""

import copy

import httpx
import pytest
from protolink import Task, request_context

from sibyl.blockchain import demo
from sibyl.blockchain.bitcoin import BitcoinExplorer, BitcoinUnavailable
from sibyl.models import AgentContext


def source(override=None):
    calls = []

    def respond(request):
        assert request.method == "GET" and request.url.host == "mempool.space"
        assert not request.headers.get("authorization")
        path = request.url.path.removeprefix("/api")
        calls.append(path)
        value = override(path) if override else None
        if isinstance(value, httpx.Response):
            return value
        if value is None:
            value = demo.read(path)
        return httpx.Response(200, text=value) if isinstance(value, str) else httpx.Response(200, json=value)

    return BitcoinExplorer(lambda: httpx.Client(transport=httpx.MockTransport(respond))), calls


@pytest.mark.parametrize(
    "identity,state,target",
    [
        (f"{1:064x}", "confirmed", demo.TXID),
        (f"{3:064x}", "pending", demo.PENDING_TXID),
        (demo.TXID, "unspent", None),
    ],
)
def test_actual_adapter_and_demo_share_exact_states_without_provider_secrets(identity, state, target):
    service, calls = source()
    result = service.output_spends(identity.upper())
    item = result["items"][0]
    assert result["source"] == "mempool.space" and result["network"] == "bitcoin-mainnet"
    assert item["state"] == state and item["spending_txid"] == target
    assert item["index"] == 0 and item["value_sats"] > 0
    assert item["spent"] == (state != "unspent")
    if state == "confirmed":
        assert item["status"]["confirmations"] == 7 and item["spending_input_index"] == 0
    if state == "pending":
        assert item["status"]["confirmations"] == 0 and not item["status"]["confirmed"]
    if state == "unspent":
        assert item["status"] is None and item["spending_input_index"] is None
    assert calls == [f"/tx/{identity}", f"/tx/{identity}/outspends", "/blocks/tip/height"]
    independent = BitcoinExplorer(lambda: pytest.fail("Demo contacted a provider"))
    simulated = independent.output_spends(identity, simulated=True)
    assert simulated["items"] == result["items"] and simulated["source"] == "demo"
    assert "Synthetic" in simulated["warnings"][0]


@pytest.mark.parametrize(
    "row",
    [
        {"spent": True},
        {"spent": True, "txid": demo.PENDING_TXID},
        {"spent": True, "txid": demo.PENDING_TXID, "vin": 0},
    ],
)
def test_incomplete_spends_are_unknown_not_unspent_or_assumed_pending(row):
    service, _ = source(lambda path: [row] if path.endswith("/outspends") else None)
    result = service.output_spends(demo.TXID)
    assert result["items"][0]["state"] == "unknown" and result["items"][0]["spent"]
    assert result["items"][0]["reason"] and result["warnings"]


@pytest.mark.parametrize(
    "row",
    [
        None,
        {},
        {"spent": 0},
        {"spent": "false"},
        {"spent": False, "txid": demo.PENDING_TXID},
        {"spent": True, "txid": demo.TXID},
        {"spent": True, "txid": "PRIVATE"},
        {"spent": True, "vin": True},
        {"spent": True, "vin": -1},
        {"spent": True, "status": {"confirmed": "true"}},
    ],
)
def test_malformed_spending_evidence_is_rejected_never_replaced_with_demo(row):
    service, _ = source(lambda path: [row] if path.endswith("/outspends") else None)
    with pytest.raises(BitcoinUnavailable) as error:
        service.output_spends(demo.TXID)
    assert "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("rows", [[], [{"spent": False}, {"spent": False}], {"spent": False}])
def test_bulk_observation_must_match_the_complete_parent_output_count(rows):
    service, _ = source(lambda path: rows if path.endswith("/outspends") else None)
    with pytest.raises(BitcoinUnavailable, match="incomplete"):
        service.output_spends(demo.TXID)


def long_source(bad_last=False):
    parent = copy.deepcopy(demo.read(f"/tx/{demo.TXID}"))
    parent["vout"] = [copy.deepcopy(parent["vout"][0]) for _ in range(45)]
    for output in parent["vout"]:
        output["value"] = 1000
    parent["fee"] = 200_000 - 45_000
    rows = [{"spent": False} for _ in range(45)]
    if bad_last:
        rows[-1] = {"spent": "invalid"}
    return source(
        lambda path: parent if path == f"/tx/{demo.TXID}" else rows if path.endswith("/outspends") else None
    )


def test_twenty_output_pages_keep_exact_indexes_and_last_page_without_n_plus_one_reads():
    service, calls = long_source()
    first = service.output_spends(demo.TXID)
    second = service.output_spends(demo.TXID, output_offset=first["next_offset"])
    last = service.output_spends(demo.TXID, output_offset=second["next_offset"])
    assert first["total"] == 45 and first["limit"] == 20
    assert [r["index"] for r in second["items"]] == list(range(20, 40))
    assert [r["index"] for r in last["items"]] == list(range(40, 45))
    assert last["next_offset"] is None and len(calls) == 9
    with pytest.raises(BitcoinUnavailable):
        service.output_spends(demo.TXID, output_offset=45)
    corrupt, _ = long_source(True)
    with pytest.raises(BitcoinUnavailable):
        corrupt.output_spends(demo.TXID)  # Invalid evidence outside the returned page still fails.


@pytest.mark.parametrize(
    "identity,offset",
    [("../private", 0), (demo.TXID, True), (demo.TXID, -1), (demo.TXID, 1.5), (demo.TXID, 10_000)],
)
def test_invalid_direct_selections_never_contact_provider(identity, offset):
    service = BitcoinExplorer(lambda: pytest.fail("Invalid selection made HTTP request"))
    with pytest.raises(ValueError):
        service.output_spends(identity, output_offset=offset)


@pytest.mark.parametrize("status", [404, 429, 500])
def test_api_source_errors_preserve_unknown_state_and_sanitized_no_store(client, monkeypatch, status):
    service, _ = source(
        lambda path: (
            httpx.Response(status, text="PRIVATE-PROVIDER-BODY") if path.endswith("/outspends") else None
        )
    )
    monkeypatch.setattr(client.app.state.services.research, "bitcoin", service)
    response = client.post("/api/v1/bitcoin/output-spends", json={"transaction_id": demo.TXID})
    assert response.status_code == (502 if status == 500 else status)
    assert "PRIVATE" not in response.text and response.headers["Cache-Control"] == "no-store"
    if status == 429:
        assert response.headers["Retry-After"] == "30"
    assert "items" not in response.json()


def test_unavailable_tip_does_not_turn_confirmed_spend_into_pending():
    service, _ = source(lambda path: httpx.Response(503) if path == "/blocks/tip/height" else None)
    result = service.output_spends(f"{1:064x}")
    assert result["items"][0]["state"] == "confirmed"
    assert result["items"][0]["status"]["confirmations"] is None and result["warnings"]


@pytest.mark.parametrize(
    "body",
    [
        {"transaction_id": "../private"},
        {"transaction_id": demo.TXID, "output_offset": True},
        {"transaction_id": demo.TXID, "demo": "true"},
        {"transaction_id": demo.TXID, "api_key": "PRIVATE"},
    ],
)
def test_http_validation_before_provider_access(client, monkeypatch, body):
    monkeypatch.setattr(
        client.app.state.services.research.bitcoin, "_client_factory", lambda: pytest.fail("Unexpected HTTP")
    )
    response = client.post("/api/v1/bitcoin/output-spends", json=body)
    assert response.status_code == 422 and "PRIVATE" not in response.text


def test_api_demo_and_native_agent_selected_page_use_shared_evidence(client, monkeypatch):
    service = client.app.state.services.research.bitcoin
    monkeypatch.setattr(service, "_client_factory", lambda: pytest.fail("Demo crossed to mainnet"))
    response = client.post(
        "/api/v1/bitcoin/output-spends", json={"transaction_id": f"{3:064x}", "demo": True}
    )
    assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
    owner = client.app.state.services.agents

    async def selected():
        with request_context(
            {"page": {"bitcoin_txid": f"{3:064x}", "bitcoin_demo": True, "bitcoin_output_offset": 0}}
        ):
            execution = await owner.network.send(
                "explorer", Task.create_tool_call("bitcoin_output_spends", {})
            )
            return execution.output

    evidence = client.portal.call(selected)
    assert evidence["items"] == response.json()["items"]
    assert evidence["items"][0]["state"] == "pending" and evidence["source"] == "demo"
    tool = owner.agents["explorer"].tools["bitcoin_output_spends"]
    assert "spendability" in tool.description and "unknown" in tool.description
    assert not owner.agents["explorer"].card.capabilities.delegation
    with pytest.raises(ValueError):
        AgentContext(bitcoin_output_offset=True)


def test_native_transport_does_not_inherit_private_demo_context(client, monkeypatch):
    adapter, calls = source()
    service = client.app.state.services.research.bitcoin
    monkeypatch.setattr(service, "_client_factory", adapter._client_factory)
    owner = client.app.state.services.agents

    async def external():
        with request_context({"page": {"bitcoin_demo": True}}):
            result = await owner.network.client.send_task(
                owner.network.cards["explorer"].url,
                Task.create_tool_call("bitcoin_output_spends", {"transaction_id": f"{1:064x}"}),
            )
            result.raise_for_status()
            return result.get_last_item().parts[-1].as_tool_output().result

    evidence = client.portal.call(external)
    assert evidence["source"] == "mempool.space" and len(calls) == 3


def test_selected_output_page_does_not_leak_to_explicit_different_transaction(client, monkeypatch):
    adapter, _ = long_source()
    service = client.app.state.services.research.bitcoin
    monkeypatch.setattr(service, "_client_factory", adapter._client_factory)
    owner = client.app.state.services.agents

    async def read(identity=None):
        with request_context({"page": {"bitcoin_txid": demo.TXID, "bitcoin_output_offset": 20}}):
            result = await owner.network.send(
                "explorer",
                Task.create_tool_call(
                    "bitcoin_output_spends", {"transaction_id": identity} if identity else {}
                ),
            )
            return result.output

    page = client.portal.call(read)
    assert page["output_offset"] == 20 and page["items"][0]["index"] == 20
    # The other Demo parent has only one output; inheriting offset 20 would fail.
    monkeypatch.setattr(service, "_client_factory", source()[0]._client_factory)
    other = client.portal.call(read, f"{1:064x}")
    assert other["output_offset"] == 0 and other["items"][0]["state"] == "confirmed"
