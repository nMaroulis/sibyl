"""Explicit, finite input contracts for native OCO and unfilled-limit replacement."""

from pydantic import Field

from sibyl.models import OrderRequest, Request


class OCORequest(OrderRequest):
    """Two alternative limits share one base quantity; neither is a position-size multiplier."""

    connection_id: str = Field(min_length=1, max_length=100)
    take_profit_price: float = Field(gt=0, le=1e15)
    trigger_price: float = Field(gt=0, le=1e15)
    limit_price: float = Field(gt=0, le=1e15)


class ReplaceRequest(Request):
    """Replace one unfilled manual GTC limit with a newly reviewed total base quantity/price."""

    quantity: float = Field(gt=0, le=1e9)
    limit_price: float = Field(gt=0, le=1e15)
    idempotency_key: str = Field(min_length=8, max_length=100)
