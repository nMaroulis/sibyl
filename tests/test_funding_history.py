"""Offline native funding contracts, atomic range imports and performance coverage."""

import json
import time
from datetime import UTC, datetime

import ccxt
import pytest

from sibyl.exchanges import create_client
from sibyl.exchanges.funding import DAY, FundingPage, fetch_funding_page, funding_streams
from sibyl.models import ConnectionCreate
from sibyl.services.funding_ledger import funding_event
from sibyl.services.funding_sync import FundingSync, FundingSyncRequest, supported
from sibyl.services.market import Market

START = 1_704_067_200_000
END = START + 7 * DAY


def request(streams=None, start=START, end=END):
    return FundingSyncRequest(
        streams=streams or ["deposit"],
        start=datetime.fromtimestamp(start / 1000, UTC),
        end=datetime.fromtimestamp(end / 1000, UTC),
    )


def event(identity="1", **values):
    return {
        "native_id": identity,
        "reference": None,
        "timestamp_ms": START + DAY,
        "asset": "BTC",
        "quantity": 0.1,
        "kind": "deposit",
        "direction": "in",
        "status": "completed",
        "internal": False,
        "amount_basis": "provider_reported",
        "fee": {"currency": None, "cost": None},
        **values,
    }


@pytest.fixture
def funding(settings, store):
    market = Market(settings, store)
    service = FundingSync(market, store)
    yield service
    service.close()
    market.close()


def queue(service, monkeypatch, fetch, body=None):
    account = service.store.connections()[0]
    monkeypatch.setattr(service.market.client(account), "fetch_funding_page", fetch)
    service.enqueue(account, body or request())
    return account


def job(service):
    return service.snapshot()["jobs"][0]


def test_page_records_and_checkpoint_persist_with_exact_native_identity(funding, monkeypatch):
    observed = []

    def fetch(stream, cursor, limit):
        observed.append(cursor)
        return (
            FundingPage([event()], {**cursor, "page": "next"}, False)
            if len(observed) == 1
            else FundingPage([], cursor, True)
        )

    queue(funding, monkeypatch, fetch)
    funding.tick()
    assert job(funding)["record_count"] == 1 and job(funding)["status"] == "queued"
    restarted = FundingSync(funding.market, funding.store)
    restarted.tick()
    assert observed[1]["page"] == "next"
    assert job(funding)["status"] == "caught_up"
    assert job(funding)["start_ms"] == START and job(funding)["end_ms"] == END
    assert "cursor" not in json.dumps(funding.snapshot()) and '"next"' not in json.dumps(funding.snapshot())
    assert funding.ledger.events()["items"][0]["native_id"] == "1"


def test_rescan_upserts_status_and_fee_corrections(funding, monkeypatch):
    account = queue(
        funding,
        monkeypatch,
        lambda stream, cursor, limit: FundingPage([event(status="pending")], cursor, True),
    )
    funding.tick()
    assert funding.ledger.events()["summaries"] == []
    monkeypatch.setattr(
        funding.market.client(account),
        "fetch_funding_page",
        lambda stream, cursor, limit: FundingPage(
            [event(fee={"currency": "BTC", "cost": -0.001})], cursor, True
        ),
    )
    funding.enqueue(account, request())
    funding.tick()
    data = funding.ledger.events()
    assert data["total"] == 1 and data["summaries"][0]["quantity"] == 0.1
    assert data["fees"][0]["quantity"] == -0.001
    assert data["items"][0]["fee_known"]
    assert job(funding)["updated"] == 1


def test_bad_page_rolls_back_all_records_and_cursor(funding, monkeypatch):
    queue(
        funding,
        monkeypatch,
        lambda stream, cursor, limit: FundingPage([event(), event("2", quantity=-1)], {"page": "bad"}, True),
    )
    funding.tick()
    assert job(funding)["status"] == "error" and funding.ledger.events()["total"] == 0
    with funding.store.db() as db:
        assert funding.ledger.read_job(db, "demo", "deposit")["cursor"] == {"start": START, "end": END}


