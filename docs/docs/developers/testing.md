# Testing

Tests construct explicit temporary Settings/Store instances, replace network/process boundaries and never use the developer's exchange credentials. Run one API worker for the real app; isolated tests can construct their own applications.

```bash
uv run pytest -q
uv run ruff check src tests
npm run typecheck
npm run build
npm run docs:build
```

## Strategy research and monitoring

`tests/test_strategy_research.py`, `tests/test_strategy_monitor.py`, `tests/test_analytics.py` and `tests/test_restored_features.py` cover causal indicator rules, next-open historical fills, costs, immutable input reruns, native chart evidence, paper-source pinning, durable journals, metric baselines, event paging/CSV and pause/stop behavior. Demo supplies explicitly synthetic input to the same simulation engine. Retained datasets let a test verify a replay without provider calls.

`test_strategy_validation.py` exercises all six algorithm search catalogs, future-price perturbations that cannot change earlier rankings, common warm-up, disjoint and complete test windows, fresh virtual capital, fixed-setting comparisons, stable score ties, minimum-trade abstention, invalid grid rejection and pre-simulation resource limits. API tests verify offline persistence/reruns, source labels, no account/order/job changes, lock release after failure and native Broker evidence reads. These are historical simulation contracts, not evidence of profitability.

## Automated exchange strategies

`tests/test_strategy_execution.py` uses a fake venue whose order acknowledgments and native execution pages are separate. It covers typed expiring HTTP approvals, concurrent/idempotent start requests, crash recovery before review acknowledgment, no order on initial start/resume, deterministic per-candle order keys, capped sizing/precision, partial-fill gating, native base/quote fees, later corrections, unrelated account holdings, rolling order counts, loss latching, account/server/spread/data-gap guards and sanitized failures. Pause during preparation invalidates the plan; Stop retains native order reconciliation without another submission. A native timeout never retries a write. Fractional quote budgets and cross-pair allocations have explicit checks.

`tests/test_strategy_cancellation.py` checks explicit lifetime bounds and unchanged authority for older jobs, deadlines committed before submission, cancellation only after expiry, native full/partial-fill races, late execution/fee corrections and three bounded terminal status reads. It simulates process loss on both sides of the durable cancellation boundary, ambiguous responses, prior manual attempts, inactive accounts, permission changes between reads and writes, and recovery with write flags off. Separate Stop & cancel reviews are read-only until typed approval, idempotent under concurrency, survive restart, abandon prepared intents, leave unrelated orders untouched and never liquidate retained units. Fake-provider coverage exercises the shared expiry pipeline for all nine supported variants; HTTP monitor filters and CSV evidence are verified. These tests perform no authenticated exchange requests and do not establish private venue acceptance.

`tests/test_strategy_closing.py` verifies local readiness, read-only fixed sell reviews, owned-unit sizing, base-fee reserves, native price/amount/cost caps and residual estimates. Confirmations reject changed ownership/scope/permissions/expiry and recheck ledger evidence inside the submission transaction. Tests cover concurrent/duplicate approvals, interrupted prepared/submitting exits, lost native replies, partial exit expiry, late fees, same-timestamp entry/exit accounting, realized P&L and residuals. A prior Stop & cancel policy excludes the separately approved new exit; its own expiry remains active with strategy-submission permission off. All nine execution variants use simulated venues, with HTTP and journal/CSV coverage. Authenticated venue acceptance remains separate work.

These tests establish application behavior, not real exchange permissions, endpoint retention, matching-engine behavior or authenticated sandbox acceptance. Use the separate [exchange execution workflow](../guides/strategy-execution.md) for deliberate acceptance testing. Nothing in the test suite enables production execution or submits a real exchange order.

## Exchange transport and reconciliation

The exchange client, spot-support, order management, recovery, discovery and reconciliation tests replace provider transports. They check request shapes, spot/base-quantity semantics, client IDs, native pagination, cumulative quantities, execution identity/deduplication and fee corrections. Coverage badges follow implemented paths and explicit gaps; the installed SDK advertising a method cannot enable an unreviewed write or historical import.

## Authenticated exchange acceptance

The ordinary tests remain offline. The separate opt-in [Binance Testnet acceptance runner](exchange-acceptance.md) can exercise actual virtual-fund orders with a dedicated saved Testnet account, transport host pinning and isolated retained state. Never substitute production credentials or infer broader venue acceptance from one successful run.

## Messaging and local models

`tests/test_telegram.py` replaces Telegram HTTP and the native agent boundary. It covers encrypted configuration, private sender binding, webhook conflicts, durable inbound/outbound records, rate-limit ordering, uncertain delivery, startup recovery and pause races. Real-bot conversation acceptance requires separate credentials and remains a deployment check.

`tests/test_ollama.py` replaces native HTTP and process creation. It checks endpoint/model detection, credential destination isolation, fixed CLI arguments, loopback-only launch and process ownership. Automated tests never start an actual Ollama installation. Manual browser verification can exercise Start/Stop on an installed local server without downloading a model or changing the active AI profile.

## Real local-model acceptance

Run the separate opt-in [agent acceptance checks](agent-acceptance.md) against an already running Ollama service. They preserve real answers and native receipts from an isolated Demo workspace; ordinary tests do not contact it.

## Frontend and docs

The TypeScript check and Vite build validate frontend contracts and feature bundles. Docusaurus builds the documentation and checks internal links. Browser checks exercise saved experiment selection/reruns, price/equity modes, actual marker selection, the chart time brush, connection requirements and disabled execution states. Browser refresh only reads persisted strategy monitoring data; it does not execute a run.

`npm run test:e2e` runs the repository's Playwright suite when its browser/runtime prerequisites are installed. New execution backend tests are independent of that environment. Do not use real account credentials in browser fixtures or infer private venue acceptance from a successful frontend build.
