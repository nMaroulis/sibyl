"""Acceptance tools must constrain real writes independently of strategy decisions."""

import json
import runpy
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from urllib.parse import urlencode

import ccxt
import pytest

from sibyl.acceptance.strategy import StrategyAcceptance
from sibyl.acceptance.transport import TestnetTransport as Transport
from sibyl.acceptance.workspace import AcceptanceReport, create_workspace
from sibyl.models import ConnectionCreate
from sibyl.storage import Store

TESTNET = "https://testnet.binance.vision/api/v3/order"


@pytest.fixture
def report(tmp_path):
    return AcceptanceReport(tmp_path, lose_entry_response=False)


def order(**changes):
    return urlencode(
        {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": "0.0001",
            "price": "100000",
            "newClientOrderId": "entry",
            "signature": "PRIVATE_SIGNATURE",
            **changes,
        }
    )


@pytest.mark.parametrize(
    "url,method,headers",
    [
        ("https://api.binance.com/api/v3/order", "POST", None),
        ("https://api.binance.com/api/v3/ticker/price?signature=private", "GET", None),
        ("https://api.binance.com/api/v3/ticker/price", "GET", {"X-MBX-APIKEY": "private"}),
        ("https://api.binance.com/api/v3/account", "GET", None),
        ("https://api.binance.com/api/v3/exchangeInfo", "DELETE", None),
        ("https://api1.binance.com/api/v3/exchangeInfo", "GET", None),
        ("https://testnet.binance.vision.evil.example/api/v3/order", "POST", None),
        ("http://testnet.binance.vision/api/v3/order", "POST", None),
        ("https://testnet.binance.vision:444/api/v3/order", "POST", None),
        ("https://user@testnet.binance.vision/api/v3/order", "POST", None),
        ("https://testnet.binance.vision/sapi/v1/transfer", "POST", None),
    ],
)
def test_transport_rejects_out_of_scope_destination_before_http(report, url, method, headers):
    transport = Transport(lambda *_: pytest.fail("Unsafe HTTP call escaped"), report)
    with pytest.raises(ValueError):
        transport(None, url, method, headers, order() if method == "POST" else None)
    assert not transport.attempts


@pytest.mark.parametrize(
    "changes",
    [
        {"symbol": "ETHUSDT"},
        {"type": "MARKET"},
        {"timeInForce": "IOC"},
        {"side": "SELL"},
        {"quantity": "NaN"},
        {"quantity": "Infinity"},
        {"quantity": "-1"},
        {"quantity": "0"},
        {"price": "NaN"},
        {"price": "Infinity"},
        {"price": "0"},
        {"price": "150001"},
        {"newClientOrderId": ""},
    ],
)
def test_transport_enforces_pair_type_amount_and_budget_before_http(report, changes):
    transport = Transport(lambda *_: pytest.fail("Unsafe order escaped"), report)
    with pytest.raises(ValueError):
        transport(None, TESTNET, "POST", body=order(**changes))
    assert not transport.attempts


def test_lost_real_response_recovers_by_read_without_a_second_buy_and_caps_exit(report):
    calls = []

    def fetch(adapter, url, method, headers, body):
        calls.append(method)
        return {"orderId": 123 if len(calls) < 3 else 456}

    transport = Transport(fetch, report, lose_entry_response=True)
    with pytest.raises(ccxt.RequestTimeout):
        transport(None, TESTNET, "POST", {"X-MBX-APIKEY": "PRIVATE_KEY"}, order())
    with pytest.raises(ValueError):
        transport(None, TESTNET, "POST", body=order(newClientOrderId="retry"))
    assert transport(None, TESTNET + "?origClientOrderId=entry", "GET")["orderId"] == 123
    # A sell is unavailable until the caller has reconciled strategy ownership.
    with pytest.raises(ValueError):
        transport(None, TESTNET, "POST", body=order(side="SELL", newClientOrderId="exit"))
    transport.allow_sell("0.00009")
    with pytest.raises(ValueError):
        transport(None, TESTNET, "POST", body=order(side="SELL", newClientOrderId="exit"))
    result = transport(
        None, TESTNET, "POST", body=order(side="SELL", quantity="0.00008", newClientOrderId="exit")
    )
    assert result["orderId"] == 456
    with pytest.raises(ValueError):
        transport(
            None, TESTNET, "POST", body=order(side="SELL", quantity="0.00001", newClientOrderId="exit2")
        )
    assert calls == ["POST", "GET", "POST"]
    receipt = json.loads(report.path.read_text())
    assert "PRIVATE" not in json.dumps(receipt)
    assert len(transport.attempts) == 2
    assert any(row["check"] == "entry_response_deliberately_discarded" for row in receipt["checks"])


def test_http_failure_reserves_attempt_even_across_competing_workers(report):
    calls = []

    def failing_fetch(*_):
        calls.append(1)
        raise ccxt.RequestTimeout("Lost response")

    transport = Transport(failing_fetch, report)

    def attempt(_):
        try:
            transport(None, TESTNET, "POST", body=order())
        except (ccxt.RequestTimeout, ValueError):
            return
        pytest.fail("An uncertain submission reported success")

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(attempt, range(2)))
    assert len(calls) == len(transport.attempts) == 1


