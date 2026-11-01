"""Transparent technical indicators and a statistical forecast baseline."""

from datetime import datetime

import numpy as np
import pandas as pd

from sibyl.market_data.analysis import market_statistics, prepare_history


def indicators(
    candles: list[dict],
    window: int = 20,
    *,
    fast_period: int = 9,
    slow_period: int = 21,
    rsi_period: int = 14,
    band_std: float = 2,
    volume_multiplier: float = 1.5,
    macd_fast_period: int = 12,
    macd_slow_period: int = 26,
    macd_signal_period: int = 9,
    adx_period: int = 14,
    atr_period: int = 14,
    cmf_period: int | None = None,
    tsi_short_period: int = 13,
    tsi_long_period: int = 25,
) -> pd.DataFrame:
    """Compute SMA, EMA, Bollinger, RSI, MACD, ATR, ADX, CMF, and TSI.

    RSI, ATR, and ADX use Wilder-style exponential smoothing. Warm-up rows
    remain NaN internally; response serialization converts them to null.
    """
    frame = pd.DataFrame(candles)
    close, high, low, volume = (frame[key] for key in ("close", "high", "low", "volume"))
    frame["sma"] = close.rolling(window).mean()
    std = close.rolling(window).std()
    frame["upper"] = frame["sma"] + band_std * std
    frame["lower"] = frame["sma"] - band_std * std
    frame["ema_fast"] = close.ewm(span=fast_period, adjust=False).mean()
    frame["ema_slow"] = close.ewm(span=slow_period, adjust=False).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / rsi_period, adjust=False, min_periods=rsi_period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / rsi_period, adjust=False, min_periods=rsi_period).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    frame["rsi"] = rsi.mask((loss == 0) & (gain > 0), 100).mask((loss == 0) & (gain == 0), 50)
    frame["macd"] = (
        close.ewm(span=macd_fast_period, adjust=False).mean()
        - close.ewm(span=macd_slow_period, adjust=False).mean()
    )
    frame["macd_signal"] = frame["macd"].ewm(span=macd_signal_period, adjust=False).mean()
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(
        axis=1
    )
    frame["atr"] = tr.ewm(alpha=1 / atr_period, adjust=False, min_periods=atr_period).mean()
    up, down = high.diff(), -low.diff()
    plus = up.where((up > down) & (up > 0), 0).ewm(alpha=1 / adx_period, adjust=False).mean()
    minus = down.where((down > up) & (down > 0), 0).ewm(alpha=1 / adx_period, adjust=False).mean()
    dx = 100 * (plus - minus).abs() / (plus + minus).replace(0, np.nan)
    frame["adx"] = dx.ewm(alpha=1 / adx_period, adjust=False, min_periods=adx_period).mean()
    money_flow = ((2 * close - high - low) / (high - low).replace(0, np.nan)).fillna(0) * volume
    frame["cmf"] = money_flow.rolling(cmf_period or window).sum() / volume.rolling(
        cmf_period or window
    ).sum().replace(0, np.nan)

    def smooth(series: pd.Series) -> pd.Series:
        return (
            series.ewm(span=tsi_short_period, adjust=False)
            .mean()
            .ewm(span=tsi_long_period, adjust=False)
            .mean()
        )

    frame["tsi"] = 100 * smooth(delta) / smooth(delta.abs()).replace(0, np.nan)
    frame["volume_surge"] = volume > volume.rolling(window).mean() * volume_multiplier
    return frame


def analyze(candles: list[dict], periods_per_year: float = 365, *, now: datetime | None = None) -> dict:
    """Return chart records, descriptive statistics and a disclosed technical bias.

    Indicator smoothing restarts at every interval break. Statistics use the
    latest contiguous segment; no missing prices or volume are interpolated.
    """
    raw, breaks = prepare_history(candles, periods_per_year)
    frame = pd.concat(
        [indicators(group.to_dict("records")) for _, group in raw.groupby(breaks.cumsum())],
        ignore_index=True,
    )
    statistics = market_statistics(frame, periods_per_year, breaks, now=now)
    last = frame.iloc[-1]
    records = (
        frame.replace([np.inf, -np.inf], np.nan)
        .astype(object)
        .where(pd.notna(frame), None)
        .to_dict("records")
    )
    return {
        "candles": records,
        "price": float(last["close"]),
        "rsi": statistics["momentum"]["rsi14"],
        "trend": "Bullish"
        if last["ema_fast"] > last["ema_slow"]
        else ("Bearish" if last["ema_fast"] < last["ema_slow"] else "Neutral"),
        "volatility": statistics["volatility"]["annualized_pct"],
        "high": float(frame["high"].max()),
        "low": float(frame["low"].min()),
        "period_return": float((last["close"] / frame.iloc[0]["close"] - 1) * 100),
        "statistics": statistics,
    }