def test_failed_checkpoint_write_rolls_back_observations(funding, monkeypatch):
    queue(funding, monkeypatch, lambda stream, cursor, limit: FundingPage([event()], cursor, True))
    original = funding.ledger.write_job

    def failed(db, state):
        if state.get("pages") == 1:
            raise RuntimeError("interrupted commit")
        original(db, state)

    monkeypatch.setattr(funding.ledger, "write_job", failed)
    funding.tick()
    assert funding.ledger.events()["total"] == 0 and job(funding)["pages"] == 0


def test_pause_during_read_retains_successful_page_and_resumes(funding, monkeypatch):
    def fetch(stream, cursor, limit):
        funding.pause("demo", stream)
        return FundingPage([event()], {**cursor, "page": "next"}, False)

    account = queue(funding, monkeypatch, fetch)
    funding.tick()
    assert job(funding)["status"] == "paused" and job(funding)["record_count"] == 1
    funding.enqueue(account, request())
    assert job(funding)["pages"] == 1


def test_replacing_paused_range_discards_old_inflight_success(funding, monkeypatch):
    account = funding.store.connections()[0]

    def fetch(stream, cursor, limit):
        funding.pause(account.id, stream)
        funding.enqueue(account, request(start=START + DAY, end=END + DAY))
        return FundingPage([event()], {**cursor, "page": "old"}, False)

    queue(funding, monkeypatch, fetch)
    funding.tick()
    assert job(funding)["start_ms"] == START + DAY and job(funding)["pages"] == 0
    assert funding.ledger.events()["total"] == 0


def test_replacing_paused_range_discards_old_inflight_failure(funding, monkeypatch):
    account = funding.store.connections()[0]

    def fetch(stream, cursor, limit):
        funding.pause(account.id, stream)
        funding.enqueue(account, request(start=START + DAY, end=END + DAY))
        raise ccxt.NetworkError("OLD SECRET")

    queue(funding, monkeypatch, fetch)
    funding.tick()
    assert job(funding)["status"] == "queued" and job(funding).get("error") is None


def test_active_range_cannot_be_replaced_and_requests_are_atomic(funding, monkeypatch):
    account = queue(funding, monkeypatch, lambda *_: None)
    with pytest.raises(ValueError, match="Pause"):
        funding.enqueue(account, request(streams=["withdrawal", "deposit"], start=START + DAY, end=END + DAY))
    assert [row["stream"] for row in funding.snapshot()["jobs"]] == ["deposit"]


def test_repeated_offset_page_cannot_loop_with_advancing_synthetic_cursor(funding, monkeypatch):
    queue(
        funding,
        monkeypatch,
        lambda stream, cursor, limit: FundingPage(
            [event()], {**cursor, "offset": cursor.get("offset", 0) + 1}, False
        ),
    )
    funding.tick()
    funding.tick()
    assert job(funding)["status"] == "error" and job(funding)["record_count"] == 1


def test_transient_failures_back_off_and_never_expose_provider_text(funding, monkeypatch):
    def offline(*_):
        raise ccxt.RateLimitExceeded("PRIVATE https://private.invalid?key=SECRET")

    queue(funding, monkeypatch, offline)
    funding.tick()
    assert job(funding)["status"] == "retrying" and job(funding)["retry_at"]
    assert "PRIVATE" not in json.dumps(funding.snapshot())
    assert "SECRET" not in json.dumps(funding.snapshot())


