"""Offline FIFO, basis assertions and opt-in balance/mark evidence contracts."""

import json

import pytest

from sibyl.models import ConnectionCreate
from sibyl.services.ledger import AccountLedger, ledger_fill
from sibyl.services.market import Market
from sibyl.services.performance import AccountPerformance, OpeningInventory, fifo


def execution(identity=1, *, side="buy", quantity=1, price=100, fees=None, **values):
    """Use the same normalization boundary as native history imports."""
    symbol = values.pop("symbol", "BTC/USDT")
    account = values.pop("account_id", "demo")
    environment = values.pop("environment", "demo")
    return ledger_fill(
        {
            "id": str(identity),
            "symbol": symbol,
            "side": side,
            "timestamp": 1_700_000_000_000 + identity * 1000,
            "amount": quantity,
            "price": price,
            "cost": quantity * price,
            "fees": [{"currency": symbol.split("/")[1], "cost": 0}] if fees is None else fees,
            **values,
        },
        {
            "account_id": account,
            "account": account,
            "exchange": "demo",
            "environment": environment,
            "symbol": symbol,
        },
    )


def retained(service, *rows):
    """Persist normalized facts without executing orders or scheduling provider reads."""
    with service.store.db() as db:
        for row in rows:
            db.execute(
                "INSERT INTO account_fills VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (
                    row["id"],
                    row["account_id"],
                    row["symbol"],
                    row["trade_id"],
                    row["timestamp_ms"],
                    json.dumps(row),
                    row["created_at"],
                    row["created_at"],
                ),
            )


@pytest.fixture
def performance(settings, store):
    AccountLedger(store)
    market = Market(settings, store)
    yield AccountPerformance(market, store)
    market.close()


def opening(**values):
    return OpeningInventory(
        symbol="BTC/USDT", quantity="2", total_cost="160", as_of="2023-01-01T00:00:00Z", **values
    )


def test_fifo_chronology_partial_lots_and_decimal_fees():
    result = fifo(
        [
            execution(3, side="sell", quantity=1.5, price=150, fees=[{"currency": "USDT", "cost": 2}]),
            execution(1, fees=[{"currency": "USDT", "cost": 1}]),
            execution(2, price=120),
        ]
    )
    assert result["net_matched_realized"] == 62  # 223 proceeds - 101 - 60 basis
    assert result["known_open_cost"] == 60
    assert result["open_quantity"] == 0.5
    assert result["fee_totals"] == {"USDT": 3}
    assert result["disposals"][0]["matched_cost"] == 161


@pytest.mark.parametrize(
    "side,fee,expected_qty,expected_pnl",
    [
        ("buy", 0.1, 0.4, 175 / 9),  # .9 received; .5 sold, pro-rata cost
        ("buy", -0.1, 0.6, 150 - 100 / 1.1 / 2),
        ("sell", 0.1, 0.4, 15),  # 75 proceeds less 60 basis, including base fee
        ("sell", -0.1, 0.6, 35),
    ],
)
def test_base_fees_and_rebates_change_inventory(side, fee, expected_qty, expected_pnl):
    rows = [execution(1), execution(2, side="sell", quantity=0.5, price=150)]
    row = rows[0 if side == "buy" else 1]
    row["fees"] = [{"currency": "BTC", "cost": fee}]
    result = fifo(rows)
    assert result["open_quantity"] == pytest.approx(expected_qty)
    # Buy fee scenarios have 75 proceeds, not 150.
    if side == "buy":
        expected_pnl = 75 - 100 * 0.5 / (1 - fee)
    assert result["net_matched_realized"] == pytest.approx(expected_pnl)


def test_quote_rebate_signs_are_preserved():
    result = fifo(
        [
            execution(1, fees=[{"currency": "USDT", "cost": -2}]),
            execution(2, side="sell", price=120, fees=[{"currency": "USDT", "cost": -1}]),
        ]
    )
    assert result["net_matched_realized"] == 23
    assert result["fee_totals"] == {"USDT": -3}


@pytest.mark.parametrize("fee", [[], [{"currency": "BTC", "cost": None}], [{"currency": None, "cost": 0.1}]])
def test_missing_acquisition_fee_never_creates_known_zero_basis(fee):
    result = fifo([execution(1, fees=fee), execution(2, side="sell", price=150)])
    assert result["net_matched_realized"] is None
    assert result["unknown_sold_quantity"] == 1
    assert result["realized_before_other_fees"] == 0
    assert result["missing_fee_count"] == 1


def test_missing_sale_fee_suppresses_final_net_but_keeps_provisional_match():
    result = fifo([execution(1), execution(2, side="sell", price=120, fees=[])])
    assert result["realized_before_other_fees"] == 20
    assert result["net_matched_realized"] is None


