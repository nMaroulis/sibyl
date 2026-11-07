---
title: Lag predictability
description: Explore Granger lag tests with chronological holdout evidence and explicit assumptions.
---

# Does a market's past help explain another?

In **Markets → Correlations**, choose exact pairs and expand **Lag predictability · Granger analysis**. The first selected pair is the reference. Choose a lag order from one to five candle intervals, then **Run lag analysis**. Each reference/target pair is tested in both directions; the other matrix pairs are not silently added. This panel always uses log returns, even when the matrix displays price levels or absolute changes.

A lag order of three includes lags 1, 2 and 3. The restricted model uses the target's own past returns plus an intercept; the augmented model adds the reference's past returns. The classical F test asks whether those added coefficients jointly improve the earlier fit. This is **Granger predictability, not proof of economic causation**, independent information, stable future performance or a profitable strategy.

## Read the evidence

- **Training F / nominal p** come from the earlier 70% of the shared consecutive return window. They never use held-out targets.
- **Adjusted p** applies Bonferroni over both directions for this request's reference pairs, including unavailable tests. It does not correct repeated windows, alternative lag choices or your earlier experiments.
- **Held-out MAE improvement** compares fixed augmented coefficients with the own-lags model on the later 30%. Positive means lower error; negative means worse. Expand **Held-out errors & assumptions** for both absolute errors, a zero-return reference and actual test-target counts.
- **Residual serial-dependence flags** qualify classical inference. Their absence does not establish stationary returns, homoskedasticity or correct specification.

The models use only actually observed prior returns for each one-step prediction. Training normalization and coefficients remain fixed through testing. The later window never chooses a lag order, coefficients or nominal p-values. This is a one-split historical comparison, not walk-forward deployment or prospective forecast acceptance.

Missing intervals are never bridged: Sibyl uses the most recent shared consecutive suffix and reports earlier discarded returns. Each model needs at least 60 training targets, at least ten per augmented coefficient and 21 later test targets. Short, constant, collinear or near-perfect fits remain unavailable. Increase the candle window or lower the chosen order deliberately. Exact dates, feed, timeframe, source/Demo attribution and planned test count remain visible.

**Export lag evidence** saves all reported models, diagnostics, errors and provenance as JSON. **Ask Analyst** passes the selected pairs/order/source through native ProtoLink page context; the agent recalculates bounded same-source evidence and receives compact results. Live data can change between requests. No LLM is required for the numerical calculation.

Classical p-values rely on stable, correctly specified linear dynamics and suitable error assumptions. Heteroskedasticity, omitted markets, regime changes and data selection can invalidate a simple significance interpretation. See [developer contracts](../developers/lag-analysis.md).