@pytest.mark.parametrize("suffix", ["&quantity=1", "&quoteOrderQty=1000", "&icebergQty=1"])
def test_additional_native_parameters_cannot_bypass_the_review_cap(report, suffix):
    transport = Transport(lambda *_: pytest.fail("An unreviewed order escaped"), report)
    with pytest.raises(ValueError):
        transport(None, TESTNET, "POST", body=order() + suffix)


def test_cancellation_must_belong_to_an_observed_acceptance_order(report):
    calls = []
    transport = Transport(lambda *args: calls.append(args) or {"orderId": 123}, report)
    transport(None, TESTNET, "POST", body=order())
    with pytest.raises(ValueError):
        transport(None, TESTNET + "?orderId=999", "DELETE")
    transport(None, TESTNET + "?orderId=123", "DELETE")
    assert len(calls) == 2


def test_native_identity_recovered_after_a_real_http_failure_allows_owned_cancellation(report):
    def fetch(adapter, url, method, headers, body):
        if method == "POST":
            raise ccxt.RequestTimeout("The server response was lost")
        return {"orderId": 123, "clientOrderId": "entry"}

    transport = Transport(fetch, report)
    with pytest.raises(ccxt.RequestTimeout):
        transport(None, TESTNET, "POST", body=order())
    transport(None, TESTNET + "?origClientOrderId=entry")
    transport(None, TESTNET + "?orderId=123", "DELETE")
    assert len(transport.attempts) == 1


def test_shared_risk_reference_reads_are_public_and_read_only(report):
    calls = []
    transport = Transport(lambda *args: calls.append(args) or {}, report)
    transport(None, "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT")
    assert len(calls) == 1 and not transport.attempts


@pytest.mark.parametrize("exchange,sandbox", [("binance", False), ("binance", True), ("coinbase", False)])
def test_invalid_accounts_are_rejected_before_credential_access_or_workspace_creation(
    tmp_path, exchange, sandbox
):
    source = SimpleNamespace(
        connections=lambda: [SimpleNamespace(id="account", exchange=exchange, sandbox=sandbox)],
        credentials=lambda *_: pytest.fail("Non-Testnet credentials were decrypted"),
    )
    with pytest.raises(ValueError, match="dedicated Binance Testnet"):
        create_workspace(source, "account", tmp_path / "new")
    assert not (tmp_path / "new").exists()


def test_isolated_workspace_copies_only_test_credentials_and_keeps_source_unchanged(tmp_path):
    source = Store(tmp_path / "source")
    production = source.add_connection(
        ConnectionCreate(exchange="binance", label="Production", api_key="PROD", secret="PROD_SECRET")
    )
    test = source.add_connection(
        ConnectionCreate(exchange="binance-testnet", label="Testnet", api_key="TEST", secret="TEST_SECRET")
    )
    before = source.connections()
    settings, account = create_workspace(source, test.id, tmp_path / "isolated")
    retained = Store(settings.data_dir)
    assert settings.allow_live_trading and settings.allow_strategy_execution
    assert account.exchange == "binance-testnet" and account.sandbox and account.active
    assert [row.exchange for row in retained.connections()] == ["binance-testnet"]
    assert retained.credentials(account.id)["apiKey"] == "TEST"
    assert source.connections() == before
    assert source.credentials(production.id)["apiKey"] == "PROD"
    with pytest.raises(FileExistsError):
        create_workspace(source, test.id, settings.data_dir)


@pytest.mark.parametrize("extra", [[], ["--execute-testnet", "--signal-wait", "601"]])
def test_cli_requires_explicit_opt_in_and_bounded_wait_before_opening_vault(monkeypatch, tmp_path, extra):
    main = runpy.run_path("scripts/check_binance_strategy_testnet.py")["main"]
    monkeypatch.setitem(
        main.__globals__, "Store", lambda *_: pytest.fail("Opened vault before argument checks")
    )
    monkeypatch.setattr(
        "sys.argv", ["check", "--account-id", "test", "--workspace", str(tmp_path / "new"), *extra]
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


@pytest.mark.parametrize(
    "state,attempts,accepted", [("found", 1, True), ("not_needed", 1, False), ("found", 2, False)]
)
def test_response_loss_acceptance_requires_recorded_recovery_and_only_one_write(
    report, monkeypatch, state, attempts, accepted
):
    client = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(services=None)))
    transport = SimpleNamespace(lose_entry_response=True, attempts=[{}] * attempts)
    check = StrategyAcceptance(client, None, report, transport)
    check.job_id = "job"
    monkeypatch.setattr(
        check, "orders", lambda: [{"id": "entry", "status": "closed", "request": {"side": "buy"}}]
    )
    monkeypatch.setattr(
        check, "request", lambda method, path: {"items": [{"reason": "Native submission is uncertain"}]}
    )
    monkeypatch.setattr(
        check,
        "reconcile",
        lambda identity: {
            "order": {"exchange_order_id": "native", "recovery": {"state": state, "pages": 1}},
        },
    )
    if accepted:
        check.wait_for_entry(1)
        assert report.values["checks"][-1]["check"] == "lost_response_recovered_without_resubmission"
    else:
        with pytest.raises(RuntimeError, match="did not recover"):
            check.wait_for_entry(1)
