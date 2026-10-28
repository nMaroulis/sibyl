"""Causal signal calculation shared by historical and paper execution."""

import numpy as np
import pandas as pd

from sibyl.models import BacktestRequest
from sibyl.services.analytics import indicators


def signals(frame: pd.DataFrame, strategy: str, request: BacktestRequest | None = None) -> pd.Series:
    """Return BUY=1, SELL=-1, HOLD=0 using only data at or before each row."""
    lower = (
        request.rsi_lower
        if request and request.rsi_lower is not None
        else (35 if strategy == "impulse-breakout" else 30)
    )
    upper = (
        request.rsi_upper
        if request and request.rsi_upper is not None
        else (65 if strategy == "impulse-breakout" else 70)
    )
    buy, sell = frame["close"] < frame["lower"], frame["close"] > frame["upper"]
    if strategy == "rsi":
        buy, sell = frame["rsi"] < lower, frame["rsi"] > upper
    elif strategy == "ema":
        buy, sell = frame["ema_fast"] > frame["ema_slow"], frame["ema_fast"] < frame["ema_slow"]
    elif strategy in {"bollinger-surge", "impulse-breakout"}:
        buy &= frame["rsi"] < lower
        sell &= frame["rsi"] > upper
        buy &= (frame["ema_fast"] > frame["ema_slow"]) & frame["volume_surge"]
        sell &= (frame["ema_fast"] < frame["ema_slow"]) & frame["volume_surge"]
        if strategy == "impulse-breakout":
            buy &= (frame["macd"] > frame["macd_signal"]) & (frame["adx"] > 25)
            sell &= (frame["macd"] < frame["macd_signal"]) & (frame["adx"] > 25)
    elif strategy == "quantum-momentum":
        buy = (
            (frame["macd"] > frame["macd_signal"])
            & (frame["tsi"] > 20)
            & (frame["cmf"] > 0)
            & (frame["atr"] > frame["atr"].rolling(10).mean())
        )
        sell = (frame["macd"] < frame["macd_signal"]) & (frame["tsi"] < -20) & (frame["cmf"] < 0)
    elif strategy != "bollinger":
        raise ValueError("Unknown strategy.")
    return pd.Series(np.select([buy, sell], [1, -1], default=0), index=frame.index)


def strategy_indicators(candles: list[dict], request: BacktestRequest) -> pd.DataFrame:
    """Apply the same configurable indicator parameters in backtests and paper jobs."""
    return indicators(
        candles,
        request.window,
        fast_period=request.fast_period,
        slow_period=request.slow_period,
        rsi_period=request.rsi_period,
        band_std=request.band_std,
        volume_multiplier=request.volume_multiplier,
        macd_fast_period=request.macd_fast_period,
        macd_slow_period=request.macd_slow_period,
        macd_signal_period=request.macd_signal_period,
        adx_period=request.adx_period,
        atr_period=request.atr_period,
        cmf_period=request.cmf_period,
        tsi_short_period=request.tsi_short_period,
        tsi_long_period=request.tsi_long_period,
    )


def exit_reason(price: float, entry: float, request: BacktestRequest) -> str | None:
    """Check close-based risk exits, never claiming intrabar stop execution."""
    change = (price / entry - 1) * 100 if entry else 0
    if request.stop_loss_pct is not None and change <= -request.stop_loss_pct:
        return "Stop loss at observed close"
    if request.take_profit_pct is not None and change >= request.take_profit_pct:
        return "Take profit at observed close"
    return None
