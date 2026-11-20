# Multi-asset portfolio research

`strategies/portfolio/` separates strict input contracts, a pure deterministic simulator and immutable input/artifact ownership. `Strategies.portfolios` attaches the research service without touching the paper/exchange execution worker. No new dependency, automatic order path or agent runtime is added.

## Inputs and bounded execution

`PortfolioStudy` accepts 2–8 distinct asset/pairs with one exact quote, fixed positive weights totaling at most 100%, 60–2,000 bars, current/demo/saved input, capital and quote fee/slippage assumptions. Input flags reject a dataset ID in current mode or a missing ID in saved mode. Server number validation rejects booleans/nonfinite values. Current reads hold one market-source snapshot; native quote aliases are refused before capture. Each input is retained through the existing immutable CandleArchive contract. A later source failure can leave captured input receipts but never a successful study.

Saved input preflights metadata counts before loading bodies, verifies archive hashes and requires exact pair/timeframe/source/environment matches. The join uses the full consecutive intersection, without resampling, missing-date drops or forward filling. It retains each original input receipt and discloses trimmed ranges. Public APIs may return fewer than the requested observations; the actual common window is reported. One study per service instance runs at a time; this is bounded synchronous research, not a distributed queue. Keep at most 100 artifacts.

## Ledger and target solve

At the initial scheduled open, targets are known from the user. Later interval decisions use the fixed candle cadence; drift decisions compare all asset weights **and residual cash** to targets at the immediately previous close. Quantities are then sized at the execution open. This assumes execution from an observed opening reference rather than filling signals at their own later close. All candles are already closed input; no future close determines an earlier rebalance.

Let E be pre-trade marked equity, Vᵢ existing marked asset value, wᵢ fixed target fractions, f the fee fraction and s the adverse slippage fraction. Target post-cost equity T solves:

```text
Δᵢ(T) = wᵢ T − Vᵢ
buy friction  = s + f + sf
sell friction = s + f − sf
T + Σ max(Δᵢ,0)(s+f+sf) + Σ max(−Δᵢ,0)(s+f−sf) = E
```

Bounded bisection over [0,E] solves this monotonic piecewise-linear equation. Desired units are wᵢT / opening price. Sells run before buys. Fees use executed quote notional; slippage cost uses the absolute difference from the observed reference. Cash/units cannot become materially negative, and the marked equity decrease is checked against fees plus slippage. Tiny floating-point trades are skipped within a capital-scaled tolerance, not venue precision. Iteration order cannot assign priority to an asset merely because cash was spent first.

Every bar records close equity/weights. The planned final-close liquidation applies to both rebalanced and identical-initial-weight buy-and-hold portfolios. Allocation history and pre-liquidation holdings remain before that final exit. Fill timestamps label the candle; `execution_at` and `phase` carry actual open versus close timing. Drift `decision_at` is the preceding candle end, equal to the next open on the consecutive grid. Rebalance events retain no-trade decisions; actual rebalance count requires at least one fill.

Metrics use initial cash plus one close value per evaluated bar, with the final point replaced by liquidated cash. Costs are included in the first/last period; no fake extra return interval is added. Sharpe uses sample return standard deviation, Sortino the root mean square of negative returns and zero target. Undefined ratios are null. Crypto annualization uses the selected timeframe; extreme exponential annualization is unavailable. Maximum drawdown includes initial capital as a peak. Gross rebalance turnover excludes initial/final fills; total traded notional and all fees remain separate. Excess return is a percentage-point difference versus cost-matched buy-and-hold.

## Artifacts, routes and native Broker

Artifacts use `runs.kind=portfolio_backtest`, separate from paper jobs, exchange intents and ordinary single-asset backtests. They retain a versioned engine, recipe with immutable dataset IDs, data receipts, complete trades, decisions, allocation history, marks and benchmarks. Replay fetches no provider, verifies engine identity and exactly matching trade/equity fingerprint before saving a child. Deletion removes only the research artifact. There is no automatic replay or deployment.

All routes use normal workspace access control and `Cache-Control: no-store` under `/api/v1/strategies`:

| Route | Behavior |
| --- | --- |
| `GET /portfolios?demo=…` | Up to 100 compact saved summaries; no provider reads. |
| `POST /portfolios` | Capture/load inputs and publish one historical simulation. |
| `GET /portfolios/inputs` | At most 1,000 immutable dataset metadata records, no candle bodies. |
| `GET /portfolios/{id}` | Full saved evidence/JSON export. |
| `POST /portfolios/{id}/rerun` | Offline version/fingerprint-checked replay. |
| `DELETE /portfolios/{id}` | Delete one research artifact, retaining inputs/trading state. |

Broker lists recent portfolio IDs in its native `strategy_context` and reuses `backtest_report` and typed `strategy_help(topic='portfolio')`. Large curves/allocation arrays are excluded from model-facing returns; benchmarks are compact and fills/rebalance events are limited to ten. Existing private `backtest_id` context selects the report. No mutation/deployment tool is exposed. No-model responses label synthetic/observed inputs and percentage-point comparisons correctly.

`tests/test_portfolio_research.py` uses independent closed-form flat-price costs, full-allocation cash checks, symbol-order comparisons, causal close/open fixtures, exact window/quote/source checks, invalid/tampered inputs, replay and private HTTP/native tool tests. Synthetic contracts do not establish real-market execution quality or future profitability. Coordinated live multi-asset strategies, venue constraints, richer flows/currencies and broader real-data acceptance remain separate pending work.
