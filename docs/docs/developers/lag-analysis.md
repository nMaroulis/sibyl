---
title: Granger analysis contracts
description: Training-only nested regressions, fixed-order inference and separate later-target scoring.
---

# Granger lag analysis

`POST /api/v1/markets/granger` accepts 2–8 unique canonical spot pairs in reference-first order, an exact source, supported timeframe, 60–720 candles and one lag order 1–5. The backend pins a source snapshot, validates pairs against that provider and reads closed candles. `market_data/analysis/granger.py` performs the numerical work. No setting changes, model training jobs, strategy execution or LLM calls occur.

The engine aligns log returns without filling intervals, caps work at 719 returns and takes their most recent common consecutive suffix. For each target, both reference→target and target→reference are planned. Other target/target pairs are not tested. A fixed split at `floor(n*0.7)` precedes fitting. Training targets use p own lags, or p own plus p reference lags, with an intercept. Each design uses training-only normalization and NumPy least squares. Rank/conditioning, constant target/regressor, minimum sample and residual-variance checks abstain explicitly.

With training sample N and lag order p, the nested statistic is `((RSS_restricted-RSS_augmented)/p) / (RSS_augmented/(N-2p-1))`. Its classical survival probability uses [SciPy's F distribution](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.f.html); see the [standard Granger null and SSR F-test](https://www.statsmodels.org/stable/generated/statsmodels.tsa.stattools.grangercausalitytests.html). Only training rows enter the statistic, normalization, coefficients or nominal p. Adjustment multiplies by `2*(markets-1)`, including unavailable planned tests. It makes no correction across user requests or orders.

The later targets use frozen coefficients and strictly earlier observed returns. Return-unit MAE is reported as percent, alongside own-lags and zero-return references and relative MAE improvement. No test-driven order selection, hidden refit or last-price comparison is substituted. Evidence includes fit normalization/coefficients, training/holdout dates, sample counts, RSS/degrees, a Ljung–Box residual diagnostic with explicitly **unadjusted residual degrees of freedom**, actual model/error states and interpretation limits. The residual check is a qualification, not a proof that all inference assumptions hold; no stationarity/heteroskedasticity test or causal claim is made.

Analyst reuses `market_relationships(lags=...)` or the selected private `granger_lags` context. Full coefficient arrays are omitted from model-facing results while local JSON exports retain them. Purpose-focused tool descriptions remain compact, with the same native `AgentClient`, private request context, discovery and group lifecycle.

Acceptance tests recover a known directional process, recompute the actual F statistic/probability, perturb held-out targets without changing fits/inference, reject invalid/constant/collinear cases, verify gaps and planned-family adjustment, and exercise API/native source scope. They establish numerical contracts, not general financial predictability.