def test_activation_and_disconnect_stop_reads_keep_funding_facts(funding, monkeypatch):
    account = queue(
        funding,
        monkeypatch,
        lambda stream, cursor, limit: FundingPage([event()], {**cursor, "page": "next"}, False),
    )
    funding.tick()
    funding.store.activate_account(account.id, False)
    monkeypatch.setattr(
        funding.market.client(account), "fetch_funding_page", lambda *_: pytest.fail("Inactive read")
    )
    funding.tick()
    assert job(funding)["status"] == "paused"
    with pytest.raises(ValueError, match="Activate"):
        funding.enqueue(account, request())
    funding.store.delete_connection(account.id)
    assert funding.ledger.events()["total"] == 1


@pytest.mark.parametrize(
    "values",
    [
        {"quantity": -1},
        {"quantity": float("inf")},
        {"quantity": 0},
        {"asset": "<raw>"},
        {"kind": "withdrawal"},
        {"status": "bogus"},
        {"native_id": None},
        {"timestamp_ms": START - 1},
        {"fee": {"currency": "BTC", "cost": float("nan")}},
        {"internal": "yes"},
    ],
)
def test_invalid_funding_facts_are_rejected(values):
    with pytest.raises(ValueError):
        funding_event(
            event(**values), {"account_id": "demo", "stream": "deposit", "start_ms": START, "end_ms": END}
        )


def test_strips_raw_addresses_and_metadata(funding, monkeypatch):
    queue(
        funding,
        monkeypatch,
        lambda stream, cursor, limit: FundingPage(
            [event(info="SECRET", address="PRIVATE", txid="PRIVATE")], cursor, True
        ),
    )
    funding.tick()
    assert "PRIVATE" not in json.dumps(funding.ledger.events()) and "SECRET" not in json.dumps(
        funding.ledger.events()
    )


def test_completed_totals_keep_accounts_assets_directions_and_environments_separate(funding):
    for account, env in [("demo", "demo"), ("other", "production")]:
        for index, (asset, status, direction) in enumerate(
            [
                ("BTC", "completed", "in"),
                ("BTC", "completed", "out"),
                ("ETH", "pending", "in"),
                ("ETH", "completed", "in"),
            ]
        ):
            row = funding_event(
                event(str(index), asset=asset, status=status, direction=direction),
                {
                    "account_id": account,
                    "account": account,
                    "exchange": "demo",
                    "environment": env,
                    "stream": "deposit",
                    "start_ms": START,
                    "end_ms": END,
                },
            )
            with funding.store.db() as db:
                db.execute(
                    "INSERT INTO funding_events VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        row["id"],
                        account,
                        "deposit",
                        row["native_id"],
                        asset,
                        row["timestamp_ms"],
                        status,
                        json.dumps(row),
                        "first",
                        "last",
                    ),
                )
    data = funding.ledger.events(limit=1)
    assert data["total"] == 8 and data["has_more"] and len(data["summaries"]) == 6
    assert sum(row["count"] for row in data["summaries"]) == 6
    assert funding.ledger.events(environment="production", status="pending")["total"] == 1
    assert funding.ledger.events(asset="BTC")["total"] == 4


@pytest.mark.parametrize("provider", ["binanceus", "binance-testnet", "coinbase", "coinbase-sandbox", "mexc"])
def test_unsupported_funding_imports_are_explicit_without_transport_reads(funding, monkeypatch, provider):
    assert funding_streams(provider) == []
    account = funding.store.add_connection(
        ConnectionCreate(
            exchange=provider, label="Not reviewed", api_key="key", secret="secret", passphrase="pass"
        )
    )
    monkeypatch.setattr(funding.market, "client", lambda *_: pytest.fail("Unreviewed provider read"))
    with pytest.raises(ValueError, match="coming soon"):
        funding.enqueue(account, request())


def test_legacy_binance_sandbox_cannot_inherit_funding_endpoints(funding):
    account = funding.store.add_connection(
        ConnectionCreate(exchange="binance", label="Sandbox", api_key="key", secret="secret", sandbox=True)
    )
    assert supported(account) == []
    adapter = create_client("binance", credentials={"apiKey": "key", "secret": "secret"}, sandbox=True)
    with pytest.raises(ccxt.NotSupported):
        adapter.fetch_funding_page("deposit", {"start": START, "end": END})
    adapter.close()


