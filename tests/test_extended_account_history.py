"""Native parser contracts, retention boundaries and revision-safe history rescans."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import ccxt
import pytest

from sibyl.exchanges import create_client
from sibyl.exchanges.funding import DAY, fetch_funding_page
from sibyl.exchanges.history import TradePage
from sibyl.exchanges.registry import provider_catalog
from sibyl.services.account_sync import AccountSync
from sibyl.services.market import Market

START = 1_704_067_200_000
END = START + 30 * DAY
METHODS = {
    "okx": "privateGetTradeFillsHistory",
    "bybit": "privateGetV5ExecutionList",
    "kucoin": "privateGetHfFills",
    "bitget": "privateSpotGetV2SpotTradeFills",
}


@pytest.fixture(params=list(METHODS))
def venue(request, monkeypatch):
    """Use the real SDK parser and client gates; replace only the final transport."""
    client = create_client(
        request.param, credentials={"apiKey": "key", "secret": "secret", "password": "pass"}
    )
    market = {
        "id": "BTC-USDT" if request.param in {"okx", "kucoin"} else "BTCUSDT",
        "symbol": "BTC/USDT",
        "base": "BTC",
        "quote": "USDT",
        "baseId": "BTC",
        "quoteId": "USDT",
        "type": "spot",
        "spot": True,
        "contract": False,
        "active": True,
        "precision": {"amount": 0.00000001, "price": 0.01},
        "limits": {},
        "info": {},
    }
    client._exchange.set_markets([market])
    monkeypatch.setattr(client._exchange, "milliseconds", lambda: END)
    yield client
    client.close()


def native(provider, identity="9007199254740995", **changes):
    """Two fills may share a millisecond; cursor IDs must remain exact strings."""
    row = {
        "okx": {
            "instType": "SPOT",
            "instId": "BTC-USDT",
            "subType": "1",
            "side": "buy",
            "fillSz": "0.01",
            "fillPx": "100",
            "fee": "-0.001",
            "feeCcy": "USDT",
            "ordId": "order-1",
            "billId": identity,
            "tradeId": identity,
            "ts": str(START + DAY + 10),
            "fillTime": str(START + DAY),
        },
        "bybit": {
            "symbol": "BTCUSDT",
            "side": "Buy",
            "execQty": "0.01",
            "execPrice": "100",
            "execValue": "1",
            "execFee": "0.001",
            "feeCoin": "USDT",
            "execId": identity,
            "execTime": str(START + DAY),
            "orderId": "order-1",
            "execType": "Trade",
            "isLeverage": "0",
        },
        "kucoin": {
            "symbol": "BTC-USDT",
            "side": "buy",
            "size": "0.01",
            "price": "100",
            "funds": "1",
            "fee": "0.001",
            "feeCurrency": "USDT",
            "tradeId": identity,
            "id": identity,
            "orderId": "order-1",
            "createdAt": START + DAY,
            "tradeType": "TRADE",
        },
        "bitget": {
            "symbol": "BTCUSDT",
            "side": "buy",
            "size": "0.01",
            "priceAvg": "100",
            "amount": "1",
            "feeDetail": {"feeCoin": "USDT", "totalFee": "-0.001", "deduction": "no"},
            "tradeId": identity,
            "orderId": "order-1",
            "cTime": str(START + DAY),
        },
    }[provider]
    return {**row, **changes, "info": "PRIVATE-RAW"}


def response(provider, rows, following=None):
    if provider == "bybit":
        return {"result": {"category": "spot", "list": rows, "nextPageCursor": following or ""}}
    if provider == "kucoin":
        return {
            "data": {
                "items": rows,
                "lastId": following if following is not None else rows[-1]["id"] if rows else None,
            }
        }
    return {"data": rows}


def transport(monkeypatch, client, pages):
    seen = []

    def read(request):
        seen.append(request.copy())
        return next(pages)

    monkeypatch.setattr(client._exchange, METHODS[client.id], read)
    return seen


def test_exact_native_pagination_keeps_timestamp_ties_and_large_ids(venue, monkeypatch):
    first = [native(venue.id), native(venue.id, "9007199254740994")]
    seen = transport(
        monkeypatch,
        venue,
        iter(
            [
                response(venue.id, first, "opaque-next" if venue.id == "bybit" else None),
                response(venue.id, []),
            ]
        ),
    )
    initial = {"start": START, "end": END if venue.id != "bybit" else START + 7 * DAY - 1}
    page = venue.fetch_trade_page("BTC/USDT", initial, 2)
    assert not page.caught_up and len(page.items) == 2
    assert {row["timestamp"] for row in page.items} == {START + DAY}
    assert {row["id"] for row in page.items} == {"9007199254740995", "9007199254740994"}
    assert page.items[0]["fees"] == [{"currency": "USDT", "cost": 0.001}]
    assert "PRIVATE" not in json.dumps(page.items)
    terminal = venue.fetch_trade_page("BTC/USDT", page.cursor, 2)
    assert terminal.caught_up and terminal.cursor == {"start": initial["end"] - DAY}
    key = {"okx": "after", "bybit": "cursor", "kucoin": "lastId", "bitget": "idLessThan"}[venue.id]
    assert seen[1][key] == ("opaque-next" if venue.id == "bybit" else "9007199254740994")
    assert seen[0]["limit"] == seen[1]["limit"] == 2


def test_provider_default_retention_is_explicit_and_frozen(venue, monkeypatch):
    seen = transport(monkeypatch, venue, iter([response(venue.id, [])]))
    page = venue.fetch_trade_page("BTC/USDT", {})
    start_key = {"okx": "begin", "bybit": "startTime", "kucoin": "startAt", "bitget": "startTime"}[venue.id]
    days = {"okx": 89, "bybit": 730, "kucoin": 7, "bitget": 89}[venue.id]
    assert seen[0][start_key] == END - days * DAY
    if venue.id == "bybit":
        assert not page.caught_up
        assert page.cursor["end"] == END
        assert page.cursor["window_start"] == END - (730 - 7) * DAY
    else:
        assert page.caught_up


def test_wrong_market_rejects_whole_native_page(venue, monkeypatch):
    row = native(venue.id, **({"instId": "ETH-USDT"} if venue.id == "okx" else {"symbol": "ETHUSDT"}))
    transport(monkeypatch, venue, iter([response(venue.id, [row])]))
    with pytest.raises(ccxt.ExchangeError, match="market"):
        venue.fetch_trade_page("BTC/USDT", {})


def test_order_reads_filter_at_source_and_validate_native_order(venue, monkeypatch):
    if venue.id == "bitget":
        with pytest.raises(ccxt.NotSupported):
            venue.fetch_order_fill_page("order-1", "BTC/USDT", {})
        return
    seen = transport(
        monkeypatch, venue, iter([response(venue.id, [native(venue.id)]), response(venue.id, [])])
    )
    page = venue.fetch_order_fill_page("order-1", "BTC/USDT", {"start": START, "end": START + DAY * 2})
    assert page.items[0]["order"] == "order-1"
    if venue.id != "bybit":
        assert not page.caught_up
        assert venue.fetch_order_fill_page("order-1", "BTC/USDT", page.cursor).caught_up
    else:
        assert page.caught_up
    assert seen[0]["ordId" if venue.id == "okx" else "orderId"] == "order-1"
    bad = native(venue.id, **({"ordId": "other"} if venue.id == "okx" else {"orderId": "other"}))
    transport(monkeypatch, venue, iter([response(venue.id, [bad])]))
    with pytest.raises(ccxt.ExchangeError, match="order"):
        venue.fetch_order_fill_page("order-1", "BTC/USDT", {})


def test_repeated_or_regressing_cursor_fails_closed(venue, monkeypatch):
    transport(
        monkeypatch,
        venue,
        iter([response(venue.id, [native(venue.id)], "same" if venue.id == "bybit" else None)]),
    )
    with pytest.raises(ccxt.ExchangeError, match="cursor|identity"):
        venue.fetch_trade_page(
            "BTC/USDT",
            {"start": START, "end": END, "page": "same" if venue.id == "bybit" else "9007199254740995"},
        )


def test_unreviewed_charges_or_missing_identity_cannot_silently_enter_history(venue, monkeypatch):
    changes = {
        "okx": {"subType": "324"},
        "bybit": {"extraFees": [{"feeCoin": "USDT", "fee": "0.1"}]},
        "kucoin": {"tax": "invalid"},
        "bitget": {"tradeId": None},
    }[venue.id]
    transport(monkeypatch, venue, iter([response(venue.id, [native(venue.id, **changes)])]))
    with pytest.raises(ccxt.ExchangeError):
        venue.fetch_trade_page("BTC/USDT", {})


def test_kucoin_self_trade_legs_use_account_fill_ids(venue, monkeypatch):
    if venue.id != "kucoin":
        return
    transport(
        monkeypatch,
        venue,
        iter([response("kucoin", [native("kucoin", id="22"), native("kucoin", id="21", side="sell")])]),
    )
    page = venue.fetch_trade_page("BTC/USDT", {}, 3)
    assert {row["id"] for row in page.items} == {"21", "22"}


def test_bybit_windows_advance_without_skipping_inclusive_boundary(venue, monkeypatch):
    if venue.id != "bybit":
        return
    seen = transport(
        monkeypatch,
        venue,
        iter(
            [response("bybit", [], ""), response("bybit", [native("bybit")], "next"), response("bybit", [])]
        ),
    )
    first = venue.fetch_trade_page("BTC/USDT", {"start": START, "end": START + 10 * DAY})
    assert not first.caught_up
    second = venue.fetch_trade_page("BTC/USDT", first.cursor)
    assert not second.caught_up
    third = venue.fetch_trade_page("BTC/USDT", second.cursor)
    assert third.caught_up
    assert seen[1]["startTime"] == seen[0]["endTime"] + 1
    assert seen[1]["startTime"] == seen[2]["startTime"]
    assert seen[2]["cursor"] == "next"


@pytest.fixture
def sync(settings, store):
    service = AccountSync(Market(settings, store), store)
    yield service
    service.close()
    service.market.close()


def fill(identity="1", **changes):
    return {
        "id": identity,
        "order": "order-1",
        "symbol": "BTC/USDT",
        "side": "buy",
        "timestamp": START,
        "amount": 0.01,
        "price": 100,
        "cost": 1,
        "fees": [{"currency": "USDT", "cost": 0.001}],
        **changes,
    }


def test_rescan_updates_old_fees_retains_out_of_range_evidence_and_reports_pass(sync, monkeypatch):
    account = sync.store.connections()[0]
    client = sync.market.client(account)
    monkeypatch.setattr(
        client, "fetch_trade_page", lambda *args: TradePage([fill(), fill("old")], {"after": "saved"}, True)
    )
    sync.enqueue(account, ["BTC/USDT"])
    sync.tick()
    seen = []

    def corrected(symbol, cursor, limit):
        seen.append(cursor)
        return TradePage([fill(fees=[{"currency": "BNB", "cost": -0.01}])], {}, True)

    monkeypatch.setattr(client, "fetch_trade_page", corrected)
    sync.enqueue(account, ["BTC/USDT"], "rescan")
    sync.tick()
    job = sync.snapshot()["jobs"][0]
    assert seen == [{}] and job["record_count"] == 2
    assert job["last_pass"]["mode"] == "rescan" and job["last_pass"]["updated"] == 1
    assert job["last_pass"]["inserted"] == 0 and job["complete_history"] is False
    assert job["oldest_timestamp_ms"] == job["newest_timestamp_ms"] == START
    assert sync.ledger.fills()["fee_totals"] == {"BNB": -0.01, "USDT": 0.001}


@pytest.mark.parametrize("failure", [False, True])
def test_new_rescan_ignores_old_inflight_result_or_failure(sync, monkeypatch, failure):
    entered, release = Event(), Event()
    account = sync.store.connections()[0]

    def read(*args):
        entered.set()
        assert release.wait(3)
        if failure:
            raise ccxt.AuthenticationError("PRIVATE")
        return TradePage([fill("obsolete")], {"old": "cursor"}, True)

    monkeypatch.setattr(sync.market.client(account), "fetch_trade_page", read)
    sync.enqueue(account, ["BTC/USDT"])
    with ThreadPoolExecutor() as pool:
        task = pool.submit(sync.tick)
        assert entered.wait(3)
        sync.pause(account.id)
        sync.enqueue(account, ["BTC/USDT"], "rescan")
        release.set()
        task.result(3)
    job = sync.snapshot()["jobs"][0]
    assert job["status"] == "queued" and job["error"] is None
    assert job["pages"] == 0 and sync.ledger.fills()["total"] == 0
    with sync.store.db() as db:
        assert sync.ledger.read_job(db, account.id, "BTC/USDT")["cursor"] == {}


def test_active_rescan_is_rejected_and_pause_resume_preserves_mode(sync, monkeypatch):
    account = sync.store.connections()[0]
    monkeypatch.setattr(
        sync.market.client(account), "fetch_trade_page", lambda *args: TradePage([fill()], {"next": 1}, False)
    )
    sync.enqueue(account, ["BTC/USDT"], "rescan")
    with pytest.raises(ValueError, match="Pause"):
        sync.enqueue(account, ["BTC/USDT"], "rescan")
    sync.tick()
    sync.pause(account.id)
    sync.enqueue(account, ["BTC/USDT"])
    job = sync.snapshot()["jobs"][0]
    assert job["mode"] == "rescan" and job["pass_pages"] == 1


def test_rescan_api_validation_and_no_private_revision(client):
    path = "/api/v1/connections/demo/sync"
    assert client.post(path, json={"symbols": ["BTC/USDT"], "mode": "delete"}).status_code == 422
    response = client.post(path, json={"symbols": ["BTC/USDT"], "mode": "rescan"})
    assert response.status_code == 202
    assert "revision" not in response.text and "cursor" not in response.text


def test_bybit_funding_uses_29_day_slices_and_native_withdrawal_ids(monkeypatch):
    client = create_client("bybit", credentials={"apiKey": "key", "secret": "secret"})
    seen = []
    responses = iter(
        [
            {
                "result": {
                    "rows": [
                        {
                            "withdrawId": "9007199254740995",
                            "coin": "BTC",
                            "amount": "0.1",
                            "withdrawFee": "0.001",
                            "createTime": str(START + DAY),
                            "status": "Pending",
                            "withdrawType": 0,
                            "tax": "0",
                            "toAddress": "PRIVATE",
                        }
                    ],
                    "nextPageCursor": "next",
                }
            },
            {"result": {"rows": [], "nextPageCursor": ""}},
            {"result": {"rows": [], "nextPageCursor": ""}},
        ]
    )

    def read(request):
        seen.append(request)
        return next(responses)

    monkeypatch.setattr(client._exchange, "privateGetV5AssetWithdrawQueryRecord", read)
    try:
        first = fetch_funding_page(client._exchange, "bybit", "withdrawal", {"start": START, "end": END})
        assert first.items[0]["native_id"] == "9007199254740995" and first.items[0]["status"] == "pending"
        assert first.items[0]["fee"] == {"currency": "BTC", "cost": "0.001"}
        assert "PRIVATE" not in json.dumps(first.items)
        second = fetch_funding_page(client._exchange, "bybit", "withdrawal", first.cursor)
        assert not second.caught_up
        third = fetch_funding_page(client._exchange, "bybit", "withdrawal", second.cursor)
        assert third.caught_up
        assert seen[1]["cursor"] == "next" and seen[2]["startTime"] == seen[1]["endTime"] + 1
        assert all(row["endTime"] - row["startTime"] < 30 * DAY and row["withdrawType"] == 0 for row in seen)
    finally:
        client.close()


def test_catalog_separates_import_reconciliation_and_funding_support():
    catalog = {row["id"]: row for row in provider_catalog()["items"]}
    for name in METHODS:
        features = {row["id"]: row for group in catalog[name]["support"] for row in group["features"]}
        assert features["history_import"]["status"] == "available"
        assert features["fill_reconciliation"]["status"] == ("pending" if name == "bitget" else "available")
    assert catalog["binance-testnet"]["history_import"] == "binance-id"
    bybit = {row["id"]: row for group in catalog["bybit"]["support"] for row in group["features"]}
    assert bybit["funding"]["status"] == "available"
    assert bybit["funding"]["label"] == "On-chain withdrawal history"
    assert "Deposits" in bybit["funding"]["detail"] and "pending" in bybit["funding"]["detail"]
