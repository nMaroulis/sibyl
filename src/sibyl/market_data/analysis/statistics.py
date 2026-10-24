"""Finite, source-local market statistics over the latest contiguous OHLCV sample."""

from datetime import UTC, datetime
from math import isfinite

import numpy as np
import pandas as pd

from .assessment import technical_assessment


def finite(value) -> float | None:
    """Represent undefined or non-finite statistics as JSON null, never zero."""
    return float(value) if value is not None and pd.notna(value) and isfinite(value) else None


def prepare_history(candles: list[dict], periods_per_year: float) -> tuple[pd.DataFrame, pd.Series]:
    """Validate observations and identify interval breaks without filling missing data."""
    if not candles or not isfinite(periods_per_year) or periods_per_year <= 0:
        raise ValueError("Analysis needs candles and a positive finite annualization frequency.")
    frame = pd.DataFrame(candles)
    fields = ["open", "high", "low", "close", "volume"]
    if not {"timestamp", *fields}.issubset(frame.columns):
        raise ValueError("Analysis requires timestamped OHLCV observations.")
    if any(isinstance(value, (bool, np.bool_)) for key in fields for value in frame[key]):
        raise ValueError("OHLCV observations must be numeric, not boolean.")
    try:
        frame[fields] = frame[fields].astype(float)
        stamps = pd.to_datetime(frame["timestamp"], utc=True, format="mixed", errors="raise")
    except (ValueError, TypeError) as error:
        raise ValueError("Analysis requires valid OHLCV values and timestamps.") from error
    if (
        not np.isfinite(frame[fields].to_numpy()).all()
        or (frame[["open", "high", "low", "close"]] <= 0).any().any()
        or (frame["volume"] < 0).any()
        or (frame["low"] > frame[["open", "close"]].min(axis=1)).any()
        or (frame["high"] < frame[["open", "close"]].max(axis=1)).any()
        or stamps.isna().any()
        or not stamps.is_monotonic_increasing
        or stamps.duplicated().any()
    ):
        raise ValueError("Analysis requires ordered unique timestamps and valid positive OHLC prices.")
    seconds = 365 * 86400 / periods_per_year
    elapsed = stamps.diff().dt.total_seconds()
    breaks = elapsed.notna() & ~np.isclose(elapsed, seconds, rtol=0, atol=0.001)
    return frame, breaks


