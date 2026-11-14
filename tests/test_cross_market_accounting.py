"""Real Decimal cross-pair lots, dated conversions, correction atomicity and API isolation."""

from decimal import Decimal

import pytest

from sibyl.accounting.executions.books import replay
from sibyl.accounting.executions.prices import HistoricalPrices
from sibyl.accounting.executions.service import AssetOpening
from sibyl.accounting.executions.versions import history
from sibyl.services.accounts.ledger import AccountLedger, ledger_fill

STAMP = 1_700_000_000_000


def fill(identity, symbol, side, quantity, price, *, fees=None, account="demo", offset=0):
    return ledger_fill(
        {
            "id": str(identity),
            "symbol": symbol,
            "side": side,
            "amount": quantity,
            "price": price,
            "cost": quantity * price,
            "timestamp": STAMP + offset,
            "fees": [{"currency": symbol.split("/")[1], "cost": 0}] if fees is None else fees,
        },
        {
            "account_id": account,
            "account": account,
            "exchange": "demo",
            "environment": "demo",
            "symbol": symbol,
        },
    )


def retain(client, rows):
    store = client.app.state.services.store
    with store.db() as db:
        db.execute("BEGIN IMMEDIATE")
        AccountLedger.upsert_fills(db, rows, "2026-01-01T00:00:00+00:00")


def prices(client, pair, price, *, source="demo", environment="demo", timestamp=None):
    market = client.app.state.services.market
    left = STAMP // 60_000 * 60_000 - 60_000 if timestamp is None else timestamp
    with market.store.db() as db:
        market.archive.commit_rows(
            db,
            {"source": source, "source_label": source, "environment": environment},
            pair,
            "1m",
            [[left, price, price, price, price, 0]],
        )


def opening(client, asset, quantity, cost):
    return client.app.state.services.performance.account_books.save_opening(
        "demo",
        AssetOpening(
            asset=asset,
            quantity=Decimal(str(quantity)),
            total_cost=Decimal(str(cost)),
            as_of="2023-01-01T00:00:00Z",
            note="Retained acquisition statement",
        ),
    )


def report(client):
    response = client.get("/api/v1/account-books?environment=demo&source=demo")
    assert response.status_code == 200, response.text
    return response.json()


def test_cross_pair_lots_and_third_currency_fees_retain_economic_cost(client):
    opening(client, "USDT", 1000, 1000)
    opening(client, "BNB", 0.1, 50)
    prices(client, "BNB/USDT", 1000)
    prices(client, "ETH/USDT", 10)
    retain(
        client,
        [
            fill(1, "BTC/USDT", "buy", 2, 100, fees=[{"currency": "BNB", "cost": 0.01}]),
            fill(2, "BTC/ETH", "sell", 1, 20, offset=1000),
            fill(3, "ETH/USDT", "sell", 10, 12, offset=2000),
        ],
    )
    result = report(client)
    rows = {row["asset"]: row for row in result["reports"][0]["items"]}
    assert rows["BTC"]["quantity"] == 1
    assert rows["BTC"]["known_open_cost"] == 105
    assert rows["BTC"]["matched_realized"] == 95
    assert rows["ETH"]["quantity"] == 10
    assert rows["ETH"]["known_open_cost"] == 100
    assert rows["ETH"]["matched_realized"] == 20
    assert rows["BNB"]["quantity"] == 0.09
    assert rows["BNB"]["matched_realized"] == 5
    assert sum(row["matched_realized"] for row in rows.values()) == 120
    assert result["complete_history"] is False
    assert result["reports"][0]["conversions"][0]["path"] == []


def test_missing_third_currency_rate_keeps_acquisition_cost_unknown(client):
    opening(client, "USDT", 1000, 1000)
    retain(
        client,
        [
            fill(1, "BTC/USDT", "buy", 2, 100, fees=[{"currency": "BNB", "cost": 0.01}]),
            fill(2, "BTC/USDT", "sell", 1, 150, offset=1000),
        ],
    )
    result = report(client)
    btc = next(row for row in result["reports"][0]["items"] if row["asset"] == "BTC")
    assert btc["unknown_open_quantity"] == 1
    assert btc["unknown_sold_quantity"] == 1
    assert btc["matched_realized"] == 0
    assert btc["net_modeled_realized"] is None


