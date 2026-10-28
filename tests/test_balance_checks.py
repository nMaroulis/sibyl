"""Observed quantity checks never invent opening basis, missing fees or funding semantics."""

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from sibyl.accounting.balance_checks import service
from sibyl.accounting.balance_checks.movements import compare
from sibyl.models import ConnectionCreate
from sibyl.services.ledger import AccountLedger, ledger_fill, now_iso


def observation(**changes):
    return {
        "started_ms": 100_000,
        "ended_ms": 101_000,
        "balances": {"BTC": 1, "USDT": 1000, "BNB": 1},
        "fills": [],
        "funding": [],
        "imports": [{"kind": "fills", "status": "caught_up", "caught_up": True}],
        **changes,
    }


def trade(**changes):
    return {
        "id": "trade",
        "timestamp_ms": 150_000,
        "symbol": "BTC/USDT",
        "side": "buy",
        "quantity": 0.01,
        "notional": 200,
        "fees_known": True,
        "fees": [{"currency": "USDT", "cost": 0.1}],
        **changes,
    }


def funding(**changes):
    return {
        "id": "funding",
        "timestamp_ms": 150_000,
        "posted_ms": changes.get("timestamp_ms", 150_000),
        "asset": "USDT",
        "direction": "in",
        "quantity": 50,
        "status": "completed",
        "fee_known": True,
        "fee": {"currency": "USDT", "cost": 0},
        "wallet_scope": "configured",
        **changes,
    }


def current(**changes):
    return observation(started_ms=200_000, ended_ms=201_000, **changes)


def rows(result):
    return {row["asset"]: row for row in result["rows"]}


def test_observed_match_uses_native_quantities_and_does_not_claim_complete_reconciliation():
    result = compare(observation(), current(fills=[trade()], balances={"BTC": 1.01, "USDT": 799.9, "BNB": 1}))
    assert result["status"] == "observed_match"
    assert not result["coverage_complete"] and not result["settlement_final"]
    assert result["activity"] == {"fills": 1, "funding": 0}
    assert rows(result)["USDT"]["difference"] == 0


def test_cross_market_trades_and_third_asset_rebates_are_combined_by_asset():
    first = trade(fees=[{"currency": "BNB", "cost": 0.001}])
    second = trade(
        id="trade2",
        symbol="ETH/BTC",
        side="buy",
        quantity=0.1,
        notional=0.005,
        fees=[{"currency": "ETH", "cost": -0.001}],
    )
    result = compare(
        observation(),
        current(fills=[first, second], balances={"BTC": 1.005, "USDT": 800, "BNB": 0.999, "ETH": 0.101}),
    )
    assert result["status"] == "observed_match"
    assert rows(result)["BNB"]["trade_change"] == -0.001
    assert rows(result)["ETH"]["trade_change"] == 0.101


def test_sell_reduces_base_and_credits_quote_after_fees():
    result = compare(
        observation(), current(fills=[trade(side="sell")], balances={"BTC": 0.99, "USDT": 1199.9, "BNB": 1})
    )
    assert result["status"] == "observed_match"


@pytest.mark.parametrize("fee", [[], [{"currency": None, "cost": 0.1}], [{"currency": "BTC", "cost": None}]])
def test_unknown_trade_fees_never_become_zero(fee):
    result = compare(observation(), current(fills=[trade(fees_known=False, fees=fee)]))
    assert result["status"] == "incomplete"
    assert all(row["expected"] is None and row["difference"] is None for row in result["rows"])


@pytest.mark.parametrize("direction,quantity", [("in", 1050), ("out", 950)])
def test_completed_explicitly_zero_fee_funding_applies_without_pairing_accounts(direction, quantity):
    result = compare(
        observation(),
        current(funding=[funding(direction=direction)], balances={"BTC": 1, "USDT": quantity, "BNB": 1}),
    )
    assert result["status"] == "observed_match"


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "pending"},
        {"status": "restricted"},
        {"status": "unknown"},
        {"fee_known": False},
        {"fee": {"currency": "USDT", "cost": 1}},
    ],
)
def test_uncertain_funding_never_assumes_amount_or_fee_inclusion(changes):
    result = compare(observation(), current(funding=[funding(**changes)]))
    assert rows(result)["USDT"]["expected"] is None
    assert result["status"] == "incomplete"
    assert result["activity"]["funding"] == 0


@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_failed_funding_does_not_move_balances(status):
    assert compare(observation(), current(funding=[funding(status=status)]))["status"] == "observed_match"


@pytest.mark.parametrize("stamp", [90_000, 100_500, 102_000, 199_500, 220_000])
def test_backfills_and_balance_boundary_activity_remain_unresolved(stamp):
    result = compare(observation(), current(fills=[trade(timestamp_ms=stamp)]))
    assert result["status"] == "incomplete"
    assert rows(result)["BTC"]["expected"] is None