def native_binance(stream="deposit", identity="native-1", status=1):
    return {
        "id": identity,
        "coin": "BTC",
        "amount": "0.1",
        "status": status,
        "insertTime": START + DAY,
        "applyTime": "2024-01-02 00:00:00",
        "transactionFee": "0.0001",
        "transferType": 1,
        "address": "PRIVATE",
        "txId": "PRIVATE",
        "info": "SECRET",
    }


@pytest.mark.parametrize(
    "stream,method,status",
    [("deposit", "sapiGetCapitalDepositHisrec", 6), ("withdrawal", "sapiGetCapitalWithdrawHistory", 6)],
)
def test_binance_native_offsets_fixed_window_and_status_mapping(monkeypatch, stream, method, status):
    adapter = create_client("binance", credentials={"apiKey": "key", "secret": "secret"})
    observed = []

    def fetch(params):
        observed.append(params)
        return [native_binance(stream, str(i), status) for i in range(2)] if len(observed) == 1 else []

    monkeypatch.setattr(adapter._exchange, method, fetch)
    first = fetch_funding_page(adapter._exchange, "binance", stream, {"start": START, "end": END}, limit=2)
    last = fetch_funding_page(adapter._exchange, "binance", stream, first.cursor, limit=2)
    assert not first.caught_up and last.caught_up
    assert observed[0] == {"startTime": START, "endTime": END, "offset": 0, "limit": 2}
    assert observed[1]["offset"] == 2 and observed[1]["endTime"] == END
    assert first.items[0]["status"] == ("restricted" if stream == "deposit" else "completed")
    assert "PRIVATE" not in json.dumps(first.items)
    assert first.items[0]["fee"]["cost"] == (None if stream == "deposit" else "0.0001")
    adapter.close()


def test_kraken_native_cursor_not_offset_preserves_units_and_reference(monkeypatch):
    adapter = create_client("kraken", credentials={"apiKey": "key", "secret": "secret"})
    observed = []

    def fetch(params):
        observed.append(params)
        return {
            "result": {
                "ledger": {
                    "native-id": {
                        "refid": "paired-ref",
                        "time": (START + DAY) / 1000,
                        "type": "transfer",
                        "asset": "XXBT",
                        "amount": "-0.1",
                        "fee": "0.0001",
                        "info": "PRIVATE",
                    }
                }
                if len(observed) == 1
                else {},
                "cursor": {"next": "opaque"} if len(observed) == 1 else {},
            }
        }

    monkeypatch.setattr(adapter._exchange, "privatePostLedgers", fetch)
    first = adapter.fetch_funding_page("transfer", {"start": START, "end": END})
    last = adapter.fetch_funding_page("transfer", first.cursor)
    assert first.items[0]["asset"] == "BTC" and first.items[0]["quantity"] == 0.1
    assert first.items[0]["direction"] == "out" and first.items[0]["reference"] == "paired-ref"
    assert first.items[0]["internal"] and first.items[0]["amount_basis"] == "ledger_amount"
    assert observed[0]["with_cursor"] and "ofs" not in observed[0]
    assert observed[1]["cursor"] == "opaque" and observed[0]["end"] == observed[1]["end"]
    assert last.caught_up
    adapter.close()


def test_missing_kraken_cursor_never_means_caught_up(monkeypatch):
    adapter = create_client("kraken", credentials={"apiKey": "key", "secret": "secret"})
    monkeypatch.setattr(
        adapter._exchange, "privatePostLedgers", lambda *_: {"result": {"ledger": {}, "count": 100}}
    )
    with pytest.raises(ccxt.ExchangeError, match="cursor"):
        adapter.fetch_funding_page("deposit", {"start": START, "end": END})
    adapter.close()


