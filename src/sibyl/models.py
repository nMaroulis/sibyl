"""Shared request and response contracts for the API and domain services."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

ExchangeId = Literal["binance", "coinbase", "kraken"]
StrategyId = Literal["rsi", "ema", "bollinger", "bollinger-surge", "impulse-breakout", "quantum-momentum"]
ModuleId = Literal[
    "oracle",
    "accountant",
    "analyst",
    "broker",
    "chronos",
    "reporter",
    "technician",
    "wiki",
    "explorer",
    "stocks",
]

Timeframe = Literal["1m", "5m", "15m", "30m", "1h", "4h", "12h", "1d", "1w"]


class Request(BaseModel):
    """Reject misspelled fields and non-finite numeric input at the API boundary."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ConnectionCreate(Request):
    """Credentials for a read-only exchange connection; secrets are write-only."""

    exchange: ExchangeId
    label: str = Field(min_length=1, max_length=60)
    api_key: SecretStr = Field(min_length=1)
    secret: SecretStr = Field(min_length=1)
    passphrase: SecretStr = SecretStr("")
    sandbox: bool = False


class Connection(BaseModel):
    """Public connection metadata. Credential material is intentionally absent."""

    id: str
    exchange: ExchangeId
    label: str
    sandbox: bool
    created_at: datetime


class Candle(BaseModel):
    """A closed OHLCV interval with a UTC timestamp."""

    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class OrderRequest(Request):
    """A paper market order. The client supplies a unique idempotency key."""

    symbol: str = "BTC/USDT"
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0, le=1_000_000)
    idempotency_key: str = Field(min_length=8, max_length=100)

    @field_validator("symbol")
    @classmethod
    def valid_symbol(cls, value: str) -> str:
        """Accept canonical base/quote symbols, not arbitrary provider identifiers."""
        value = value.upper().strip()
        parts = value.split("/")
        if len(parts) != 2 or not all(part.isalnum() and 1 <= len(part) <= 12 for part in parts):
            raise ValueError("Use a symbol such as BTC/USDT.")
        return value


class BacktestRequest(Request):
    """Parameters for a long-only, next-open, fee-aware historical simulation."""

    strategy: StrategyId = "ema"
    symbol: str = "BTC/USDT"
    capital: float = Field(default=10_000, ge=100, le=10_000_000)
    candles: int = Field(default=180, ge=60, le=720)
    fee_bps: float = Field(default=10, ge=0, le=200)
    slippage_bps: float = Field(default=5, ge=0, le=200)
    window: int = Field(default=20, ge=5, le=120)
    timeframe: Timeframe = "1d"
    fast_period: int = Field(default=9, ge=2, le=100)
    slow_period: int = Field(default=21, ge=3, le=200)
    rsi_period: int = Field(default=14, ge=2, le=100)
    rsi_lower: float | None = Field(default=None, ge=1, le=49)
    rsi_upper: float | None = Field(default=None, ge=51, le=99)
    band_std: float = Field(default=2, ge=0.5, le=5)
    volume_multiplier: float = Field(default=1.5, ge=0.5, le=10)
    macd_fast_period: int = Field(default=12, ge=2, le=100)
    macd_slow_period: int = Field(default=26, ge=3, le=200)
    macd_signal_period: int = Field(default=9, ge=2, le=100)
    adx_period: int = Field(default=14, ge=2, le=100)
    atr_period: int = Field(default=14, ge=2, le=100)
    cmf_period: int | None = Field(default=None, ge=2, le=120)
    tsi_short_period: int = Field(default=13, ge=2, le=100)
    tsi_long_period: int = Field(default=25, ge=3, le=200)
    stop_loss_pct: float | None = Field(default=None, gt=0, le=90)
    take_profit_pct: float | None = Field(default=None, gt=0, le=1000)
    max_trades: int | None = Field(default=None, ge=1, le=10000)

    @model_validator(mode="after")
    def valid_periods(self):
        """Require ordered EMAs and enough observations to warm up the strategy."""
        if self.fast_period >= self.slow_period:
            raise ValueError("Fast EMA must be shorter than slow EMA.")
        if self.macd_fast_period >= self.macd_slow_period:
            raise ValueError("Fast MACD must be shorter than slow MACD.")
        if self.tsi_short_period >= self.tsi_long_period:
            raise ValueError("Short TSI must be shorter than long TSI.")
        if self.warmup >= self.candles:
            raise ValueError("Choose more observations than the longest indicator period.")
        return self

    @property
    def warmup(self) -> int:
        """Use enough history for every configured smoothing window."""
        return max(
            30,
            self.window,
            self.slow_period,
            self.rsi_period,
            self.macd_slow_period,
            self.macd_signal_period,
            self.adx_period,
            self.atr_period,
            self.cmf_period or self.window,
            self.tsi_long_period,
        )

    _symbol = field_validator("symbol")(OrderRequest.valid_symbol.__func__)


class ExchangeOrderRequest(OrderRequest):
    """Prepare an exchange order against an explicit saved account."""

    connection_id: str = Field(min_length=1, max_length=100)


class ExchangeOrderConfirm(Request):
    """Confirm a short-lived server-side order intent with a typed market phrase."""

    confirmation: str = Field(min_length=1, max_length=100)


class AgentContext(Request):
    """Validated page selections; observations and credentials always come from server tools."""

    symbol: str | None = None
    timeframe: Timeframe | None = None
    limit: int | None = Field(default=None, ge=60, le=720)
    equity_symbol: str | None = Field(default=None, pattern=r"^[A-Z0-9^][A-Z0-9.^-]{0,9}$")
    horizon: int | None = Field(default=None, ge=1, le=30)
    parameters: BacktestRequest | None = None
    job_id: str | None = Field(default=None, min_length=1, max_length=100)
    article_id: str | None = Field(default=None, max_length=100)
    query: str | None = Field(default=None, max_length=200)

    @field_validator("symbol")
    @classmethod
    def valid_symbol(cls, value: str | None) -> str | None:
        """Apply the same canonical market validation used by trading and backtests."""
        return OrderRequest.valid_symbol(value) if value is not None else None


class AgentRequest(Request):
    """Ask a module agent about server-provided context, optionally with a session."""

    module: ModuleId = "oracle"
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, max_length=100)
    context: AgentContext = Field(default_factory=AgentContext)
