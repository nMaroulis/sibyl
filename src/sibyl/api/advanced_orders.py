"""Reviewed native list/replacement endpoints; agents receive read-only evidence only."""

from fastapi import APIRouter

from sibyl.api.routes import S, Symbol
from sibyl.models import ExchangeOrderConfirm
from sibyl.services.trading.advanced.contracts import OCORequest, ReplaceRequest
from sibyl.services.trading.advanced.replacement import preview_replacement

router = APIRouter(prefix="/api/v1", tags=["Broker"])


@router.get("/connections/{connection_id}/order-capabilities")
def capabilities(connection_id: str, s: S, symbol: Symbol = "BTC/USDT"):
    """Read implemented and native per-instrument advanced-order permissions."""
    connection = s.trading._connection(connection_id, allow_demo=True)
    with s.market.adapter(connection) as client:
        return {
            "symbol": symbol,
            "exchange": connection.exchange,
            "sandbox": connection.sandbox,
            **client.advanced_support(symbol),
        }


@router.post("/exchange-order-lists/preview")
def preview(body: OCORequest, s: S):
    """Review both alternatives without submitting or reserving funds."""
    return s.trading.advanced.preview(body)


@router.get("/exchange-order-lists/{identity}")
def detail(identity: str, s: S):
    """Read actual retained per-leg evidence; no provider refresh occurs."""
    return s.trading.advanced.detail(identity)


@router.post("/exchange-order-lists/{identity}/confirm")
def confirm(identity: str, body: ExchangeOrderConfirm, s: S):
    """Commit one native linked-list attempt after explicit typed approval."""
    return s.trading.advanced.execute(identity, body.confirmation)


@router.post("/exchange-orders/{identity}/replace/preview")
def replace(identity: str, body: ReplaceRequest, s: S):
    """Read the original and review one native unfilled-only cancel/replace attempt."""
    return preview_replacement(s.trading, identity, body)
