"""Pure preview checks; the exchange still applies its filters at submission."""

import math
from decimal import Decimal


def conditional_prices(client, request):
    """Check native availability, trigger precision/direction and executable-side limit placement."""
    if request.order_type not in client.advanced_support(request.symbol)["types"]:
        raise ValueError("This conditional order is unavailable on the selected spot market.")
    trigger = request.trigger_price
    precise = client.price_to_precision(request.symbol, trigger)
    if Decimal(precise) <= 0 or Decimal(precise) != Decimal(str(trigger)):
        raise ValueError("Trigger price exceeds market precision.")
    bounds = (client.market(request.symbol).get("limits") or {}).get("price") or {}
    if (bounds.get("min") is not None and trigger < bounds["min"]) or (
        bounds.get("max") is not None and trigger > bounds["max"]
    ):
        raise ValueError("Trigger price is outside native market limits.")
    last = client.fetch_ticker(request.symbol).get("last")
    if not last or not math.isfinite(last) or last <= 0:
        raise ValueError("A current last-trade price is required for a conditional review.")
    above = (request.order_type == "stop_loss_limit") == (request.side == "buy")
    if (above and trigger <= last) or (not above and trigger >= last):
        raise ValueError(
            "Trigger must be above the current price for buy stops/sell take-profit, and below it for sell stops/buy take-profit."
        )
    if (request.side == "sell" and request.limit_price > trigger) or (
        request.side == "buy" and request.limit_price < trigger
    ):
        raise ValueError(
            "Use a limit at or below the trigger for sells, or at or above it for buys. Conditional limits can remain unfilled."
        )


def replaceable(order):
    """Reject lists, strategies, imported/partial/uncertain orders and outstanding cancellations."""
    if (
        order.get("origin", "sibyl") not in {"sibyl", "replacement"}
        or order.get("oco_group_id")
        or order["request"].get("order_type") != "limit"
        or order["status"] != "open"
        or order.get("filled") != 0
        or order.get("replace_state")
        or order.get("cancel_state")
        or not order.get("exchange_order_id")
    ):
        raise ValueError(
            "Replace requires a native observed, wholly unfilled manual GTC limit with no pending cancellation."
        )
