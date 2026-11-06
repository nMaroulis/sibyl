"""Native-shaped SDK fixtures exercise pagination and fees without private HTTP or orders."""

from copy import deepcopy

import ccxt
import pytest

from sibyl.exchanges.history import fetch_trade_page
from sibyl.exchanges.order_fills import fetch_order_fill_page
from sibyl.exchanges.registry import provider_catalog
from sibyl.models import ConnectionCreate
from sibyl.services.accounts.ledger import AccountLedger
from sibyl.services.accounts.sync import AccountSync

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


@pytest.mark.parametrize(
    "change", [{"break": "full"}, {"symbol": "ETHUSD"}, {"tid": True}, {"order_id": None}]
)
def test_gemini_reversal_or_identity_ambiguity_never_advances_history(monkeypatch, change):
    venue = sdk("gemini")
    monkeypatch.setattr(venue, "privatePostV1Mytrades", lambda request: [gemini(1, **change)])
    with pytest.raises((ccxt.ExchangeError, ValueError)):
        fetch_trade_page(venue, "gemini-trades", "BTC/USD", {}, 100)


def test_catalog_only_claims_implemented_history_and_retains_recovery_gaps():
    for row in provider_catalog()["items"]:
        if row["id"] in {"bitstamp", "gemini"}:
            features = {item["id"]: item for group in row["support"] for item in group["features"]}
            assert features["history_import"]["status"] == "available"
            assert features["fill_reconciliation"]["status"] == "available"
            assert features["recovery"]["status"] == "pending"
            assert features["automated"]["status"] == "pending"