@pytest.mark.parametrize("cost", [0.01, -0.01])
def test_third_currency_fees_and_rebates_remain_native(cost):
    result = fifo(
        [execution(1), execution(2, side="sell", price=130, fees=[{"currency": "BNB", "cost": cost}])]
    )
    assert result["realized_before_other_fees"] == 30
    assert result["net_matched_realized"] is None
    assert result["fee_totals"] == {"USDT": 0, "BNB": cost}
    assert result["unconverted_fee_currencies"] == ["BNB"]


def test_unknown_opening_consumed_before_known_purchases_and_partial_proceeds():
    result = fifo(
        [execution(1), execution(2, side="sell", quantity=2, price=150)],
        {"quantity": "1", "total_cost": None},
    )
    assert result["unknown_sold_quantity"] == 1
    assert result["matched_sold_quantity"] == 1
    assert result["net_matched_realized"] == 50  # Only the known half's proceeds.
    assert result["disposals"][0]["matched_proceeds"] == 150


def test_unmatched_sell_never_uses_a_future_buy():
    result = fifo([execution(1, side="sell", price=110), execution(2, price=90)])
    assert result["unknown_sold_quantity"] == 1
    assert result["realized_before_other_fees"] == 0
    assert result["open_quantity"] == 1
    assert result["known_open_cost"] == 90


def test_explicit_zero_opening_cost_is_distinct_from_unknown():
    rows = [execution(1, side="sell", price=100)]
    assert fifo(rows, {"quantity": "1", "total_cost": "0"})["net_matched_realized"] == 100
    assert fifo(rows, {"quantity": "1", "total_cost": None})["unknown_sold_quantity"] == 1


def test_same_timestamp_ordering_and_estimated_notional_are_provisional():
    result = fifo([execution(1), execution(2, side="sell", timestamp=1_700_000_001_000)])
    assert not result["net_known"] and "timestamp" in " ".join(result["issues"])
    result = fifo([execution(1), execution(2, side="sell", price=125, cost=None)])
    assert result["realized_before_other_fees"] == 25
    assert not result["net_known"]


def test_inconsistent_fees_block_matching_instead_of_negative_lots():
    result = fifo([execution(1, fees=[{"currency": "BTC", "cost": 2}]), execution(2, side="sell")])
    assert result["matching_blocked"]
    assert result["net_matched_realized"] is None


def test_decimal_internal_arithmetic_avoids_binary_residual_inventory():
    result = fifo(
        [
            execution(1, quantity=0.1),
            execution(2, quantity=0.2),
            execution(3, side="sell", quantity=0.3, price=101),
        ]
    )
    assert result["open_quantity"] == 0
    assert result["net_matched_realized"] == pytest.approx(0.3)


def test_overflow_remains_json_safe_and_suppresses_marking(performance):
    retained(performance, execution(1, quantity=1e300, price=1e200, cost=None))
    data = performance.report()
    assert data["items"][0]["matching_blocked"]
    assert data["items"][0]["known_open_cost"] is None
    json.dumps(data, allow_nan=False)


def test_report_account_environment_and_quote_totals_never_mix(performance):
    retained(
        performance,
        execution(1),
        execution(2, side="sell", price=120),
        execution(1, symbol="ETH/USD", account_id="prod", environment="production"),
        execution(2, symbol="ETH/USD", account_id="prod", environment="production", side="sell", price=130),
        execution(1, account_id="test", environment="test"),
        execution(2, account_id="test", environment="test", side="sell", price=140),
    )
    data = performance.report()
    assert {(x["environment"], x["quote"], x["net_matched_realized"]) for x in data["totals"]} == {
        ("demo", "USDT", 20),
        ("production", "USD", 30),
        ("test", "USDT", 40),
    }
    assert performance.report(account_id="test")["fill_count"] == 2
    assert performance.report(symbol="ETH/USD")["fill_count"] == 2
    assert performance.report(environment="demo")["fill_count"] == 2
    assert data["complete_history"] is False


def test_filtered_market_still_detects_cross_market_base_or_quote_inventory(performance):
    retained(performance, execution(1), execution(2, side="sell", price=120), execution(3, symbol="ETH/BTC"))
    data = performance.report(symbol="BTC/USDT")
    assert data["items"][0]["cross_market"]
    assert data["items"][0]["net_matched_realized"] is None
    assert data["totals"][0]["matched_realized"] == 20