def forecast(candles: list[dict], horizon: int = 14) -> dict:
    """Project a log-return random-walk baseline with an approximate 95% interval.

    This is an uncalibrated statistical baseline, not a trained Chronos model.
    Drift and volatility are estimated from at most 90 daily observations.
    """
    frame = pd.DataFrame(candles)
    returns = np.log(frame["close"]).diff().dropna().tail(90)
    drift, sigma = float(returns.mean()), float(returns.std())
    last = float(frame.iloc[-1]["close"])
    date = pd.Timestamp(frame.iloc[-1]["timestamp"])
    points = []
    for day in range(1, horizon + 1):
        center, interval = drift * day, 1.96 * sigma * np.sqrt(day)
        points.append(
            {
                "timestamp": (date + pd.Timedelta(days=day)).isoformat(),
                "value": last * float(np.exp(center)),
                "lower": last * float(np.exp(center - interval)),
                "upper": last * float(np.exp(center + interval)),
            }
        )
    return {
        "model": "Log-return baseline",
        "trained": False,
        "horizon": horizon,
        "points": points,
        "last_price": last,
        "daily_volatility": sigma * 100,
        "note": "Approximate 95% model interval; uncalibrated and not a guarantee of future prices.",
    }


def correlation(
    histories: dict[str, list[dict]], method: str = "pearson", transform: str = "log_returns"
) -> dict:
    """Align timestamps, transform observations, and calculate Pearson or ranked correlation."""
    series = {
        symbol: pd.Series({c["timestamp"]: c["close"] for c in candles})
        for symbol, candles in histories.items()
    }
    prices = pd.DataFrame(series).sort_index()
    if transform == "prices":
        observations = prices.dropna()
    elif transform == "changes":
        observations = prices.diff().dropna()
    else:
        observations = np.log(prices).diff().dropna()
    if method not in {"pearson", "spearman"}:
        raise ValueError("Choose Pearson or Spearman correlation.")
    # Ranking before Pearson avoids a SciPy dependency for Spearman's rank correlation.
    matrix = (observations.rank() if method == "spearman" else observations).corr().fillna(0)
    return {
        "symbols": list(matrix.columns),
        "matrix": matrix.values.tolist(),
        "observations": len(observations),
        "method": method,
        "transform": transform,
    }


def performance_metrics(
    values: list[float], trade_returns: list[float], periods_per_year: float = 365
) -> dict:
    """Calculate risk and trade statistics with null ratios when their denominator is zero.

    Sortino uses the root mean square of negative period returns with a zero target.
    Calmar uses annualized compounded return divided by peak-to-trough drawdown.
    Profit factor uses percentage returns from equally reinvested round trips, not account P&L.
    """
    equity = pd.Series(values, dtype=float)
    returns = equity.pct_change().dropna()
    std = float(returns.std()) if len(returns) > 1 else 0
    downside = float(np.sqrt(np.mean(np.minimum(returns, 0) ** 2))) if len(returns) else 0
    drawdown = float(((equity.cummax() - equity) / equity.cummax()).max()) if len(equity) else 0
    wins = [value for value in trade_returns if value > 0]
    losses = [value for value in trade_returns if value < 0]
    annual = None
    if len(returns) and equity.iloc[0] > 0 and equity.iloc[-1] > 0:
        exponent = float(np.log(equity.iloc[-1] / equity.iloc[0]) * periods_per_year / len(returns))
        if abs(exponent) < 20:
            annual = float(np.expm1(exponent))
    return {
        "sharpe": float(returns.mean() / std * np.sqrt(periods_per_year)) if std > 0 else 0,
        "sortino": float(returns.mean() / downside * np.sqrt(periods_per_year)) if downside > 0 else None,
        "calmar": annual / drawdown if annual is not None and drawdown > 0 else None,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "average_win": float(np.mean(wins)) if wins else None,
        "average_loss": float(np.mean(losses)) if losses else None,
        "best_trade": max(trade_returns) if trade_returns else None,
        "worst_trade": min(trade_returns) if trade_returns else None,
        "max_drawdown": drawdown * 100,
        "drawdown_curve": [float(value) for value in ((equity / equity.cummax() - 1) * 100)],
        "observations": len(returns),
    }