def market_statistics(
    frame: pd.DataFrame,
    periods_per_year: float,
    breaks: pd.Series,
    *,
    now: datetime | None = None,
) -> dict:
    """Summarize the latest consecutive segment, with explicit warm-up and provenance.

    `frame` contains the existing causal indicator columns, restarted at breaks.
    Prices retain the provider's quote unit and volume retains its base unit.
    Sharpe/Sortino assume zero risk-free/target returns. Tail risk is empirical,
    one-candle, unlevered close-return loss; it is not a forward confidence bound.
    """
    segment_start = int(np.flatnonzero(breaks.to_numpy())[-1]) if breaks.any() else 0
    recent = frame.iloc[segment_start:]
    close, high, low, volume = (recent[key] for key in ("close", "high", "low", "volume"))
    last = recent.iloc[-1]
    n, price = len(recent), float(last["close"])
    returns = close.pct_change().dropna()
    seconds = 365 * 86400 / periods_per_year
    stamps = pd.to_datetime(frame["timestamp"], utc=True, format="mixed")
    observed_at = pd.Timestamp(now or datetime.now(UTC))
    age = (observed_at - (stamps.iloc[-1] + pd.Timedelta(seconds=seconds))).total_seconds()
    if age < -1:
        raise ValueError("Analysis accepts only closed candles, not future intervals.")
    missing = sum(
        max(0, int(round(value / seconds)) - 1) for value in stamps.diff().dt.total_seconds().dropna()
    )
    warnings = []
    if segment_start:
        warnings.append(
            f"Interval breaks detected; statistics use only the latest {n} consecutive candles of {len(frame)} loaded. No gaps are filled."
        )
    stale = age > max(2 * seconds, 120)
    if stale:
        warnings.append("The latest closed candle is old; statistics describe a historical sample.")
    if n < 200:
        warnings.append("SMA 200 needs 200 consecutive candles; unavailable readings remain blank.")
    if n < 50:
        warnings.append("Short sample: several indicators and the overall score need more history.")
    if not volume.gt(0).any():
        warnings.append(
            "The provider supplied no positive volume in this sample; volume-based readings are unavailable."
        )
    sample = {
        "loaded": len(frame),
        "observations": n,
        "return_observations": len(returns),
        "start": recent.iloc[0]["timestamp"],
        "end": last["timestamp"],
        "interval_seconds": seconds,
        "gap_count": int(breaks.sum()),
        "missing_intervals": missing,
        "stale": stale,
        "age_seconds": max(0, age),
        "warnings": warnings,
    }

    def indicator(key, minimum):
        return finite(last[key]) if n >= minimum else None

    def average(period):
        return finite(close.tail(period).mean()) if n >= period else None

    def change(period):
        return finite((price / close.iloc[-period - 1] - 1) * 100) if n > period else None

    def distance(value):
        return finite((price / value - 1) * 100) if value is not None and value > 0 else None

    std = finite(returns.std()) if len(returns) >= 2 else None
    mean = finite(returns.mean()) if len(returns) else None
    downside = float(np.sqrt(np.mean(np.minimum(returns, 0) ** 2))) if len(returns) >= 2 else None
    drawdown = (close / close.cummax() - 1) * 100
    q05 = float(returns.quantile(0.05)) if len(returns) >= 20 else None
    tail_loss = max(0, -float(returns[returns <= q05].mean()) * 100) if q05 is not None else None
    range14 = high.rolling(14).max() - low.rolling(14).min()
    stochastic = 100 * (close - low.rolling(14).min()) / range14.replace(0, np.nan)
    mean20 = finite(volume.tail(20).mean()) if n >= 20 else None
    previous_volume = finite(volume.iloc[-21:-1].mean()) if n >= 21 else None
    volume20 = float(volume.tail(20).sum()) if n >= 20 else 0
    typical = (high + low + close) / 3
    vwap = finite((typical.tail(20) * volume.tail(20)).sum() / volume20) if volume20 > 0 else None
    signed_volume = np.sign(close.diff()).fillna(0) * volume
    sample_high, sample_low = float(high.max()), float(low.min())
    previous = recent.iloc[-2] if n >= 2 else None
    pivot = (previous["high"] + previous["low"] + previous["close"]) / 3 if previous is not None else None
    atr, upper, lower = indicator("atr", 14), indicator("upper", 20), indicator("lower", 20)
    band_width = upper - lower if upper is not None and lower is not None else 0
    metrics = {
        "price": price,
        "sample": sample,
        "returns": {
            "sample_pct": (price / close.iloc[0] - 1) * 100,
            "bar1_pct": change(1),
            "bar5_pct": change(5),
            "bar20_pct": change(20),
            "bar60_pct": change(60),
            "mean_pct": mean * 100 if mean is not None else None,
            "median_pct": finite(returns.median() * 100),
            "best_pct": finite(returns.max() * 100),
            "worst_pct": finite(returns.min() * 100),
            "positive_pct": float((returns > 0).mean() * 100) if len(returns) else None,
        },
        "trend": {
            "sma20": average(20),
            "sma50": average(50),
            "sma200": average(200),
            "ema9": indicator("ema_fast", 9),
            "ema21": indicator("ema_slow", 21),
            "distance_sma50_pct": distance(average(50)),
            "adx14": indicator("adx", 28),
        },
        "momentum": {
            "rsi14": indicator("rsi", 15),
            "macd": indicator("macd", 35),
            "macd_signal": indicator("macd_signal", 35),
            "macd_histogram": finite(last["macd"] - last["macd_signal"]) if n >= 35 else None,
            "roc10_pct": change(10),
            "stochastic_k14": finite(stochastic.iloc[-1]),
            "stochastic_d3": finite(stochastic.rolling(3).mean().iloc[-1]),
        },
        "volatility": {
            "annualized_pct": std * np.sqrt(periods_per_year) * 100 if std is not None else None,
            "period_pct": std * 100 if std is not None else None,
            "downside_annualized_pct": downside * np.sqrt(periods_per_year) * 100
            if downside is not None
            else None,
            "atr14": atr,
            "atr_pct": atr / price * 100 if atr is not None else None,
            "bollinger_width_pct": band_width / float(last["sma"]) * 100 if upper is not None else None,
            "bollinger_percent_b": (price - lower) / band_width if band_width > 0 else None,
        },
        "risk": {
            "max_drawdown_pct": max(0.0, -float(drawdown.min())),
            "current_drawdown_pct": max(0.0, -float(drawdown.iloc[-1])),
            "sharpe": mean / std * np.sqrt(periods_per_year) if std is not None and std > 1e-12 else None,
            "sortino": mean / downside * np.sqrt(periods_per_year)
            if downside is not None and downside > 1e-12
            else None,
            "var95_pct": max(0, -q05 * 100) if q05 is not None else None,
            "expected_shortfall95_pct": tail_loss,
        },
        "volume": {
            "last": float(last["volume"]),
            "mean20": mean20,
            "relative20": float(last["volume"]) / previous_volume
            if previous_volume is not None and previous_volume > 0
            else None,
            "obv_change20": finite(signed_volume.tail(20).sum()) if n >= 21 and volume20 > 0 else None,
            "cmf20": indicator("cmf", 20),
            "vwap20": vwap,
            "distance_vwap20_pct": distance(vwap),
        },
        "levels": {
            "sample_high": sample_high,
            "sample_low": sample_low,
            "range_position_pct": (price - sample_low) / (sample_high - sample_low) * 100
            if sample_high > sample_low
            else None,
            "prior_high20": finite(high.iloc[-21:-1].max()) if n >= 21 else None,
            "prior_low20": finite(low.iloc[-21:-1].min()) if n >= 21 else None,
            "distance_high_pct": distance(sample_high),
            "distance_low_pct": distance(sample_low),
            "pivot": finite(pivot),
            "r1": finite(2 * pivot - previous["low"]) if previous is not None else None,
            "s1": finite(2 * pivot - previous["high"]) if previous is not None else None,
            "r2": finite(pivot + previous["high"] - previous["low"]) if previous is not None else None,
            "s2": finite(pivot - previous["high"] + previous["low"]) if previous is not None else None,
        },
    }
    metrics["assessment"] = technical_assessment(metrics, sample)

    # Derived ratios can overflow even with finite inputs. Sanitize every leaf.
    def safe(value):
        if isinstance(value, dict):
            return {key: safe(item) for key, item in value.items()}
        if isinstance(value, (float, np.floating)):
            return finite(value)
        return value

    return safe(metrics)
