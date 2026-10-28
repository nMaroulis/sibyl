# Market statistics and technical bias

Open **Markets**, select a feed, exact pair and candle interval, then scroll to **Market statistics**. Statistics are calculated in Python from that feed's closed OHLCV candles. They use no LLM, new data subscription or additional provider requests. Offline Demo uses the same calculations on explicitly synthetic data.

## Read the sample first

Every result shows its source, pair, timeframe, first/last candle opening timestamps, actual consecutive candle count and return count. All periods mean **candles of the selected interval**: a 20-candle reading on `1h` is not a 20-day reading. Volume is the provider's base-asset volume, not market-wide turnover or order-book liquidity.

If intervals are missing or irregular, smoothing restarts after each break. The statistics use **only the latest contiguous segment** and disclose how many of the loaded candles it contains. Missing intervals are never interpolated. The chart can still show earlier segments, with gaps marked.

A candle becomes stale when time since its expected close exceeds the greater of **two selected intervals or 120 seconds**. Historical statistics remain available, but the overall current score is withheld. Forming or future candles are rejected. Missing warm-up history and zero denominators display **—**, rather than invented neutral values.

Chart zoom changes the visible viewport only. It does **not** change the statistical sample or the context sent to Analyst. Change the timeframe or **Observations** control to recalculate the sample.

## Technical bias, from 0 to 100

The side card summarizes **directional technical alignment**. Higher means more bullish, not safer, more valuable or more likely to make money. It is a fixed, uncalibrated heuristic, not an investment-quality rating, trading instruction or probability of profit.

Expand **What makes this score?** for the actual votes and available weights. Each component votes 0, 50 or 100:

| Component | Weight | Bullish: 100 | Neutral: 50 | Bearish: 0 |
| --- | --- | --- | --- | --- |
| EMA alignment | 25% | EMA 9 > EMA 21 | Equal | EMA 9 < EMA 21 |
| Medium-term trend | 20% | Close > SMA 50 | Equal | Close < SMA 50 |
| MACD momentum | 20% | MACD > signal | Equal | MACD < signal |
| RSI momentum | 20% | RSI > 55 | 45–55 inclusive | RSI < 45 |
| Volume pressure | 15% | CMF > 0.05 | −0.05–0.05 inclusive | CMF < −0.05 |

The score is the rounded weighted mean of available votes. Missing votes are excluded and their weights are visibly absent; a zero-volume source can still have 85% of the original weight. An overall score requires **50 consecutive candles, fresh history and at least 80% available weight**. Floating-point equality uses relative tolerance `1e-10` and absolute tolerance `1e-12` for the direct comparisons. A score at least 65 is **Bullish**, at most 35 is **Bearish**, otherwise **Mixed**. Version: `technical-bias-v1`.

These related indicators are not independent confirmations. Short samples, moving-average initialization and the chosen interval can materially change the result. An elevated RSI can coexist with a bullish score: the page separately notes readings above 70 or below 30, without assuming a reversal.

## Available readings

Each statistics card shows its main readings first. Expand **More readings & definitions** for the remaining values and a definition of every reading. Hovering a metric also shows its definition. Prices retain the pair's quote unit; base volume retains the base unit.

| Group | Implemented readings |
| --- | --- |
| Returns & distribution | Sample, 1/5/20/60-candle return; positive-candle share; mean, median, best and worst candle returns |
| Trend | EMA 9/21, SMA 20/50/200, close distance from SMA 50, ADX 14 |
| Momentum | RSI 14, MACD 12/26 and signal 9, histogram, ROC 10, stochastic %K 14 and %D 3 |
| Volatility | Sample candle and annualized volatility; ATR 14 and ATR/price; Bollinger width and %B; annualized downside deviation |
| Historical risk | Maximum and current close-based drawdown within the sample; zero-rate Sharpe and zero-target Sortino; historical one-candle VaR and expected shortfall at 95% |
| Volume & flow | Latest/mean-20 base volume; latest volume relative to the preceding 20; CMF 20; rolling typical-price VWAP 20 and distance; 20-candle OBV change |
| Price references | Sample high/low and distance; previous 20-candle high/low excluding the latest; position in the sample range; previous-candle classic pivot, R1/R2 and S1/S2 |

### Calculation details

- Simple return is `close[t] / close[t−1] − 1`. An N-candle return needs N+1 closes. Mean, median, best/worst and positive-return share use those simple returns.
- Sample volatility uses standard deviation with `ddof=1`. Annualization multiplies by `sqrt(365 × 86400 / interval_seconds)`. Intraday extrapolation and short samples can be unstable; no future volatility is implied.
- Sharpe is mean return / sample deviation × the same annualization factor, with zero risk-free rate. Sortino uses the root mean square of `min(return, 0)` across **all** returns, with zero target. They require at least two returns and a denominator above `1e-12`. No transaction costs are modeled.
- Drawdown uses the running maximum **close** of this sample. The maximum and current declines are positive loss percentages. They are not intrabar, lifetime or account drawdowns.
- Historical VaR is `max(0, −quantile(returns, 0.05))`; the quantile uses linear interpolation. Expected shortfall is `max(0, −mean(returns ≤ that quantile))`. Both are percentages for **one selected candle interval**, require at least 20 returns and describe the observed tail. Neither is a maximum loss or a calibrated forecast. All-positive tails produce zero, not a negative loss estimate.
- EMA and Wilder-style exponential smoothers initialize at the segment's beginning, using pandas `adjust=False`. RSI needs 15 candles, ATR 14, ADX is shown after 28, and MACD after 35. They can differ from a chart initialized using a longer history. SMA 200 requires 200 candles; choose 365 or 720 observations where supported.
- Bollinger bands are SMA 20 ± two **sample** standard deviations. Width is `(upper−lower)/SMA × 100`; %B is `(close−lower)/(upper−lower)` and can exceed 1 or fall below 0.
- Stochastic %K is `100 × (close−lowest low 14)/(highest high 14−lowest low 14)`. %D is its three-candle mean. A zero range is undefined.
- Rolling VWAP uses `(high+low+close)/3 × volume` over the last 20 candles. It is an OHLCV approximation, not session or tick VWAP. Relative volume compares the latest volume to the **preceding** 20, excluding the latest. OBV change sums signed base volume for the latest 20 close changes; it requires 21 closes and is not lifetime OBV.
- Price references are mechanical observations, not confirmed support/resistance. Pivot uses the **previous selected candle**: `P=(H+L+C)/3`, `R1=2P−L`, `S1=2P−H`, `R2=P+H−L`, `S2=P−H+L`.

Indicator background: [Fidelity's technical-analysis guide](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/overview), [ATR](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr), and [Bollinger bands](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/bollinger-bands). Sibyl's exact initialization, score and scope are defined above.

## Export and discuss

**Export statistics** saves numeric readings, units, definitions, score votes and sample/source identifiers as CSV. It exports the full consecutive analysis sample's statistics; **Export visible candles** in the chart exports only the viewport's raw OHLCV.

**Ask Analyst** calls the same backend analysis through its native ProtoLink tool. It can read the statistics, score votes, missing inputs and warnings on demand. Without an LLM, the tool snapshot still reports observed bias and risk. Neither Analyst nor these scores can submit orders.

These readings cover descriptive price/volume analysis. Fundamentals, order-book depth, funding, derivatives positioning and a validated predictive model are outside this score. Use the separate research and strategy-validation workspaces for their implemented evidence.