def test_basis_saved_separately_survives_restart_and_is_audited(performance):
    request = opening()
    result = performance.save_opening("demo", request)
    assert result["total_cost"] == "160"
    retained(performance, execution(1, side="sell", quantity=0.5, price=100))
    restarted = AccountPerformance(performance.market, performance.store)
    row = restarted.report()["items"][0]
    assert row["opening_applied"] and row["net_matched_realized"] == 10
    assert row["open_quantity"] == 1.5 and row["known_open_cost"] == 120
    with performance.store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM account_fills").fetchone()[0] == 1
    performance.remove_opening("demo", "BTC/USDT")
    assert restarted.report()["items"][0]["unknown_sold_quantity"] == 0.5
    audit = restarted.audit("demo", "BTC/USDT")["items"]
    assert [x["action"] for x in audit] == ["remove", "save"]
    assert audit[0]["before"]["total_cost"] == "160"


def test_opening_overlap_after_earlier_import_is_ignored(performance):
    performance.save_opening("demo", opening())
    retained(performance, execution(1, side="sell", timestamp=1_600_000_000_000))
    row = performance.report()["items"][0]
    assert not row["opening_applied"] and not row["net_known"]
    assert any("overlaps" in x for x in row["issues"])
    with pytest.raises(ValueError, match="before the first"):
        performance.save_opening("demo", opening())
    assert len(performance.audit("demo", "BTC/USDT")["items"]) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("quantity", 0),
        ("quantity", "NaN"),
        ("quantity", "Infinity"),
        ("total_cost", -1),
        ("as_of", "2099-01-01T00:00:00Z"),
        ("as_of", "2023-01-01T00:00:00"),
        ("symbol", "BTC/USDT:USDT"),
    ],
)
def test_opening_api_rejects_invalid_assertions(client, field, value):
    payload = {
        "symbol": "BTC/USDT",
        "quantity": "1",
        "total_cost": "100",
        "as_of": "2023-01-01T00:00:00Z",
        field: value,
    }
    assert client.post("/api/v1/connections/demo/opening-inventory", json=payload).status_code == 422


def test_api_basis_report_audit_and_delete(client):
    url = "/api/v1/connections/demo/opening-inventory"
    payload = opening().model_dump(mode="json")
    assert client.post(url.replace("demo", "missing"), json=payload).status_code == 404
    assert client.post(url, json=payload).status_code == 200
    report = client.get("/api/v1/account-ledger/performance?side=sell&offset=100")
    assert report.headers["Cache-Control"] == "no-store"
    assert report.json()["items"][0]["open_quantity"] == 2
    assert client.get(url + "/audit?symbol=BTC/USDT").json()["items"][0]["after"]["total_cost"] == "160"
    assert client.delete(url + "?symbol=BTC/USDT").status_code == 204
    assert client.get("/api/v1/account-ledger/performance").json()["items"] == []


def test_example_has_computed_results_and_no_side_effects(client):
    before = client.get("/api/v1/account-ledger/fills").json()
    sample = client.get("/api/v1/account-ledger/performance/example").json()
    assert sample["example"] and sample["items"][0]["disposal_count"] == 2
    assert sample["items"][0]["net_matched_realized"] == pytest.approx(2756.53)
    assert sample["items"][0]["open_quantity"] == pytest.approx(0.08998)
    assert client.get("/api/v1/account-ledger/fills").json() == before
    assert client.app.state.services.store.orders() == []
    assert client.get("/api/v1/account-ledger/performance").json()["items"] == []


def test_regular_report_never_calls_private_balance_or_market(performance, monkeypatch):
    retained(performance, execution(1))
    monkeypatch.setattr(performance.market, "account_balances", lambda *_: pytest.fail("private read"))
    monkeypatch.setattr(performance.market, "metadata", lambda *_: pytest.fail("market read"))
    assert performance.report()["items"][0]["mark_status"] == "not_requested"


def test_current_mark_requires_matching_balance_known_basis_and_active_account(performance, monkeypatch):
    retained(performance, execution(1))
    monkeypatch.setattr(performance.market, "account_balances", lambda *_: [{"asset": "BTC", "total": 1}])
    monkeypatch.setattr(
        "sibyl.services.performance.Valuation.price",
        lambda _, asset: {"price": 120 if asset == "BTC" else 1, "status": "undated", "route": []},
    )
    row = performance.report(mark=True)["items"][0]
    assert row["unrealized"] == 20 and row["mark_status"] == "undated"
    assert row["mark_source"]["source"] == "demo"
    monkeypatch.setattr(performance.market, "account_balances", lambda *_: [{"asset": "BTC", "total": 2}])
    assert performance.report(mark=True)["items"][0]["unrealized"] is None
    performance.store.activate_account("demo", False)
    monkeypatch.setattr(
        performance.market, "account_balances", lambda *_: pytest.fail("inactive private read")
    )
    assert performance.report(mark=True)["items"][0]["unrealized"] is None


