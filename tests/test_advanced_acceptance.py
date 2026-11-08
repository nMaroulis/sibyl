"""Prove the real-venue acceptance runner cannot escape its finite virtual-fund scope."""

from urllib.parse import urlencode

import ccxt
import pytest

from sibyl.acceptance.advanced_transport import AdvancedTestnetTransport


class Report:
    def record(self, *args, **kwargs):
        pass


def body(**changes):
    return urlencode(
        {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": ".0002",
            "price": "50000",
            "newClientOrderId": "unique-id",
            "type": "LIMIT",
            "timeInForce": "GTC",
            **changes,
        }
    )


@pytest.mark.parametrize(
    "url,method,payload",
    [
        ("https://api.binance.com/api/v3/order", "POST", body()),
        ("https://testnet.binance.vision/api/v3/order", "POST", body(side="SELL")),
        ("https://testnet.binance.vision/api/v3/order", "POST", body(quantity="1")),
        ("https://testnet.binance.vision/api/v3/order", "POST", body(quantity="NaN")),
        ("https://testnet.binance.vision/api/v3/order", "POST", body(symbol="ETHUSDT")),
        ("https://testnet.binance.vision/api/v3/order", "POST", body(reduceOnly="false")),
        ("https://testnet.binance.vision/api/v3/order", "DELETE", "orderId=unowned"),
        (
            "https://testnet.binance.vision/api/v3/order/cancelReplace",
            "POST",
            body(cancelOrderId="unowned", cancelReplaceMode="ALLOW_FAILURE"),
        ),
    ],
)
def test_acceptance_refuses_out_of_scope_before_network(url, method, payload):
    calls = []
    transport = AdvancedTestnetTransport(lambda *a: calls.append(a), Report())
    with pytest.raises(ValueError):
        transport(None, url, method, {}, payload)
    assert calls == []


def test_native_write_budget_and_duplicate_ids_are_reserved_before_response_loss():
    calls = []

    def lost(*args):
        calls.append(args)
        raise ccxt.RequestTimeout("Controlled unavailable transport")

    transport = AdvancedTestnetTransport(lost, Report())
    for index in range(5):
        with pytest.raises(ccxt.RequestTimeout):
            transport(
                None,
                "https://testnet.binance.vision/api/v3/order",
                "POST",
                {},
                body(newClientOrderId=f"id-{index}"),
            )
    with pytest.raises(ValueError, match="budget"):
        transport(
            None, "https://testnet.binance.vision/api/v3/order", "POST", {}, body(newClientOrderId="id-6")
        )
    assert len(calls) == 5


def test_controlled_oco_loss_keeps_real_native_child_identities_for_safe_cancellation():
    transport = AdvancedTestnetTransport(
        lambda *a: {"orderReports": [{"orderId": 11}, {"orderId": 12}]}, Report(), lose_oco_response=True
    )
    payload = urlencode(
        {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": ".0002",
            "abovePrice": "50000",
            "belowPrice": "49000",
            "listClientOrderId": "list",
            "aboveClientOrderId": "above",
            "belowClientOrderId": "below",
        }
    )
    with pytest.raises(ccxt.RequestTimeout):
        transport(None, "https://testnet.binance.vision/api/v3/orderList/oco", "POST", {}, payload)
    assert transport.native_ids == {"11", "12"}
    with pytest.raises(ValueError, match="repeat"):
        transport(None, "https://testnet.binance.vision/api/v3/orderList/oco", "POST", {}, payload)
