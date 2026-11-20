"""Native-shaped SDK fixtures exercise pagination and fees without private HTTP or orders."""

from copy import deepcopy

import ccxt
import pytest

from sibyl.accounting.executions.versions import history
from sibyl.exchanges.history import fetch_trade_page
from sibyl.exchanges.order_fills import fetch_order_fill_page
from sibyl.exchanges.registry import provider_catalog
from sibyl.models import ConnectionCreate
from sibyl.services.accounts.ledger import AccountLedger
from sibyl.services.accounts.sync import AccountSync
from sibyl.services.trading.discovery import normalized_order

STAMP = 1_700_000_000_000


def sdk(provider):
    exchange = getattr(ccxt, provider)()
    exchange.set_markets(
        [
            {
                "id": "btcusd",
                "symbol": "BTC/USD",
                "base": "BTC",
                "quote": "USD",
                "baseId": "btc",
                "quoteId": "usd",
                "type": "spot",
                "spot": True,
                "contract": False,
                "active": True,
                "precision": {"amount": 8, "price": 2},
                "limits": {},
            }
        ]
    )
    return exchange


def bitstamp(identity, **changes):
    return {
        "id": identity,
        "type": "2",
        "order_id": "123",
        "datetime": "2023-11-14 22:13:20.123000",
        "btc": "0.01",
        "usd": "-100",
        "btc_usd": "10000",
        "fee": "0.1",
        **changes,
    }


def gemini(identity, **changes):
    return {
        "tid": identity,
        "order_id": "123",
        "timestampms": STAMP,
        "symbol": "BTCUSD",
        "price": "10000",
        "amount": "0.01",
        "type": "Buy",
        "fee_currency": "USD",
        "fee_amount": "0.1",
        **changes,
    }


def test_bitstamp_id_pages_preserve_large_ids_signs_and_nontrade_checkpoints(monkeypatch):
    venue = sdk("bitstamp")
    huge = 2**60
    data = [bitstamp(huge + i) for i in range(205)]
    data[99] = {"id": huge + 99, "type": "1"}
    data[101] = bitstamp(huge + 101, btc="-0.01", usd="100", fee="-0.01")
    calls = []

    def native(request):
        calls.append(request)
        assert request["sort"] == "asc" and request["limit"] == 1000 and request["pair"] == "btcusd"
        return [row for row in data if row["id"] >= int(request["since_id"])][:1000]

    monkeypatch.setattr(venue, "privatePostUserTransactionsPair", native)
    first = fetch_trade_page(venue, "bitstamp-transactions", "BTC/USD", {}, 100)
    assert len(first.items) == 99 and not first.caught_up
    assert first.cursor == {"after_id": str(huge + 100)}
    second = fetch_trade_page(venue, "bitstamp-transactions", "BTC/USD", first.cursor, 100)
    assert second.items[1]["side"] == "sell" and second.items[1]["fees"] == [
        {"currency": "USD", "cost": -0.01}
    ]
    last = fetch_trade_page(venue, "bitstamp-transactions", "BTC/USD", second.cursor, 100)
    assert last.caught_up and len(last.items) == 5
    assert len({row["id"] for page in (first, second, last) for row in page.items}) == 204
    assert first.items[0]["id"] == str(huge) and first.items[0]["order"] == "123"


