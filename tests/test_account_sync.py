"""Offline import contracts: pagination, atomic checkpoints, failures and account isolation."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import ccxt
import pytest

from sibyl.exchanges import create_client
from sibyl.exchanges.history import TradePage
from sibyl.models import ConnectionCreate, OrderRequest
from sibyl.services.account_sync import AccountSync, AccountSyncRequest
from sibyl.services.ledger import ledger_fill
from sibyl.services.market import Market


@pytest.fixture
def sync(settings, store):
    service = AccountSync(Market(settings, store), store)
    yield service
    service.close()
    service.market.close()


def fill(identity="1", **values):
    return {
        "id": identity,
        "order": "order-1",
        "symbol": "BTC/USDT",
        "side": "buy",
        "timestamp": 1_700_000_000_000,
        "amount": 0.01,
        "price": 100,
        "cost": 1,
        "fees": [{"currency": "USDT", "cost": 0.001}],
        **values,
    }


def queue(sync, monkeypatch, fetch):
    account = sync.store.connections()[0]
    client = sync.market.client(account)
    monkeypatch.setattr(client, "fetch_trade_page", fetch)
    sync.enqueue(account, ["BTC/USDT"])
    return account


def job(sync):
    return sync.snapshot()["jobs"][0]


def test_real_demo_paper_history_is_paged_incrementally_and_survives_restart(sync):
    account = sync.store.connections()[0]
    for index in range(103):
        sync.store.execute_paper(
            OrderRequest(side="buy", quantity=0.0001, idempotency_key=f"import-demo-{index:03}"),
            100,
        )
    sync.enqueue(account, ["BTC/USDT"])
    sync.tick()
    assert job(sync)["record_count"] == 100
    restarted = AccountSync(sync.market, sync.store)
    restarted.tick()
    restarted.tick()
    assert job(restarted)["status"] == "caught_up"
    assert job(restarted)["record_count"] == 103
    restarted.enqueue(account, ["BTC/USDT"])
    restarted.tick()
    assert job(restarted)["record_count"] == 103
    sync.store.execute_paper(
        OrderRequest(side="sell", quantity=0.0001, idempotency_key="import-next-fill"), 110
    )
    restarted.enqueue(account, ["BTC/USDT"])
    restarted.tick()
    restarted.tick()
    assert job(restarted)["record_count"] == 104
    assert restarted.ledger.fills(side="sell")["total"] == 1
    assert restarted.ledger.fills()["complete_history"] is False


def test_demo_keyset_keeps_all_fills_with_the_same_timestamp(sync):
    for index in range(5):
        record = sync.store.execute_paper(
            OrderRequest(side="buy", quantity=0.001, idempotency_key=f"timestamp-tie-{index}"), 100
        )
        record["created_at"] = "2023-11-14T22:13:20+00:00"
        with sync.store.db() as db:
            db.execute(
                "UPDATE orders SET payload=?,created_at=? WHERE id=?",
                (
                    json.dumps(record),
                    record["created_at"],
                    record["id"],
                ),
            )
    adapter = sync.market.client(sync.store.connections()[0])
    cursor, identities = {}, []
    for _ in range(4):
        page = adapter.fetch_trade_page("BTC/USDT", cursor, limit=2)
        cursor = page.cursor
        identities.extend(row["id"] for row in page.items)
    assert len(identities) == len(set(identities)) == 5


def test_duplicate_native_ids_upsert_fee_corrections_without_cross_currency_sums(sync, monkeypatch):
    pages = iter(
        [
            TradePage([fill()], {"page": "next"}, False),
            TradePage(
                [fill(fees=[{"currency": "BNB", "cost": -0.01}, {"currency": "USDT", "cost": 0.02}])],
                {"page": "complete"},
                True,
            ),
        ]
    )
    queue(sync, monkeypatch, lambda *args: next(pages))
    sync.tick()
    sync.tick()
    data = sync.ledger.fills()
    assert data["total"] == 1
    assert data["fee_totals"] == {"BNB": -0.01, "USDT": 0.02}
    assert job(sync)["inserted"] == 1 and job(sync)["updated"] == 1
    assert data["items"][0]["fees_known"] is True
    assert "cursor" not in json.dumps(sync.snapshot())


def test_bad_page_cannot_commit_any_fill_or_advance_its_checkpoint(sync, monkeypatch):
    account = queue(
        sync, monkeypatch, lambda *args: TradePage([fill(), fill("2", amount=-1)], {"page": "bad"}, True)
    )
    sync.tick()
    assert job(sync)["status"] == "error"
    assert sync.ledger.fills()["total"] == 0
    with sync.store.db() as db:
        assert sync.ledger.read_job(db, account.id, "BTC/USDT")["cursor"] == {}
    observed = []

    def valid(symbol, cursor, limit):
        observed.append(cursor)
        return TradePage([fill()], {"page": "valid"}, True)

    monkeypatch.setattr(sync.market.client(account), "fetch_trade_page", valid)
    sync.enqueue(account, ["BTC/USDT"])
    sync.tick()
    assert observed == [{}]
    assert sync.ledger.fills()["total"] == 1


def test_checkpoint_write_failure_rolls_back_its_fill_upserts(sync, monkeypatch):
    queue(sync, monkeypatch, lambda *args: TradePage([fill()], {"page": "next"}, False))
    write = sync.ledger.write_job

    def interrupted(db, state):
        if state["pages"] == 1:
            raise RuntimeError("simulated interruption before commit")
        write(db, state)

    monkeypatch.setattr(sync.ledger, "write_job", interrupted)
    sync.tick()
    assert job(sync)["status"] == "error"
    assert job(sync)["pages"] == 0
    assert sync.ledger.fills()["total"] == 0
    with sync.store.db() as db:
        assert sync.ledger.read_job(db, "demo", "BTC/USDT")["cursor"] == {}


@pytest.mark.parametrize(
    "row",
    [
        fill(id=None),
        fill(timestamp=None),
        fill(timestamp=float("nan")),
        fill(price=0),
        fill(symbol="ETH/USDT"),
        fill(side="unknown"),
        fill(cost=-1),
        fill(fees=[{"currency": "<raw>", "cost": 0.1}]),
    ],
)
def test_invalid_execution_records_fail_explicitly(row):
    with pytest.raises(ValueError):
        ledger_fill(row, {"symbol": "BTC/USDT"})


def test_missing_fees_are_unavailable_rather_than_zero(sync, monkeypatch):
    queue(sync, monkeypatch, lambda *args: TradePage([fill(fees=[])], {}, True))
    sync.tick()
    data = sync.ledger.fills()
    assert data["missing_fee_count"] == 1 and data["fee_totals"] == {}
    assert data["items"][0]["fees"] == []


def test_stuck_cursor_stops_instead_of_looping_or_skipping(sync, monkeypatch):
    queue(sync, monkeypatch, lambda *args: TradePage([fill()], {}, False))
    sync.tick()
    assert job(sync)["status"] == "error"
    assert sync.ledger.fills()["total"] == 0


def test_cycle_of_different_cursors_stops_instead_of_reimporting_forever(sync, monkeypatch):
    pages = iter(
        [
            TradePage([fill("1")], {"page": "A"}, False),
            TradePage([fill("2")], {"page": "B"}, False),
            TradePage([fill("3")], {"page": "A"}, False),
        ]
    )
    queue(sync, monkeypatch, lambda *args: next(pages))
    for _page in range(3):
        sync.tick()
    assert job(sync)["status"] == "error"
    assert job(sync)["record_count"] == 2
    assert "seen_cursors" not in job(sync)


def test_filtered_ledger_totals_cover_all_pages_and_keep_unknown_notional(sync, monkeypatch):
    queue(
        sync,
        monkeypatch,
        lambda *args: TradePage(
            [
                fill("1", side="buy", cost=None),
                fill("2", side="sell"),
                fill("3", side="sell"),
            ],
            {},
            True,
        ),
    )
    sync.tick()
    data = sync.ledger.fills(side="sell", environment="demo", limit=1)
    assert data["total"] == 2 and data["has_more"]
    assert data["fee_totals"] == {"USDT": 0.002}
    assert sync.ledger.fills(side="buy")["items"][0]["notional"] is None
    assert sync.ledger.fills(symbol="ETH/USDT")["total"] == 0
    assert sync.ledger.fills(side="sell", offset=1, limit=1)["items"][0]["id"] != data["items"][0]["id"]


def test_pause_during_read_keeps_successful_page_and_resume_uses_new_checkpoint(sync, monkeypatch):
    observed = []

    def read(symbol, cursor, limit):
        observed.append(cursor)
        sync.pause("demo", symbol)
        return TradePage([fill()], {"page": "next"}, False)

    account = queue(sync, monkeypatch, read)
    sync.tick()
    assert job(sync)["status"] == "paused" and job(sync)["record_count"] == 1
    sync.tick()
    assert observed == [{}]
    monkeypatch.setattr(
        sync.market.client(account),
        "fetch_trade_page",
        lambda symbol, cursor, limit: observed.append(cursor) or TradePage([], cursor, True),
    )
    sync.enqueue(account, ["BTC/USDT"])
    sync.tick()
    assert observed[-1] == {"page": "next"}
    assert job(sync)["status"] == "caught_up"


def test_disconnect_stops_queued_reads_but_keeps_ledger(sync, monkeypatch):
    account = queue(sync, monkeypatch, lambda *args: TradePage([fill()], {"page": "next"}, False))
    sync.tick()
    sync.store.delete_connection(account.id)
    sync.tick()
    assert job(sync)["status"] == "disconnected"
    assert sync.snapshot()["accounts"] == []
    assert sync.ledger.fills(account_id=account.id)["total"] == 1


def test_network_failures_back_off_and_never_expose_provider_text(sync, monkeypatch):
    attempts = []

    def unavailable(*args):
        attempts.append(True)
        raise ccxt.RateLimitExceeded("PRIVATE-KEY https://private.example?secret=PRIVATE")

    account = queue(sync, monkeypatch, unavailable)
    sync.tick()
    assert job(sync)["status"] == "retrying" and job(sync)["retry_at"]
    sync.enqueue(account, ["BTC/USDT"])
    sync.tick()
    assert len(attempts) == 1
    assert "PRIVATE" not in json.dumps(sync.snapshot())
    for _attempt in range(5):
        with sync.store.db() as db:
            current = sync.ledger.read_job(db, account.id, "BTC/USDT")
            current["next_attempt"] = 0
            sync.ledger.write_job(db, current)
        sync.tick()
    assert job(sync)["status"] == "error"
    assert len(attempts) == 6


def test_auth_failures_wait_for_explicit_retry(sync, monkeypatch):
    def denied(*args):
        raise ccxt.AuthenticationError("PRIVATE-CREDENTIAL")

    queue(sync, monkeypatch, denied)
    sync.tick()
    assert job(sync)["status"] == "error" and job(sync)["next_attempt"] == 0
    assert "PRIVATE" not in json.dumps(sync.snapshot())


def test_recover_interrupted_read_keeps_checkpoint(sync, monkeypatch):
    account = queue(sync, monkeypatch, lambda *args: TradePage([fill()], {"page": "retained"}, False))
    sync.tick()
    with sync.store.db() as db:
        current = sync.ledger.read_job(db, account.id, "BTC/USDT")
        current["status"] = "running"
        sync.ledger.write_job(db, current)
    restarted = AccountSync(sync.market, sync.store)
    assert job(restarted)["status"] == "queued"
    with sync.store.db() as db:
        assert sync.ledger.read_job(db, account.id, "BTC/USDT")["cursor"] == {"page": "retained"}


def test_tick_has_one_inflight_read_even_with_concurrent_callers(sync, monkeypatch):
    entered, release = Event(), Event()
    attempts = []

    def read(*args):
        attempts.append(True)
        entered.set()
        assert release.wait(3)
        return TradePage([fill()], {}, True)

    queue(sync, monkeypatch, read)
    with ThreadPoolExecutor(max_workers=4) as pool:
        running = pool.submit(sync.tick)
        assert entered.wait(3)
        others = [pool.submit(sync.tick) for _ in range(3)]
        for task in others:
            task.result(timeout=3)
        release.set()
        running.result(timeout=3)
    assert len(attempts) == 1
    assert job(sync)["record_count"] == 1


def test_account_and_environment_identity_isolation(sync, monkeypatch):
    queue(sync, monkeypatch, lambda *args: TradePage([fill()], {}, True))
    sync.tick()
    connection = sync.store.add_connection(
        ConnectionCreate(
            exchange="binance-testnet",
            label="Test funds",
            api_key="PRIVATE",
            secret="PRIVATE",
        )
    )
    adapter = sync.market.client(connection)
    monkeypatch.setattr(adapter, "fetch_trade_page", lambda *args: TradePage([fill()], {}, True))
    sync.enqueue(connection, ["BTC/USDT"])
    sync.tick()
    assert sync.ledger.fills()["total"] == 2
    assert sync.ledger.fills(environment="test")["total"] == 1
    assert sync.ledger.fills(environment="demo")["total"] == 1
    assert "PRIVATE" not in json.dumps(sync.ledger.fills())


def test_unsupported_provider_is_explicit_and_does_not_construct_a_transport(sync, monkeypatch):
    connection = sync.store.add_connection(
        ConnectionCreate(exchange="mexc", label="Read account", api_key="key", secret="secret")
    )
    monkeypatch.setattr(
        sync.market, "client", lambda *args: pytest.fail("Do not authenticate unsupported imports")
    )
    with pytest.raises(ValueError, match="coming soon"):
        sync.enqueue(connection, ["BTC/USDT"])
    assert not sync.snapshot()["jobs"]


def test_sync_api_validates_inputs_and_exposes_no_private_cursor(client):
    assert AccountSyncRequest(symbols=["btc/usdt", "BTC/USDT"]).symbols == ["BTC/USDT"]
    assert client.post("/api/v1/connections/missing/sync", json={"symbols": ["BTC/USDT"]}).status_code == 404
    for body in ({"symbols": []}, {"symbols": ["BTC/USDT:USDT"]}, {"symbols": ["BTC/USDT"], "cursor": "raw"}):
        assert client.post("/api/v1/connections/demo/sync", json=body).status_code == 422
    response = client.post("/api/v1/connections/demo/sync", json={"symbols": ["BTC/USDT"]})
    assert response.status_code == 202
    assert "cursor" not in response.text
    client.app.state.services.account_sync.tick()
    assert client.get("/api/v1/account-sync").json()["jobs"][0]["status"] == "caught_up"
    assert "BTC/USDT" in client.get("/api/v1/connections/demo/markets").json()["symbols"]
    assert client.get("/api/v1/account-ledger/fills?limit=0").status_code == 422
    assert client.get("/api/v1/account-ledger/fills?symbol=BTC%2FUSDT%3AUSDT").status_code == 422
    assert client.post("/api/v1/connections/demo/sync/pause?symbol=BTC/USDT").status_code == 200
    evidence = client.app.state.services.agents._tools["technician"]()
    assert evidence["history_imports"][0]["symbol"] == "BTC/USDT"
    assert "cursor" not in json.dumps(evidence)


def history_client(identity):
    """Use actual installed SDK parsers, replacing only native authenticated transports."""
    client = create_client(identity, credentials={"apiKey": "key", "secret": "secret", "password": "pass"})
    market = {
        "id": "XXBTZUSD" if identity == "kraken" else "BTC-USD" if "coinbase" in identity else "BTCUSDT",
        "symbol": "BTC/USD" if identity in {"coinbase", "coinbase-sandbox", "kraken"} else "BTC/USDT",
        "base": "BTC",
        "quote": "USD" if identity in {"coinbase", "coinbase-sandbox", "kraken"} else "USDT",
        "baseId": "BTC",
        "quoteId": "USD",
        "type": "spot",
        "spot": True,
        "option": False,
        "swap": False,
        "future": False,
        "contract": False,
        "active": True,
        "precision": {"amount": 0.00000001, "price": 0.01},
        "limits": {},
        "info": {"altname": "XBTUSD"},
    }
    client._exchange.set_markets([market])
    return client, market


@pytest.mark.parametrize("identity", ["binance", "binanceus", "binance-testnet"])
def test_binance_history_uses_exact_native_id_without_timestamp_skipping(monkeypatch, identity):
    client, market = history_client(identity)
    observed = []
    native = {
        "id": 9007199254740993,
        "orderId": 4,
        "symbol": "BTCUSDT",
        "isBuyer": True,
        "isMaker": False,
        "price": "100",
        "qty": "0.01",
        "quoteQty": "1",
        "time": 1700000000000,
        "commission": "0.01",
        "commissionAsset": "BNB",
        "info": "PRIVATE",
    }

    def read(request):
        observed.append(request)
        return [native] if len(observed) == 1 else []

    monkeypatch.setattr(client._exchange, "privateGetMyTrades", read)
    page = client.fetch_trade_page(market["symbol"], {})
    assert page.cursor == {"from_id": "9007199254740994"} and not page.caught_up
    terminal = client.fetch_trade_page(market["symbol"], page.cursor)
    assert terminal.caught_up
    assert observed[0]["fromId"] == "0" and observed[1]["fromId"] == "9007199254740994"
    assert "startTime" not in observed[0]
    assert page.items[0]["fees"] == [{"currency": "BNB", "cost": 0.01}]
    assert "PRIVATE" not in json.dumps(page.items)
    client.close()


def test_coinbase_native_cursor_and_quote_sized_fill_parsing(monkeypatch):
    client, market = history_client("coinbase")
    observed = []
    raw = {
        "entry_id": "entry-1",
        "trade_id": "trade-1",
        "order_id": "order-1",
        "trade_time": "2023-11-14T22:13:20Z",
        "product_id": "BTC-USD",
        "price": "100",
        "size": "10",
        "size_in_quote": True,
        "commission": "0.1",
        "side": "BUY",
        "user_id": "PRIVATE",
    }

    def read(request):
        observed.append(request)
        return {"fills": [raw], "cursor": "opaque"} if len(observed) == 1 else {"fills": [], "cursor": ""}

    monkeypatch.setattr(client._exchange, "v3PrivateGetBrokerageOrdersHistoricalFills", read)
    page = client.fetch_trade_page(market["symbol"], {})
    assert page.items[0]["amount"] == 0.1
    assert page.items[0]["cost"] == 10
    assert not page.caught_up
    terminal = client.fetch_trade_page(market["symbol"], page.cursor)
    assert observed[1]["cursor"] == "opaque"
    assert observed[0]["product_ids"] == ["BTC-USD"] and observed[0]["product_types"] == ["SPOT"]
    assert observed[0]["end_sequence_timestamp"] == observed[1]["end_sequence_timestamp"]
    assert "page" not in terminal.cursor and terminal.caught_up
    assert "PRIVATE" not in json.dumps(page.items)
    client.close()


def test_coinbase_verification_gate_is_not_misreported_as_empty_history(monkeypatch):
    client, market = history_client("coinbase")
    monkeypatch.setattr(
        client._exchange,
        "v3PrivateGetBrokerageOrdersHistoricalFills",
        lambda request: {
            "fills": [],
            "cursor": "",
            "proof_token_required": True,
        },
    )
    with pytest.raises(ccxt.PermissionDenied):
        client.fetch_trade_page(market["symbol"], {})
    client.close()


def test_coinbase_sandbox_uses_response_header_not_a_guessed_trade_cursor(monkeypatch):
    client, market = history_client("coinbase-sandbox")
    observed = []

    def read(request):
        observed.append(request)
        client._exchange.last_response_headers = {"CB-AFTER": "header-cursor"} if len(observed) == 1 else {}
        return (
            [
                {
                    "trade_id": 7,
                    "order_id": "order-1",
                    "created_at": "2023-11-14T22:13:20Z",
                    "product_id": "BTC-USD",
                    "price": "100",
                    "size": "0.1",
                    "fee": "0.01",
                    "side": "buy",
                }
            ]
            if len(observed) == 1
            else []
        )

    monkeypatch.setattr(client._exchange, "privateGetFills", read)
    page = client.fetch_trade_page(market["symbol"], {})
    terminal = client.fetch_trade_page(market["symbol"], page.cursor)
    assert observed[1]["after"] == "header-cursor"
    assert observed[0]["end_date"] == observed[1]["end_date"]
    assert page.items[0]["side"] == "buy" and terminal.caught_up
    client.close()


def test_kraken_uses_bounded_spot_cursor_not_filtered_page_length(monkeypatch):
    client, market = history_client("kraken")
    observed = []

    def read(request):
        observed.append(request)
        return (
            {
                "result": {
                    "trades": {
                        "native-trade": {
                            "ordertxid": "order-1",
                            "pair": "XXBTZUSD",
                            "time": 1700000000,
                            "type": "buy",
                            "price": "100",
                            "cost": "1",
                            "vol": "0.01",
                            "fee": "0.001",
                            "info": "PRIVATE",
                        }
                    },
                    "cursor": {"next": "kraken-next"},
                }
            }
            if len(observed) == 1
            else {"result": {"trades": {}, "cursor": {}}}
        )

    monkeypatch.setattr(client._exchange, "privatePostTradesHistory", read)
    page = client.fetch_trade_page(market["symbol"], {})
    terminal = client.fetch_trade_page(market["symbol"], page.cursor)
    assert observed[0]["type"] == "no position" and observed[0]["with_cursor"] is True
    assert observed[0]["consolidate_taker"] is False and observed[0]["pair"] == "XXBTZUSD"
    assert observed[1]["cursor"] == "kraken-next" and observed[0]["end"] == observed[1]["end"]
    assert page.items[0]["id"] == "native-trade" and terminal.caught_up
    assert "PRIVATE" not in json.dumps(page.items)
    client.close()
