"""Explicit on-demand lag research over one selected provider's closed candles."""

from typing import Literal

from fastapi import APIRouter
from pydantic import Field, field_validator

from sibyl.api.routes import S
from sibyl.exchanges.data import TIMEFRAMES
from sibyl.market_data.analysis.granger import granger
from sibyl.models import OrderRequest, Request, Timeframe


class LagAnalysis(Request):
    symbols: list[str] = Field(min_length=2, max_length=8)
    timeframe: Timeframe = "1d"
    limit: int = Field(default=360, ge=60, le=720, strict=True)
    lags: Literal[1, 2, 3, 4, 5] = 2
    source: str | None = Field(default=None, max_length=120, pattern=r"^[a-z0-9:-]+$")

    @field_validator("symbols")
    @classmethod
    def exact_symbols(cls, values):
        result = [OrderRequest.valid_symbol(value) for value in values]
        if len(set(result)) != len(result):
            raise ValueError("Choose each spot pair once.")
        return result


router = APIRouter(prefix="/api/v1/markets", tags=["Analyst"])


@router.post("/granger")
def lag_analysis(body: LagAnalysis, s: S):
    """Calculate two directions per reference pair without changing market settings."""
    with s.market.snapshot(body.source):
        for symbol in body.symbols:
            s.market.client().market(symbol)
        histories = {symbol: s.market.candles(symbol, body.limit, body.timeframe) for symbol in body.symbols}
        return {
            **s.market.metadata(),
            "timeframe": body.timeframe,
            **granger(histories, seconds=TIMEFRAMES[body.timeframe], lags=body.lags),
        }