def test_api_validates_ranges_and_demo_has_no_fabricated_funding(client):
    url = "/api/v1/connections/demo/funding-sync"
    payload = request(["deposit", "withdrawal", "transfer"]).model_dump(mode="json")
    assert client.post(url, json=payload).status_code == 202
    # The lifespan worker can own the nonblocking import lock while this test ticks.
    # Wait for observable completion rather than assuming three calls acquired it.
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        client.app.state.services.funding_sync.tick()
        jobs = client.get("/api/v1/funding-sync").json()["jobs"]
        if all(row["status"] == "caught_up" for row in jobs):
            break
        time.sleep(0.01)
    assert all(row["status"] == "caught_up" for row in jobs), jobs
    assert client.get("/api/v1/account-ledger/funding").json()["items"] == []
    for changes in [
        {"start": "2024-01-01T00:00:00"},
        {"streams": []},
        {"end": "2024-06-01T00:00:00Z"},
        {"end": "2099-01-01T00:00:00Z"},
        {"streams": ["trade"]},
    ]:
        assert client.post(url, json={**payload, **changes}).status_code == 422
    assert client.post(url.replace("demo", "missing"), json=payload).status_code == 404
    assert client.get("/api/v1/account-ledger/funding?limit=0").status_code == 422
    assert client.get("/api/v1/account-ledger/funding?asset=%3Craw%3E").status_code == 422


def test_example_is_read_only_and_pending_is_excluded_from_totals(client):
    example = client.get("/api/v1/account-ledger/funding/example").json()
    assert example["example"] and example["total"] == 4
    assert len(example["summaries"]) == 3 and not any(row["asset"] == "BTC" for row in example["summaries"])
    assert client.get("/api/v1/account-ledger/funding").json()["total"] == 0
    assert client.app.state.services.store.orders() == []


def test_kraken_terminal_short_page_may_omit_cursor(monkeypatch):
    adapter = create_client("kraken", credentials={"apiKey": "key", "secret": "secret"})
    monkeypatch.setattr(
        adapter._exchange, "privatePostLedgers", lambda *_: {"result": {"ledger": {}, "count": None}}
    )
    assert adapter.fetch_funding_page("deposit", {"start": START, "end": END}).caught_up
    adapter.close()


def test_funding_accountant_reads_same_filtered_ledger_via_protolink(client, monkeypatch):
    service = client.app.state.services
    monkeypatch.setattr(
        service.market, "account_balances", lambda *_: pytest.fail("Funding evidence is local")
    )
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "accountant",
            "message": "Explain the funding example.",
            "context": {"funding_view": True, "funding_example": True},
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["engine"] == "ProtoLink" and result["evidence"]["view"] == "funding"
    assert result["evidence"]["example"] and result["evidence"]["total"] == 4
    assert "not investment returns" in result["answer"]
    assert service.funding_sync.ledger.events()["total"] == 0


def seed_market_fifo(service):
    """Use normalized execution facts, without placing an order even in this test workspace."""
    from sibyl.services.ledger import ledger_fill

    for index, side in enumerate(["buy", "sell"]):
        row = ledger_fill(
            {
                "id": f"fill-{index}",
                "symbol": "BTC/USDT",
                "timestamp": START + index * DAY,
                "side": side,
                "amount": 1,
                "price": 100 + index * 20,
                "cost": 100 + index * 20,
                "fees": [{"currency": "USDT", "cost": 0}],
            },
            {
                "account_id": "demo",
                "account": "Demo",
                "exchange": "demo",
                "environment": "demo",
                "symbol": "BTC/USDT",
            },
        )
        with service.store.db() as db:
            db.execute(
                "INSERT INTO account_fills VALUES(?,?,?,?,?,?,?,?)",
                (
                    row["id"],
                    "demo",
                    row["symbol"],
                    row["trade_id"],
                    row["timestamp_ms"],
                    json.dumps(row),
                    row["created_at"],
                    row["created_at"],
                ),
            )


