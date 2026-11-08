"""Manual native replacement review; strategy-owned, OCO and partial orders are excluded."""

from sibyl.models import ExchangeOrderRequest
from sibyl.services.trading.advanced.validation import replaceable


def preview_replacement(trading, identity, request):
    """Observe the old order and save a new, separately confirmed total-size GTC intent."""
    with trading.lifecycle.lock(identity):
        original = trading.lifecycle.refresh(identity)
        replaceable(original)
        connection = trading._connection(original["request"]["connection_id"])
        with trading.market.adapter(connection) as client:
            if not client.advanced_support(original["request"]["symbol"])["replace"]:
                raise ValueError("Native cancel/replace is unavailable for this market/provider.")
        body = ExchangeOrderRequest(
            connection_id=connection.id,
            symbol=original["request"]["symbol"],
            side=original["request"]["side"],
            quantity=request.quantity,
            limit_price=request.limit_price,
            order_type="limit",
            idempotency_key=request.idempotency_key,
        )
        return trading.preview(body, replacement_of=identity)
