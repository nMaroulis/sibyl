---
title: Measured returns, outcomes and execution receipts
description: Source-bound cash-flow review, prospective forecast actuals and atomic execution notifications.
---

# Measured returns, outcomes and execution receipts

These services compose existing domain infrastructure; they add no agent framework, provider SDK or generic job queue. User mutations are explicit FastAPI actions, native agent tools are read-only, and local workers use the existing supervisor.

## Measured account returns

`services/portfolio/returns/` separates validated review contracts, Decimal calculation and period persistence. `AccountPerformance.returns` owns `return_periods` and `return_audit` in the workspace database. Fresh snapshots reuse strict `RiskObservations`: one to ten active accounts, one environment/reference source, dated fresh prices, bounded reads and configuration/freshness checks at commit. Each account has its own receipt interval. The set must complete within 45 seconds; no cross-exchange atomic-snapshot claim is made.

Opening/closing valuations are immutable. Connection/feed configuration is checked using a fingerprint of a private encrypted-configuration guard; encrypted credentials themselves never enter the period or API. Old portfolio chart samples are not sufficient accounting boundaries.

Funding evidence is bounded to 2,000 candidate observations. Reviews bind native material facts, actual movement times and historical principal values in USDT. Wallet scope uses existing funding rules/reviews; own transfers require current confirmed links. Both legs must be present, reviewed and inside all relevant valuation boundaries before combined external flows cancel. Manual external-flow assertions are separate, labeled period inputs, capped at 200; they never modify native ledgers. Principal excludes fees, so fees/income remain in performance. Coverage is an explicit user assertion bound to current funding facts, wallet effects, transfer links, reviews and closing observations. Any material change invalidates the result until reviewed again. It is not independent provider completeness verification.

The calculation is `gain = end - start - sum(flows)` and `return = gain / (start + sum(flow * remaining_time / period_time))`, using Decimal arithmetic and exact elapsed timestamp weights before JSON conversion. Nonpositive weighted capital returns no percentage. This is a timestamp-weighted Modified Dietz approximation, distinct from exact time weighting, market FIFO or tax accounting. Methodological background: [CFA Institute GIPS handbook](https://www.gipsstandards.org/wp-content/uploads/2021/03/gips_handbook_2nd_edition.pdf); using this formula does not claim GIPS compliance.

Routes under `/api/v1/account-returns`: list/start, `/{id}` evidence/export, `/{id}/close`, `/{id}/flows/{event}` review, `/{id}/manual`, manual removal and `/{id}/coverage`. All mutations use period revisions; reviews/coverage also bind exact source/evidence fingerprints. Accountant's `investment_returns` reads the selected `return_period_id` through native private context.

## Prospective forecast outcomes

`forecasting/forward.py` owns `forecast_tracking`. Only current-feed, non-Demo outputs with targets after their original save time can enroll. Tracked outputs are excluded from ordinary latest-20 cleanup. A workspace budget limits tracking to 200 outputs.

Hourly due checks read only exact-source/environment/pair daily archive rows, matching the candle whose close time equals the target. Actual receipt time cannot predate that close. No other feed, interpolation or zero substitutes for missing actuals. Explicit refresh uses the original source and a 90-candle page. Scoring keeps original output/input fingerprints; corrections retain a per-target version and the latest five receipts.

Metrics use observed targets only. Equal-horizon aggregation across tracked outputs includes model, naïve last-close and original-window drift benchmarks. Cross-horizon summaries are descriptive, not independent samples or unbiased model selection. Paused revisions fence in-flight commits. The worker never retrains, recalibrates, deploys or contacts a provider. Chronos's `forecast_outcomes` reads existing evidence; `forecast_tracking` in page context selects this tool in no-LLM mode.

Routes under `/api/v1/forecast-models`: `/{model}/tracking`, `/outputs/{output}/track`, `/outputs/{output}/tracking`, tracking `/action` and `/check?refresh=true`.

## Atomic execution observations

`alerts/orders/events.py` appends sanitized order/fill evidence inside the source transaction: central `OrderLifecycle.write`, new discovered-order insertion and `AccountLedger.upsert_fills`. No-op writes/display-only fill changes do not emit a receipt. Order cumulative quantities and individual fills retain distinct event types; historical imports are labeled. The journal is bounded by pruning every 1,000 inserts to about 100,000 retained changes.

`OrderAlerts` commits per-account cursors and inbox inserts in one transaction. Creation/edit/resume use the global journal tail as a future-only baseline. One due subscription processes at most 100 account events per pass, with oldest-check ordering for fairness. Gap detection pauses rules whose cursors predate retained history. Revision checks protect editors and subscription controls; notifications retain their original rule revision and environment. No provider reads or trading side effects occur in evaluation.

`/api/v1/order-alerts` provides list/create, `/{id}/edit` and `/{id}/action`. The existing alert-delivery allowlist adds `order`; recipient reviews, freshness/cooldown, future-only policies, outbox transactions and send fencing are unchanged. Broker's `execution_alerts` reads saved rules and recent notifications. Restored archives pause new tracking and execution subscriptions before normal workers can resume.

Acceptance tests use controlled valuation/market evidence, actual SQLite transactions, native group calls and HTTP endpoints. They establish contracts and causal selection, not authenticated venue acceptance, historical funding completeness or real forward predictive skill. No live order or Telegram message is required by the suite.

Native Accountant responses summarize valuation boundaries and return at most twenty flows per call (`flow_offset` pages further evidence). Chronos model-wide reads return at most twenty compact tracked-output summaries plus equal-horizon aggregates; a selected run returns its bounded target evidence. Full originals remain available through explicit HTTP exports. Period removal and tracking removal require the current revision and never alter native funding/fills or the original recent forecast.