def test_corrected_or_removed_precheckpoint_history_requires_review():
    old = trade(timestamp_ms=90_000)
    baseline = observation(fills=[old])
    corrected = {**old, "fees": [{"currency": "USDT", "cost": 2}]}
    for changes in ([corrected], []):
        result = compare(baseline, current(fills=changes))
        assert result["status"] == "incomplete"
        assert rows(result)["BTC"]["expected"] is None


def test_missing_assets_are_zero_only_when_the_complete_observed_map_omits_them():
    result = compare(observation(), current(balances={"USDT": 1000}))
    assert result["status"] == "differences"
    assert rows(result)["BTC"]["difference"] == -1


def test_unconfigured_or_unfinished_imports_are_reported_even_when_numbers_match():
    for imports in ([], [{"kind": "fills", "status": "running", "caught_up": False}]):
        result = compare(observation(), current(imports=imports))
        assert result["status"] == "incomplete" and result["notes"]


def test_unknown_funding_fee_asset_blocks_unrelated_expected_balances_too():
    result = compare(
        observation(), current(funding=[funding(fee_known=False, fee={"currency": None, "cost": None})])
    )
    assert all(row["expected"] is None for row in result["rows"])


def test_fee_correction_retains_both_the_old_and_new_fee_asset_gaps():
    old = trade(timestamp_ms=90_000, fees=[{"currency": "OLD", "cost": 1}])
    new = {**old, "fees": [{"currency": "NEW", "cost": 1}]}
    result = rows(compare(observation(fills=[old]), current(fills=[new])))
    assert result["OLD"]["expected"] is None and result["NEW"]["expected"] is None


def test_account_label_and_order_attribution_updates_do_not_invent_a_quantity_correction():
    old = trade(timestamp_ms=90_000, account="Before", order_id=None)
    new = {**old, "account": "Renamed account", "order_id": "now-known-native-id"}
    assert compare(observation(fills=[old]), current(fills=[new]))["status"] == "observed_match"


class Balances:
    """Read-only venue fixture; exposing a mutation would fail the test."""

    def __init__(self):
        self.total = {"BTC": 1.0, "USDT": 1000.0}
        self.calls = 0
        self.callback = lambda: None

    def fetch_balance_snapshot(self):
        self.calls += 1
        self.callback()
        return {"total": deepcopy(self.total), "free": {}, "used": {}, "info": "PRIVATE_NATIVE"}

    def close(self):
        pass


@pytest.fixture
def checks(client, monkeypatch):
    services = client.app.state.services
    account = services.store.add_connection(
        ConnectionCreate(
            exchange="binance-testnet", label="Test account", api_key="PRIVATE_KEY", secret="PRIVATE_SECRET"
        )
    )
    native = Balances()
    services.market._clients[account.id] = native
    clock = SimpleNamespace(value=datetime.now(UTC).timestamp())
    monkeypatch.setattr(service, "time", SimpleNamespace(time=lambda: clock.value))
    with services.store.db() as db:
        payload = {"status": "caught_up", "account_id": account.id, "symbol": "BTC/USDT"}
        db.execute(
            "INSERT INTO account_sync VALUES(?,?,?,?,?,?)",
            (account.id, "BTC/USDT", "caught_up", clock.value + 86400, 0, json.dumps(payload)),
        )
    return services.balance_checks, services, account, native, clock


def test_checkpoint_then_comparison_uses_fresh_balances_and_retained_fills(checks):
    checks, services, account, native, clock = checks
    saved = checks.capture(account.id)
    checkpoint = saved["checkpoint"]["id"]
    clock.value += 10
    metadata = {
        "account_id": account.id,
        "account": account.label,
        "exchange": account.exchange,
        "environment": "test",
        "symbol": "BTC/USDT",
    }
    raw = {
        "id": "new-trade",
        "order": "order",
        "timestamp": clock.value * 1000,
        "symbol": "BTC/USDT",
        "side": "buy",
        "amount": 0.01,
        "price": 20000,
        "cost": 200,
        "fees": [{"currency": "USDT", "cost": 0.1}],
    }
    with services.store.db() as db:
        AccountLedger.upsert_fills(db, [ledger_fill(raw, metadata)], now_iso())
    clock.value += 10
    native.total = {"BTC": 1.01, "USDT": 799.9}
    result = checks.check(account.id, checkpoint)
    assert result["latest"]["status"] == "observed_match"
    assert native.calls == 2
    assert "PRIVATE" not in json.dumps(result) and '"scope"' not in json.dumps(result)
    assert "fills" not in result["checkpoint"]
    # GET retained evidence does not perform another balance read.
    assert checks.journal.state(account.id)["latest"] == result["latest"]
    assert native.calls == 2


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, None, -1])
def test_invalid_balances_preserve_the_last_good_checkpoint(checks, bad):
    checks, services, account, native, clock = checks
    saved = checks.capture(account.id)
    native.total["BTC"] = bad
    clock.value += 10
    with pytest.raises(ValueError, match="fresh balance observation"):
        checks.check(account.id, saved["checkpoint"]["id"])
    assert checks.journal.state(account.id)["checkpoint"] == saved["checkpoint"]
    assert not checks.journal.state(account.id)["history"]


