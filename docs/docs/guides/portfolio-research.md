---
title: Portfolio lab
description: Backtest a target allocation across multiple assets, inspect costs and rebalance decisions, and replay exact inputs.
---

# Portfolio lab

Open **Strategies → Portfolio lab** to test a mix of assets rather than a single buy/sell algorithm. The simulator compares fixed target weights and rebalancing against cost-matched buy-and-hold and quote cash. It uses virtual capital and does not place orders or start a monitored strategy.

## Build a study

1. Choose your normal account mode or the smaller **Demo preview** option. Demo remains a clearly labeled synthetic source; account activation does not enable trading here. With no active account, saved studies can still be read and replayed offline.
2. Add **2–8 exact spot pairs**, all quoted in the same currency. Enter asset weights totaling at most 100%; the remainder stays in that quote currency as cash. **Equal weights** assigns the entire budget across the chosen assets. No stablecoin parity or currency conversion is assumed.
3. Choose current closed candles or **Immutable saved datasets**. Current input follows the market-data source named below the selector, independently of connected-account venue. It saves exact inputs before simulation. Saved input needs a separate compatible dataset for each asset; the searchable picker includes the archive's bounded metadata catalog.
4. Choose timeframe, capital and an interval or drift rule. Interval rules act every specified number of candles, not calendar months. Drift rules inspect the largest absolute asset/cash weight deviation from the fixed targets at the previous close, measured in percentage points.
5. Expand **Costs & simulation assumptions** to change fees and adverse slippage in basis points. Both apply to every simulated buy/sell. Choose **Run portfolio backtest**.

Each input must have 60–2,000 candles. All assets must share the exact source, environment, quote and timeframe. The engine uses their common consecutive UTC window, with at least 60 bars. It reports the actual window and any trimming. It rejects gaps; it never forward-fills missing prices or silently converts an aliased quote.

## Inspect what happened

The result shows final equity, net return, maximum drawdown and excess return versus buy-and-hold. Excess return is a **percentage-point difference**, not a relative percentage improvement. Buy-and-hold starts with the same asset/cash mix and costs, without subsequent rebalances. Cash earns zero and is denominated in the same quote currency.

The chart has four views:

- **Equity & benchmarks:** simulated rebalanced portfolio, buy-and-hold and cash.
- **Drawdown:** each portfolio's negative distance below its running peak, including initial costs.
- **Asset allocation:** close-marked asset/cash weights before the planned final exit.
- **Price & trades:** select one asset; green markers buy and rose markers sell at actual simulated prices. Dense ranges show bounded representative markers; the complete paged fill table and exports retain every execution.

Drag across the plot or use its range handles to zoom; **Reset zoom** restores the window. Charts disable per-point animation and mount one view at a time.

**Risk, costs & source receipts** shows observed Sharpe/Sortino, annualized volatility, turnover, fees/slippage, input fingerprints and engine identity. Undefined ratios remain unavailable. Rebalance gross turnover sums traded mark value divided by pre-rebalance NAV; initial allocation and final liquidation are excluded. Rebalance count includes only decisions that actually traded. Zero-trade scheduled checks remain in the exported event evidence.

**Simulated buys & sells** pages 50 fills at a time. Exact execution times distinguish opening trades from the final closing exit. Candle labels identify interval opens. **Export full study** retains curves, weights, source receipts, decisions, trades and parameters; **Export fills CSV** is a flat execution ledger. Ask Broker to explain the selected saved study using its native read-only evidence tool.

## Replay and assumptions

**Rerun exact inputs** uses the original immutable datasets and parameters with no provider calls. It requires the same portfolio engine and matching trade/equity fingerprint; otherwise it refuses to save a misleading replay. A rerun creates a separate artifact linked to its parent. Retain up to 100 studies; deleting a study keeps its input datasets, orders, account records and monitored runs.

Decisions use fixed schedules or earlier closes; trade sizing uses the following observed open. A post-cost equity solve accounts for fees/slippage before assigning target units, and sells fund buys. This avoids simulated borrowing to cover fees. Quantities are fractional; minimum orders, liquidity, spread variation, partial fills and venue precision are not modeled. Cash has no yield. Both invested portfolios pay a planned final-close liquidation; allocation history and pre-liquidation holdings describe the portfolio before that exit.

User-chosen assets/weights and repeated experiments can overfit or reflect survivorship bias. Historical annualization is descriptive, not a forecast. This fixed-allocation research does not train or coordinate multiple signal strategies. Live multi-asset allocation/execution, financing, richer venue constraints and broader real-market acceptance remain pending.