def test_unknown_inventory_and_stale_rates_are_not_marked(performance, monkeypatch):
    retained(performance, execution(1, fees=[]))
    monkeypatch.setattr(performance.market, "account_balances", lambda *_: [{"asset": "BTC", "total": 1}])
    monkeypatch.setattr(
        "sibyl.services.performance.Valuation.price", lambda *_: pytest.fail("Unknown lots cannot be marked")
    )
    assert performance.report(mark=True)["items"][0]["unrealized"] is None
    retained(performance, execution(1))
    monkeypatch.setattr(
        "sibyl.services.performance.Valuation.price", lambda *_: {"price": None, "status": "stale"}
    )
    assert performance.report(mark=True)["items"][0]["unrealized"] is None


def test_closed_inventory_requires_no_conversion_quotes(performance, monkeypatch):
    retained(performance, execution(1), execution(2, side="sell"))
    monkeypatch.setattr(performance.market, "account_balances", lambda *_: [])
    monkeypatch.setattr("sibyl.services.performance.Valuation.price", lambda *_: pytest.fail("No open lots"))
    assert performance.report(mark=True)["items"][0]["unrealized"] == 0


def test_demo_feed_never_marks_actual_exchange_inventory(performance, monkeypatch):
    account = performance.store.add_connection(
        ConnectionCreate(exchange="binance", label="Real", api_key="key", secret="secret")
    )
    retained(performance, execution(1, account_id=account.id, environment="production"))
    monkeypatch.setattr(performance.market, "account_balances", lambda *_: pytest.fail("Demo source blocked"))
    assert performance.report(mark=True)["items"][0]["unrealized"] is None


def test_report_does_not_silently_truncate_history(performance, monkeypatch):
    retained(performance, execution(1), execution(2))
    monkeypatch.setattr("sibyl.services.performance.MAX_FILLS", 1)
    with pytest.raises(ValueError, match="never silently truncated"):
        performance.report()


def test_disconnected_history_and_basis_remain_readable(performance, monkeypatch):
    performance.save_opening("demo", opening())
    retained(performance, execution(1, side="sell"))
    performance.store.delete_connection("demo")
    monkeypatch.setattr(performance.market, "account_balances", lambda *_: pytest.fail("Disconnected"))
    assert performance.report(mark=True)["items"][0]["net_matched_realized"] == 20
    assert performance.audit("demo", "BTC/USDT")["items"]


def test_accountant_reads_selected_fifo_via_protolink_without_private_reads(client, monkeypatch):
    service = client.app.state.services
    retained(service.performance, execution(1), execution(2, side="sell", price=120))
    monkeypatch.setattr(
        service.market, "account_balances", lambda *_: pytest.fail("FIFO assistant must not request balances")
    )
    monkeypatch.setattr(
        service.portfolio, "overview", lambda *_: pytest.fail("Use selected FIFO evidence, not portfolio")
    )
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "accountant",
            "message": "Explain this report.",
            "context": {
                "performance_view": True,
                "performance_account_id": "demo",
                "symbol": "BTC/USDT",
                "performance_environment": "demo",
            },
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["engine"] == "ProtoLink" and result["evidence"]["view"] == "performance"
    assert result["evidence"]["totals"][0]["net_matched_realized"] == 20
    assert "20.0000 USDT" in result["answer"]
    assert "account returns" in result["answer"]
    assert "curve" not in result["evidence"]["items"][0]


def test_accountant_example_is_isolated_from_real_retained_fills(client):
    retained(client.app.state.services.performance, execution(1))
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "accountant",
            "message": "Explain this example.",
            "context": {"performance_view": True, "performance_example": True},
        },
    )
    assert response.json()["evidence"]["example"]
    assert response.json()["evidence"]["fill_count"] == 4
    assert response.json()["answer"].startswith("Example calculation.")
    assert client.get("/api/v1/account-ledger/fills").json()["total"] == 1


def test_filter_markets_include_opening_only_pairs_and_original_fills(client):
    service = client.app.state.services.performance
    retained(service, execution(1))
    service.save_opening(
        "demo", OpeningInventory(symbol="ETH/USD", quantity="1", as_of="2023-01-01T00:00:00Z")
    )
    response = client.get("/api/v1/account-ledger/performance/markets")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["symbols"] == ["BTC/USDT", "ETH/USD"]
    service.remove_opening("demo", "ETH/USD")
    assert service.markets()["symbols"] == ["BTC/USDT"]
