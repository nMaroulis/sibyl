# Strategy studio

The studio lets you choose an algorithm, change assumptions, run historical tests, inspect fills, and start a persistent paper job.

## Six algorithms

| Algorithm        | Entry                                                                      | Exit                                                                   |
| ---------------- | -------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| EMA Crossover    | EMA 9 above EMA 21                                                         | EMA 9 below EMA 21                                                     |
| RSI Reversion    | RSI below 30                                                               | RSI above 70                                                           |
| Bollinger Bands  | Close below lower band                                                     | Close above upper band                                                 |
| Bollinger Surge  | Lower band, RSI below 30, bullish EMA, volume above 1.5× rolling mean      | Upper band, RSI above 70, bearish EMA, volume surge                    |
| Impulse Breakout | Lower band, RSI below 35, bullish EMA/MACD, ADX above 25, volume surge     | Upper band, RSI above 65, bearish EMA/MACD, ADX above 25, volume surge |
| Quantum Momentum | Bullish MACD, TSI above 20, positive CMF, ATR above rolling 10-period mean | Bearish MACD, TSI below −20, negative CMF                              |

These names describe deterministic rules. The multi-factor strategies can be very selective and may produce no trades in a sample. None is a quantum-computing or trained AI strategy.

## Parameters

Choose a spot market, timeframe, virtual starting capital in the quote currency, and 90–720 observations (API: 60–720). Fee and slippage inputs are basis points per fill. Additional controls:

| Parameter                       | Default                  | Bounds                                     |
| ------------------------------- | ------------------------ | ------------------------------------------ |
| Fast / slow EMA                 | 9 / 21                   | 2–100 / 3–200; fast must be shorter        |
| RSI period                      | 14                       | 2–100                                      |
| RSI buy / sell thresholds       | 30 / 70; Impulse 35 / 65 | 1–49 / 51–99; blank uses algorithm default |
| Bollinger / CMF / volume window | 20                       | 5–120                                      |
| Band standard deviations        | 2                        | 0.5–5                                      |
| Volume multiplier               | 1.5                      | 0.5–10                                     |
| Stop loss / take profit         | Off                      | >0–90% / >0–1000%                          |
| Maximum round trips             | Unlimited                | 1–10,000                                   |

The advanced section also exposes MACD fast/slow/signal periods (defaults 12/26/9), ADX and ATR periods (14 each), a separate optional CMF window (blank uses the rolling window), and TSI short/long periods (13/25). Fast MACD and short TSI periods must be smaller than their slow/long periods. Bounds are shown in the API schema.

Only controls used by the chosen algorithm affect its signals. The sample must exceed the longest configured smoothing period.

## Backtest execution

A simulation warms up the maximum of 30 observations and all configured indicator periods. It computes a signal from the previous closed candle and fills at the next candle's open. It is long-only, uses all available virtual capital per entry, and does not leverage or short. Fees and adverse slippage apply to both buys and sells. Any final position is liquidated at the last close with the same costs.

The buy-and-hold benchmark uses the same effective period and entry/exit costs. Results and individual fills are saved locally; use the result selector to inspect earlier tests.

### Metrics

- Total return compares final cash with initial capital.
- Maximum drawdown is the largest nonnegative percentage loss from a prior running equity peak, including initial capital.
- Sharpe is mean candle equity return / sample candle standard deviation × square root of periods per year, with zero risk-free rate. It is zero for a flat equity path.
- Win rate counts profitable completed round trips after costs.
- Fees sum all simulated entry and exit fees.

Historical optimization can overfit. A backtest does not prove future profitability or model live execution quality.

## Paper strategy monitor

**Start paper strategy** creates a job with its own isolated virtual capital. The worker checks running jobs every 30 seconds. It acts at most once for each newly closed candle, using a current reference quote with configured fee and slippage assumptions. Equity is marked using the reference price.

Jobs, positions, last processed candles, the latest 100 fills, and a bounded 720-observation equity curve persist in SQLite. Console risk metrics summarize this retained curve and can be distorted by gaps after pauses or downtime. Restarting the API resumes running jobs without replaying already processed candles. Downtime is not backfilled: a resumed worker evaluates the latest available closed candle. If the configured price source changes, existing jobs pause and should be recreated for that source.

Pause stops evaluation without selling the virtual position. Resume continues evaluation. Open each run in the dedicated [Strategy monitor](./strategy-monitor.md) for updating charts, BUY/SELL markers, a complete decision journal, parameters, and performance details. Stop is terminal and retains the virtual position; it does not liquidate. Paper strategies never access exchange balances or create exchange orders. Run a single API worker; multiple workers are not supported for strategy scheduling.

## Risk metrics and exports

Sortino divides mean period return by the root mean square of negative period returns (zero target), annualized by square root of periods per year. Calmar is annualized compounded return divided by maximum fractional drawdown. Annualization uses the selected interval. Extreme short-sample annualization is omitted. Undefined ratios display a dash and serialize as `null`.

Profit factor is the sum of positive round-trip **percentage returns** divided by the absolute sum of negative round-trip percentage returns. It is not the ratio of cash profits to cash losses. Average win/loss and best/worst trades are percentage returns after costs. No-loss samples have undefined profit factor.

The drawdown view shows negative percentage distance below the running equity peak; maximum drawdown is reported as a positive magnitude. Export fills with fees and exit reasons, or the equity path with drawdown. Saved backtests remain selectable.

Stop-loss and take-profit thresholds use the observed close relative to entry price. They fill at the next open in a backtest and at a current quote on a subsequent worker tick in a paper job. They do not guarantee intrabar stop prices. Reaching a round-trip limit prevents further entries; paper jobs become completed after their final exit. Pause retains the virtual position. Completed and stopped jobs cannot resume.

Freqtrade, ML/RL strategies, and automatic live exchange strategies are marked **Coming soon**. Broker can inspect current parameters but cannot run or execute them.