@pytest.mark.parametrize(
    "status,asset,fee,blocked",
    [
        ("completed", "BTC", None, True),
        ("pending", "BTC", None, True),
        ("failed", "BTC", None, False),
        ("cancelled", "BTC", None, False),
        ("completed", "ETH", None, False),
        ("completed", "ETH", {"currency": "BTC", "cost": 0.001}, True),
    ],
)
def test_funding_movements_flag_affected_fifo_without_inventing_lots(
    funding, monkeypatch, status, asset, fee, blocked
):
    from sibyl.services.ledger import AccountLedger
    from sibyl.services.performance import AccountPerformance

    AccountLedger(funding.store)
    performance = AccountPerformance(funding.market, funding.store)
    seed_market_fifo(funding)
    row = event(asset=asset, status=status)
    if fee:
        row["fee"] = fee
    queue(funding, monkeypatch, lambda stream, cursor, limit: FundingPage([row], cursor, True))
    funding.tick()
    data = performance.report()["items"][0]
    assert data["realized_before_other_fees"] == 20
    assert (data["net_matched_realized"] is None) == blocked
    assert bool(data["funding_event_count"]) == blocked


def test_funding_before_opening_boundary_does_not_double_count_user_assertion(client, monkeypatch):
    from sibyl.services.performance import OpeningInventory

    service = client.app.state.services
    service.performance.save_opening(
        "demo", OpeningInventory(symbol="BTC/USDT", quantity=1, total_cost=100, as_of="2024-01-05T00:00:00Z")
    )
    queue(
        service.funding_sync, monkeypatch, lambda stream, cursor, limit: FundingPage([event()], cursor, True)
    )
    service.funding_sync.tick()
    row = service.performance.report()["items"][0]
    assert row["funding_event_count"] == 0 and row["known_open_cost"] == 100


def test_funding_model_cannot_change_fixed_report_selection(client, monkeypatch):
    from protolink import create_llm

    registry = client.app.state.services.agents
    registry.settings.llm_provider = "ollama"
    monkeypatch.setattr(
        "sibyl.agents.registry.create_llm",
        lambda *a, **kw: create_llm(
            "mock",
            sequential_responses=[
                {
                    "type": "tool_call",
                    "tool": "accountant_snapshot",
                    "args": {"funding_view": False, "account_id": "other-account", "example": False},
                },
                "The selected funding snapshot.",
            ],
        ),
    )
    monkeypatch.setattr(
        client.app.state.services.market,
        "account_balances",
        lambda *_: pytest.fail("No private balances for funding inference"),
    )
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "accountant",
            "message": "Explain funding.",
            "context": {"funding_view": True, "funding_example": True},
        },
    )
    assert response.status_code == 200
    assert response.json()["evidence"]["example"] and response.json()["evidence"]["total"] == 4
    assert response.json()["mode"] == "llm"


def test_completed_range_remains_rescannable_after_account_deactivation(funding, monkeypatch):
    account = queue(
        funding,
        monkeypatch,
        lambda stream, cursor, limit: FundingPage([event()], {**cursor, "offset": 1}, True),
    )
    funding.tick()
    funding.pause(account.id)
    assert job(funding)["status"] == "caught_up"
    funding.enqueue(account, request())
    with funding.store.db() as db:
        assert funding.ledger.read_job(db, account.id, "deposit")["cursor"] == {"start": START, "end": END}


def test_funding_page_budget_stops_before_an_extra_provider_read(funding, monkeypatch):
    account = queue(funding, monkeypatch, lambda *_: pytest.fail("Budget must stop this read"))
    with funding.store.db() as db:
        current = funding.ledger.read_job(db, account.id, "deposit")
        current["pages"] = 2000
        funding.ledger.write_job(db, current)
    funding.tick()
    assert job(funding)["status"] == "error" and "smaller date range" in job(funding)["error"]
