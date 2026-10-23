"""Explicit, bounded authorization for one account and one spot strategy."""

from pydantic import Field, model_validator

from sibyl.models import BacktestRequest, Request


class ExecutionGuard(ValueError):
    """A public, credential-free explanation for blocking automated execution."""


class ExecutionRisk(Request):
    """Limits on new orders; these do not guarantee a maximum market loss."""

    max_order_quote: float = Field(default=500, gt=0, le=10_000_000)
    max_loss_pct: float = Field(default=10, gt=0, le=90)
    max_orders_per_day: int = Field(default=6, ge=1, le=100)
    max_spread_bps: float = Field(default=50, gt=0, le=500)
    price_limit_bps: float = Field(default=25, gt=0, le=200)
    fee_reserve_bps: float = Field(default=100, ge=10, le=500)
    order_lifetime_seconds: int | None = Field(default=None, ge=60, le=86_400, strict=True)


class ExecutionParameters(BacktestRequest):
    """Native quote units can be fractional, including BTC/ETH-quoted markets."""

    capital: float = Field(gt=0, le=10_000_000)


class ExchangeStrategyRequest(Request):
    """A fixed strategy, exact market, saved account and allocated quote budget."""

    connection_id: str = Field(min_length=1, max_length=100)
    parameters: ExecutionParameters
    risk: ExecutionRisk = Field(default_factory=ExecutionRisk)

    @model_validator(mode="after")
    def bounded_order(self):
        if self.risk.max_order_quote > self.parameters.capital:
            raise ValueError("Maximum order value cannot exceed the strategy quote budget.")
        return self


class StrategyApproval(Request):
    """Confirm the immutable, expiring server-side strategy review."""

    confirmation: str = Field(min_length=1, max_length=120)