def test_foreign_rebate_lowers_purchase_cost_and_retains_rebate_inventory(client):
    opening(client, "USDT", 1000, 1000)
    prices(client, "BNB/USDT", 100)
    retain(client, [fill(1, "BTC/USDT", "buy", 1, 100, fees=[{"currency": "BNB", "cost": -0.01}])])
    rows = {row["asset"]: row for row in report(client)["reports"][0]["items"]}
    assert rows["BTC"]["known_open_cost"] == 99
    assert rows["BNB"]["quantity"] == 0.01
    assert rows["BNB"]["known_open_cost"] == 1


def test_historical_rates_never_read_future_close_stale_rate_or_other_environment(client):
    prices(client, "ETH/USDT", 10)
    prices(client, "ETH/USDT", 999, timestamp=STAMP // 60_000 * 60_000)
    prices(client, "BTC/USDT", 1000, environment="production")
    with client.app.state.services.store.db() as db:
        rates = HistoricalPrices(db, "demo", "demo", STAMP, STAMP + 100_000)
    assert rates.rate("ETH", "USDT", STAMP)[0] == 10
    assert rates.rate("ETH", "USDT", STAMP + 86_400_000 + 60_000) is None
    assert rates.rate("BTC", "USDT", STAMP) is None
    assert rates.rate("USD", "USDT", STAMP) is None
    assert rates.rate("USDT", "USDT", STAMP) == (Decimal(1), [])


def test_historical_inverse_and_bridge_routes_keep_actual_observations(client):
    prices(client, "USDT/ETH", 0.1)
    prices(client, "ALT/ETH", 0.2)
    with client.app.state.services.store.db() as db:
        rates = HistoricalPrices(db, "demo", "demo", STAMP, STAMP)
    rate, path = rates.rate("ALT", "USDT", STAMP)
    assert rate == 2
    assert len(path) == 2 and path[1]["inverse"]


def test_fill_versions_are_material_idempotent_and_atomic(client):
    row = fill(1, "BTC/USDT", "buy", 1, 100)
    retain(client, [row])
    retain(client, [row])
    changed = {**row, "fees": [{"currency": "USDT", "cost": 2}]}
    retain(client, [changed])
    store = client.app.state.services.store
    assert [entry["revision"] for entry in history(store, row["id"])["items"]] == [2, 1]
    assert history(store, row["id"])["items"][1]["payload"]["fees"][0]["cost"] == 0
    with pytest.raises(RuntimeError), store.db() as db:
        AccountLedger.upsert_fills(db, [{**changed, "notional": 102}], "2026-01-02T00:00:00Z")
        raise RuntimeError("checkpoint failed")
    assert history(store, row["id"])["total"] == 2
    assert client.get(f"/api/v1/account-books/fills/{row['id']}/versions").status_code == 200


def test_opening_revisions_date_validation_and_withdrawal_preserve_audit(client):
    saved = opening(client, "USDT", 1000, 1000)
    payload = {
        "asset": "USDT",
        "quantity": "900",
        "total_cost": "900",
        "as_of": "2023-01-01T00:00:00Z",
        "note": "Corrected statement",
        "revision": 0,
    }
    response = client.post("/api/v1/account-books/openings/demo", json=payload)
    assert response.status_code == 400
    payload["revision"] = saved["revision"]
    response = client.post("/api/v1/account-books/openings/demo", json=payload)
    assert response.status_code == 200
    assert response.json()["revision"] == 2
    assert client.get("/api/v1/account-books/openings").json()["items"][0]["quantity"] == "900"
    assert client.delete(f"/api/v1/account-books/openings/{saved['id']}?revision=1").status_code == 400
    assert client.delete(f"/api/v1/account-books/openings/{saved['id']}?revision=2").status_code == 200
    assert client.get("/api/v1/account-books/openings").json()["items"] == []
    with client.app.state.services.store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM asset_opening_audit").fetchone()[0] == 3
    retain(client, [fill(1, "BTC/USDT", "buy", 1, 100)])
    response = client.post(
        "/api/v1/account-books/openings/demo",
        json={**payload, "revision": 0, "asset": "BTC", "total_cost": "100", "as_of": "2024-01-01T00:00:00Z"},
    )
    assert response.status_code == 400


def test_cross_pair_transfer_carries_original_basis_to_a_different_market(client):
    prices(client, "ETH/USDT", 10)
    with client.app.state.services.store.db() as db:
        rates = HistoricalPrices(db, "demo", "demo", STAMP, STAMP + 10000)
    out = {
        "id": "out",
        "account_id": "source",
        "asset": "BTC",
        "timestamp_ms": STAMP + 1000,
        "posted_ms": STAMP + 1000,
    }
    inc = {
        "id": "in",
        "account_id": "destination",
        "asset": "BTC",
        "timestamp_ms": STAMP + 2000,
        "posted_ms": STAMP + 2000,
    }
    link = {
        "id": "link",
        "outgoing": out,
        "incoming": inc,
        "plan": {"source_debit": "1", "dispatch_quantity": "1", "destination_credit": "1"},
    }
    result = replay(
        "USDT",
        rates,
        [
            fill(1, "BTC/USDT", "buy", 1, 100, account="source"),
            fill(2, "BTC/ETH", "sell", 1, 20, account="destination", offset=3000),
        ],
        [out, inc],
        [],
        [link],
    )
    destination = next(
        row for row in result["items"] if row["account_id"] == "destination" and row["asset"] == "BTC"
    )
    assert destination["matched_realized"] == 100
    assert result["transfers"][0]["known_cost"] == 100


def test_native_accountant_reads_selected_books_without_a_balance_or_network_read(client, monkeypatch):
    def forbidden(*_a, **_kw):
        pytest.fail("Cross-pair evidence contacted a provider")

    monkeypatch.setattr(client.app.state.services.portfolio, "overview", forbidden)
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "accountant",
            "message": "Explain these books",
            "context": {
                "account_books_view": True,
                "account_books_currency": "USDT",
                "performance_account_id": "demo",
                "performance_environment": "demo",
                "market_source": "demo",
            },
        },
    )
    assert response.status_code == 200, response.text
    assert "credentials" not in response.text


