# Shared strategy risk admission

`strategies/execution/risk/` separates typed policies (`contracts.py`), native-ledger projection (`ledger.py`), bounded reference prices (`prices.py`) and persistence/lifecycle admission (`service.py`). It reuses the existing native fill accounting, `Valuation`, shared exchange order pipeline and strategy lifecycle lock. It introduces no exchange client, agent write tool or independent reservation ledger.

## Scope and accounting

Two durable policy rows isolate `production` and `test`. New exchange runs automatically participate in their environment. Demo and paper runs, manual orders and unrelated wallet holdings are excluded. All retained exchange runs are included, including terminal runs' P&L, residual ownership and unresolved orders. More than 100 runs per environment fails closed; each projection retains the existing 10,000-native-fill budget.

Each coherent SQLite snapshot rebuilds cash/units from linked native fills. Observed cumulative base quantity must match imported quantity. Native costs, fees, sides and environments use the existing reconciliation comparison. An ordinary open order with reconciled partial fills is assessable; terminal incomplete pages, unknown writes, missing costs/fees and third-currency fees are not. Prepared unsubmitted orders consume no capacity until admission.

Using current reference USDT rates:

```text
allocated = sum(original_quote_budget * quote_rate for retained allocations)
position = sum(owned_base * base_rate)
pending_buy = sum(unfilled_base * max(limit_price * quote_rate, base_rate))
exposure = position + pending_buy
run_pnl = (native_cash - original_quote_budget) * quote_rate + owned_base * base_rate
daily_pnl = sum(run_pnl - period_baseline[run_id])
daily_loss = max(0, -daily_pnl)
```

Pending sells do not reduce exposure. Active/paused allocations and terminal runs with holdings/unresolved orders retain their full original budget. All terminal run P&L remains in the day's calculation after allocation headroom is released. A new allocation contributes zero starting P&L rather than an inflow gain. This is reference-marked strategy evidence, not whole-account P&L or a guaranteed executable price. Foreign-quote cumulative P&L is translated at current rates; conversion moves can therefore change the observed metric.

The first complete assessment records existing cumulative P&L as the initial baseline. New jobs subsequently enter at baseline zero. A later UTC day uses the prior assessment's last observed P&L as its baseline, preserving gaps across downtime. No exact-midnight mark is claimed. Late fills/corrections affect the current observed period. The last complete baseline is never replaced by an incomplete assessment. Missing previously tracked jobs fail closed instead of erasing loss contributions.

## Prices and transaction boundaries

Conversion uses a pinned observed production feed, including for virtual exchange funds. Existing `Valuation` direct/inverse/bridge paths, quote/time budgets and native stablecoin/fiat rates are reused. Only USDT itself is identity-valued. Every other price requires a dated `fresh` quote; no undated or Demo fallback is accepted. Assessments expire after 60 seconds; original quote times remain within -60/+300-second future/age bounds. Reads happen outside SQLite write transactions. A private hash of encrypted market/source-account configuration rejects settings changes without decrypting credentials or serializing them to evidence.

Assessment commit reloads current policy and rebuilds current ledger ownership. It rejects changed revisions, missing new asset prices, expired evidence and older assessments arriving after a newer committed one. Risk policy changes serialize with the existing lifecycle lock. Preview/Start and Resume also use this control, with unused Start reviews pinned to the policy revision.

The shared `ExchangeTrading._execute` native-write transaction calls `PortfolioLimits.admit` for automatic signal orders. It validates the current job/account/environment, policy generation, daily latch and fresh prices, then **rebuilds positions and outstanding buys in that same `BEGIN IMMEDIATE` transaction**. Candidate buys consume prospective capacity before their durable `submitting` state is committed. The next admission sees that committed intent, including an uncertain in-flight write; capacity is not released based on a missing acknowledgment. This prevents two local writers from spending the same headroom without a second reservation table.

Admission can detect a late-fill daily-loss breach. It persists the latch, affected pauses, abandoned unsent intents and audit **before the caller raises the refusal**, so rollback of a rejected order cannot silently erase the loss lock. Failed evidence refuses the write and records a safe quality diagnostic. Provider/storage errors never become invented P&L. Existing domain guards, global halt, per-run limits and both backend permissions remain independent.

## Persistence and lifecycle

`strategy_portfolio_limits` stores policy/revision, lock/tripped UTC day, baseline/latest P&L maps, last complete assessment and a safe quality error. `strategy_limit_events` retains the latest 200 policy/lock/quality-pause events per environment; reads return the latest 20. Samples include reference paths/timestamps and per-run contributions. Private feed fingerprints are omitted from HTTP and native agent tool evidence.

Changing a policy pauses all running exchange jobs in its environment and abandons prepared unsent signal intents. A daily breach increments the policy revision, latches that environment, pauses its running jobs and invalidates old reviews. The lock cannot be disabled or released on the breach UTC day; a later-day release needs fresh evidence below the daily cap and the current revision/typed phrase. Changing thresholds preserves the baseline and latch. Release resumes nothing and does not release the independent manual halt or per-run loss latches.

The existing strategy worker checks enabled policies before evaluating exchange jobs, including retained stopped positions. Assessment failure pauses affected running jobs without replacing the last complete sample. An admitted/in-flight native order is not recalled; cancellation, separately approved closes and manual orders retain their existing authority. This is not distributed coordination or an automatic liquidation policy.

## HTTP and ProtoLink

All paths are below `/api/v1/strategies/exchange`, with existing workspace token/origin controls. Successful reads/writes and revision conflicts use `Cache-Control: no-store`. Bodies reject unknown fields, boolean/string numeric values and non-finite/negative caps.

| Method | Path | Contract |
| --- | --- | --- |
| GET | `/limits` | Passive production/test state, dated metrics, reference evidence and history |
| POST | `/limits/{environment}` | `enabled`, `source`, three positive caps, strict nonnegative `revision`, `confirmation: SAVE STRATEGY LIMITS`; all caps required when enabled |
| POST | `/limits/{environment}/check` | Bounded observed public reference refresh; no order write |
| POST | `/limits/{environment}/release` | Current `revision`, `confirmation: RELEASE DAILY LOSS LOCK`; prior-day lock only, fresh assessment, no resumes |

Broker's ordinary typed ProtoLink `portfolio_limits()` tool reads saved policies/evidence. `strategy_help(topic="limits")` explains setup and semantics. No agent can save, assess or release a policy, change execution flags, or submit an order.

`tests/test_portfolio_limits.py` exercises account aggregation, review/start races, native-write headroom, partial/unresolved orders, late fees, stopped positions, quality failures, policy revisions, UTC rollover/gaps, persistence, deliberate releases, HTTP validation and source privacy. The existing execution/control/closing/cancellation suites cover independent order authority. Ordinary tests use isolated native-shaped venues and never read saved user credentials.