@pytest.mark.parametrize(
    "provider,kind", [("bitstamp", "bitstamp-transactions"), ("gemini", "gemini-trades")]
)
def test_import_checkpoint_and_fees_survive_service_restart(manual_client, monkeypatch, provider, kind):
    owner = manual_client.app.state.services
    account = owner.store.add_connection(
        ConnectionCreate(
            exchange=provider, label="Isolated adapter", api_key="fake-key", secret="fake-secret"
        )
    )
    venue = sdk(provider)
    if provider == "bitstamp":
        rows = [bitstamp(i + 1) for i in range(105)]
        monkeypatch.setattr(
            venue,
            "privatePostUserTransactionsPair",
            lambda request: [r for r in rows if r["id"] >= int(request["since_id"])],
        )
    else:
        rows = [gemini(i + 1, timestampms=STAMP + i // 50) for i in range(105)]
        monkeypatch.setattr(
            venue,
            "privatePostV1Mytrades",
            lambda request: list(reversed([r for r in rows if r["timestampms"] >= request["timestamp"]])),
        )
    adapter = owner.market.client(account)
    monkeypatch.setattr(
        adapter,
        "fetch_trade_page",
        lambda symbol, cursor, limit: fetch_trade_page(venue, kind, symbol, cursor, limit),
    )
    service = owner.account_sync
    service.enqueue(account, ["BTC/USD"])
    service.tick()
    assert service.ledger.fills(account_id=account.id)["total"] == 100
    reopened = AccountSync(owner.market, owner.store)
    reopened.tick()
    state = next(row for row in reopened.snapshot()["jobs"] if row["account_id"] == account.id)
    assert state["status"] == "caught_up" and state["record_count"] == 105
    reopened.enqueue(account, ["BTC/USD"])
    reopened.tick()
    assert AccountLedger(owner.store, recover=False).fills(account_id=account.id)["total"] == 105
    reopened.close()


def test_gemini_inclusive_millisecond_edge_retains_every_trade_and_detects_saturation(monkeypatch):
    venue = sdk("gemini")
    rows = [gemini(i + 1) for i in range(205)]
    monkeypatch.setattr(venue, "privatePostV1Mytrades", lambda request: list(reversed(rows)))
    cursor, collected = {}, []
    for _ in range(3):
        page = fetch_trade_page(venue, "gemini-trades", "BTC/USD", cursor, 100)
        collected.extend(row["id"] for row in page.items)
        cursor = page.cursor
    assert page.caught_up and len(set(collected)) == 205 and len(cursor["seen_ids"]) == 205
    rows[:] = [gemini(i + 1) for i in range(500)]
    cursor = {}
    for _ in range(5):
        page = fetch_trade_page(venue, "gemini-trades", "BTC/USD", cursor, 100)
        assert not page.caught_up
        cursor = page.cursor
    with pytest.raises(ccxt.ExchangeError, match="saturated"):
        fetch_trade_page(venue, "gemini-trades", "BTC/USD", cursor, 100)


@pytest.mark.parametrize(
    "provider,kind", [("bitstamp", "bitstamp-transactions"), ("gemini", "gemini-trades")]
)
def test_embedded_native_order_fills_keep_history_identity_and_sell_side(monkeypatch, provider, kind):
    venue = sdk(provider)
    if provider == "gemini":
        document = {
            "order_id": "123",
            "symbol": "BTCUSD",
            "trades": [gemini(i + 1, type="Sell") for i in range(105)],
        }
        monkeypatch.setattr(venue, "privatePostV1OrderStatus", lambda request: document)
    else:
        document = {
            "id": "123",
            "market": "BTC/USD",
            "type": "1",
            "transactions": [
                {
                    "tid": i + 1,
                    "price": "10000",
                    "btc": "0.01",
                    "usd": "100",
                    "fee": "0.1",
                    "datetime": "2023-11-14 22:13:20.123000",
                    "type": 2,
                }
                for i in range(105)
            ],
        }
        monkeypatch.setattr(venue, "privatePostOrderStatus", lambda request: document)
    first = fetch_order_fill_page(venue, kind, "123", "BTC/USD", {}, 100)
    second = fetch_order_fill_page(venue, kind, "123", "BTC/USD", first.cursor, 100)
    assert len(first.items) == 100 and not first.caught_up and len(second.items) == 5 and second.caught_up
    assert all(
        row["side"] == "sell" and row["order"] == "123" and row["symbol"] == "BTC/USD" for row in first.items
    )
    assert first.items[0]["fees"] == [{"currency": "USD", "cost": 0.1}]
    bad = deepcopy(document)
    if provider == "gemini":
        bad["symbol"] = "ETHUSD"
        monkeypatch.setattr(venue, "privatePostV1OrderStatus", lambda request: bad)
    else:
        bad.pop("type")
        monkeypatch.setattr(venue, "privatePostOrderStatus", lambda request: bad)
    with pytest.raises(ccxt.ExchangeError):
        fetch_order_fill_page(venue, kind, "123", "BTC/USD", {}, 100)


@pytest.mark.parametrize("change", [{"symbol": "ETHUSD"}, {"tid": True}, {"order_id": None}])
def test_gemini_identity_ambiguity_never_advances_history(monkeypatch, change):
    venue = sdk("gemini")
    monkeypatch.setattr(venue, "privatePostV1Mytrades", lambda request: [gemini(1, **change)])
    with pytest.raises((ccxt.ExchangeError, ValueError)):
        fetch_trade_page(venue, "gemini-trades", "BTC/USD", {}, 100)


@pytest.mark.parametrize(
    "marker, expected", [("manual", "manual"), ("full", "full"), ("correct", "unverified")]
)
def test_gemini_breaks_at_inclusive_edge_and_in_exact_order_pages(monkeypatch, marker, expected):
    venue = sdk("gemini")
    row = gemini(1)
    monkeypatch.setattr(venue, "privatePostV1Mytrades", lambda request: [row])
    first = fetch_trade_page(venue, "gemini-trades", "BTC/USD", {}, 100)
    row["break"] = marker
    updated = fetch_trade_page(venue, "gemini-trades", "BTC/USD", first.cursor, 100)
    assert updated.items[0]["trade_break"] == expected
    assert updated.items[0]["id"] == first.items[0]["id"]
    assert not fetch_trade_page(venue, "gemini-trades", "BTC/USD", updated.cursor, 100).items
    document = {"order_id": "123", "symbol": "BTCUSD", "trades": [row]}
    monkeypatch.setattr(venue, "privatePostV1OrderStatus", lambda request: document)
    exact = fetch_order_fill_page(venue, "gemini-trades", "123", "BTC/USD", {}, 100)
    assert exact.items == updated.items and exact.caught_up


def test_gemini_break_updates_normalized_history_books_and_order_reconciliation(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    account = owner.store.add_connection(
        ConnectionCreate(exchange="gemini", label="Isolated Gemini", api_key="fake-key", secret="fake-secret")
    )
    venue = sdk("gemini")
    rows = [gemini(1), gemini(2, timestampms=STAMP + 1)]
    monkeypatch.setattr(
        venue,
        "privatePostV1Mytrades",
        lambda request: [r for r in rows if r["timestampms"] >= request["timestamp"]],
    )
    adapter = owner.market.client(account)
    monkeypatch.setattr(
        adapter, "fetch_trade_page", lambda *args: fetch_trade_page(venue, "gemini-trades", *args)
    )
    monkeypatch.setattr(
        adapter,
        "fetch_order_fill_page",
        lambda identity, symbol, cursor, limit=100: fetch_order_fill_page(
            venue, "gemini-trades", identity, symbol, cursor, limit
        ),
    )
    sync = owner.account_sync
    sync.enqueue(account, ["BTC/USD"])
    sync.tick()

    ledger = sync.ledger
    before = ledger.fills(account_id=account.id)
    busted_id = before["items"][0]["id"]
    assert before["fee_totals"] == {"USD": 0.2}
    assert owner.performance.report(account.id)["items"][0]["open_quantity"] == 0.02

    rows[1]["break"] = "full"
    sync.enqueue(account, ["BTC/USD"])
    sync.tick()
    after = ledger.fills(account_id=account.id)
    assert after["trade_breaks"] == {"full": 1} and after["total"] == 2
    assert after["fee_totals"] == {"USD": 0.1}
    assert after["items"][0]["trade_break"] == "full"
    monkeypatch.setattr(adapter, "market", lambda symbol: venue.market(symbol))
    monkeypatch.setattr(
        adapter._exchange,
        "fetch_my_trades",
        lambda symbol, **kwargs: [venue.parse_trade(rows[1], venue.market(symbol))],
    )
    recent = adapter.fetch_my_trades("BTC/USD")[0]
    assert recent["trade_break"] == "full" and "info" not in recent
    report = owner.performance.report(account.id)
    assert report["fill_count"] == 1 and report["items"][0]["open_quantity"] == 0.01
    (book,) = owner.performance.account_books.report(account.id, currency="USD")["reports"]
    btc = next(row for row in book["items"] if row["asset"] == "BTC")
    assert btc["quantity"] == 0.01 and btc["known_open_cost"] == pytest.approx(100.1)

    order = normalized_order(
        {
            "id": "123",
            "symbol": "BTC/USD",
            "side": "buy",
            "status": "closed",
            "filled": 0.01,
            "cost": 100,
            "timestamp": STAMP,
        }
    )
    with owner.store.db() as db:
        assert owner.trading.discovery._upsert(db, account, order) == "imported"
        identity = db.execute(
            "SELECT id FROM exchange_orders WHERE json_extract(payload,'$.exchange_order_id')='123'"
        ).fetchone()[0]
    # A native order detail without the flag cannot bring back the voided fill.
    detail = {"order_id": "123", "symbol": "BTCUSD", "trades": [gemini(1), gemini(2, timestampms=STAMP + 1)]}
    monkeypatch.setattr(venue, "privatePostV1OrderStatus", lambda request: detail)
    observed = owner.trading.reconciliation.sync(identity, manual=True)
    assert observed["reconciliation"]["status"] == "matched", observed["reconciliation"]
    assert observed["reconciliation"]["trade_breaks"] == {"full": 1}
    audit = history(owner.store, busted_id)["items"]
    assert len(audit) == 2 and audit[0]["payload"]["trade_break"] == "full"
    assert "trade_break" not in audit[1]["payload"]

    detail["trades"][0]["break"] = "manual"
    manual = owner.trading.reconciliation.sync(identity, manual=True)
    assert manual["reconciliation"]["status"] == "trade_break_review"
    assert manual["reconciliation"]["fill_count"] == 0
    assert manual["reconciliation"]["trade_breaks"] == {"manual": 1, "full": 1}
    report = owner.performance.report(account.id)
    assert report["items"][0]["net_matched_realized"] is None
    assert any("separate balance adjustments" in issue for issue in report["items"][0]["issues"])
    (book,) = owner.performance.account_books.report(account.id, currency="USD")["reports"]
    assert all(row["net_modeled_realized"] is None for row in book["items"])


def test_catalog_claims_implemented_history_and_scoped_recovery():
    for row in provider_catalog()["items"]:
        if row["id"] in {"bitstamp", "gemini"}:
            features = {item["id"]: item for group in row["support"] for item in group["features"]}
            assert features["history_import"]["status"] == "available"
            assert features["fill_reconciliation"]["status"] == "available"
            assert features["recovery"]["status"] == "available"
            if row["id"] == "bitstamp":
                assert "resting spot GTC" in features["recovery"]["detail"]
            assert features["automated"]["status"] == "pending"