def test_later_history_import_invalidates_overlapping_opening(client):
    saved = opening(client, "BTC", 1, 100)
    old = fill(1, "BTC/USDT", "buy", 2, 100)
    old["timestamp_ms"] = saved["timestamp_ms"] - 1000
    retain(client, [old])
    result = report(client)
    assert result["unapplied_openings"][0]["id"] == saved["id"]
    btc = next(row for row in result["reports"][0]["items"] if row["asset"] == "BTC")
    assert btc["quantity"] == 2  # Old opening was excluded, never doubled into three.


def test_retained_price_correction_changes_result_and_input_fingerprint(client):
    opening(client, "USDT", 1000, 1000)
    retain(client, [fill(1, "BTC/USDT", "buy", 1, 100), fill(2, "BTC/ETH", "sell", 1, 20, offset=1000)])
    prices(client, "ETH/USDT", 10)
    before = report(client)
    prices(client, "ETH/USDT", 12)
    after = report(client)
    assert before["input_fingerprint"] != after["input_fingerprint"]
    assert (
        next(row for row in before["reports"][0]["items"] if row["asset"] == "BTC")["matched_realized"] == 100
    )
    assert (
        next(row for row in after["reports"][0]["items"] if row["asset"] == "BTC")["matched_realized"] == 140
    )


def test_selected_books_cannot_change_reporting_currency_or_feed_during_inference(client, monkeypatch):
    from protolink import create_llm

    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    monkeypatch.setattr(
        "sibyl.agents.utils.registry.create_llm",
        lambda *_a, **_kw: create_llm(
            "mock",
            sequential_responses=[
                {
                    "type": "tool_call",
                    "tool": "account_asset_books",
                    "args": {"source": "binance", "currency": "BTC"},
                },
                "I used the selected report and disclosed its scope.",
            ],
        ),
    )
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "accountant",
            "message": "Explain this selected report",
            "context": {
                "account_books_view": True,
                "account_books_currency": "USDT",
                "market_source": "demo",
                "performance_environment": "demo",
            },
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["evidence"]["currency"] == "USDT"
    assert response.json()["evidence"]["source"] == "demo"