def test_scope_rotation_invalidates_comparison_before_a_provider_read(checks):
    checks, services, account, native, clock = checks
    saved = checks.capture(account.id)
    with services.store.db() as db:
        db.execute(
            "UPDATE connections SET credentials=? WHERE id=?",
            (services.store.cipher.encrypt(b"{}"), account.id),
        )
    assert checks.journal.state(account.id)["configuration_changed"]
    with pytest.raises(ValueError, match="wallet scope changed"):
        checks.check(account.id, saved["checkpoint"]["id"])
    assert native.calls == 1


def test_a_stale_checkpoint_control_cannot_overwrite_or_read_a_provider(checks):
    checks, services, account, native, clock = checks
    saved = checks.capture(account.id)
    for action in (lambda: checks.capture(account.id), lambda: checks.check(account.id, "wrong-id")):
        with pytest.raises(ValueError, match="checkpoint changed"):
            action()
    assert native.calls == 1
    assert checks.journal.state(account.id)["checkpoint"] == saved["checkpoint"]


def test_deactivation_during_a_read_prevents_commit_and_keeps_saved_evidence(checks):
    checks, services, account, native, clock = checks
    saved = checks.capture(account.id)
    clock.value += 10
    native.callback = lambda: services.store.activate_account(account.id, False)
    with pytest.raises(ValueError, match="Activate this account"):
        checks.check(account.id, saved["checkpoint"]["id"])
    assert not checks.journal.state(account.id)["history"]


@pytest.mark.parametrize("future", [False, True])
def test_provider_update_time_is_not_confused_with_the_observation_window(checks, monkeypatch, future):
    checks, services, account, native, clock = checks
    original = native.fetch_balance_snapshot
    monkeypatch.setattr(
        native,
        "fetch_balance_snapshot",
        lambda: {**original(), "timestamp": clock.value * 1000 + 60_000 if future else 1},
    )
    if future:
        with pytest.raises(ValueError, match="fresh balance observation"):
            checks.capture(account.id)
    else:
        assert checks.capture(account.id)["checkpoint"]["id"]


def test_native_unicode_asset_identifiers_are_preserved_and_unchanged_zero_assets_are_omitted(checks):
    checks, services, account, native, clock = checks
    native.total.update({"币安人生": 5, "EMPTY": 0})
    saved = checks.capture(account.id)
    clock.value += 10
    result = checks.check(account.id, saved["checkpoint"]["id"])["latest"]
    assert rows(result)["币安人生"]["observed"] == 5
    assert "EMPTY" not in rows(result)


def test_reports_are_bounded_and_replacing_a_checkpoint_retains_prior_reports(checks):
    checks, services, account, native, clock = checks
    saved = checks.capture(account.id)
    for _ in range(22):
        clock.value += 10
        state = checks.check(account.id, saved["checkpoint"]["id"])
    assert len(state["history"]) == 20
    replaced = checks.capture(account.id, saved["checkpoint"]["id"])
    assert replaced["checkpoint"]["id"] != saved["checkpoint"]["id"]
    assert replaced["latest"] is None and len(replaced["history"]) == 20


def test_http_controls_are_local_and_validate_payloads(client):
    accounts = client.get("/api/v1/account/balance-checks").json()["accounts"]
    assert accounts[0]["environment"] == "demo"
    base = "/api/v1/account/balance-checks/demo"
    assert client.get(base).headers["cache-control"] == "no-store"
    captured = client.post(base + "/checkpoint", json={}).json()
    assert captured["checkpoint"]["id"]
    assert client.post(base + "/compare", json={"checkpoint_id": "bad"}).status_code == 400
    assert (
        client.post(
            base + "/compare", json={"checkpoint_id": captured["checkpoint"]["id"], "repair": True}
        ).status_code
        == 422
    )


def test_competing_initial_checkpoint_requests_cannot_silently_rebase_an_account(checks):
    checks, services, account, native, clock = checks

    def capture():
        try:
            return checks.capture(account.id)
        except ValueError:
            return None

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: capture(), range(2)))
    assert sum(result is not None for result in results) == 1 and native.calls == 1


def test_retained_report_lookup_enforces_account_and_does_not_fetch_balances(checks):
    checks, services, account, native, clock = checks
    saved = checks.capture(account.id)
    clock.value += 10
    state = checks.check(account.id, saved["checkpoint"]["id"])
    identity = state["latest"]["id"]
    assert "rows" not in state["history"][0]
    assert checks.journal.report(account.id, identity) == state["latest"]
    with pytest.raises(LookupError):
        checks.journal.report("another-account", identity)
    assert native.calls == 2
