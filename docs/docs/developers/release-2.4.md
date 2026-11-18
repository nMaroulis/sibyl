# v2.4.0 implementation plan

This release is being implemented in six dependency-ordered batches. Entries below are engineering work, not a claim of authenticated acceptance. Provider-specific limitations remain in the capability inventory. Multi-user hosting and cited web research remain deferred.

v2.4.0 targets the remaining planned implementation work. The following release will focus on hands-on testing, robustness fixes, visual refinement and UX improvements. Automated validation remains part of each implementation batch; live provider acceptance is recorded separately.

## 1. Accounting and reconciliation

- [x] Account/asset FIFO across trading pairs, historical reporting-currency conversion and third-currency fees/rebates, with unknown-basis and ordering evidence.
- [x] Audited fill correction history, source revisions and atomic ledger/checkpoint behavior.
- [x] Reviewed asset openings, existing documented/reviewed funding effects and cross-market one-to-one transfer lot carryover with immutable evidence.
- [x] Audited split/merged transfer groups with exact principal matrices, pair/group reservation conflicts, current source/review checks and whole-group cross-pair FIFO carryover.
- [ ] Additional fee conventions and independently verified external-flow classifications.
- [x] Bybit same-UID UNIFIED wallet transfer history with native pagination, local revision evidence and optional background checks.
- [x] Import selected-pair MEXC fills over a bounded rolling window with durable bisection, one-day overlap and both self-trade legs retained.
- [x] Import CoinEx selected-market cash spot fills through frozen 30-day queries, native page checkpoints and one-day incremental overlap.
- [x] Import BitMart v4 selected-market cash spot fills through bounded seven-day queries, native time-window splits and shared exact-order identities.
- [ ] Wider funding/history adapters and account balance reconciliation.

## 2. Exchange infrastructure

- [x] Reviewed manual GTC limit/cancel adapters for the eleven remaining configured production providers, with captured native request contracts.
- [x] Add account-wide OKX cash spot discovery, resumable native pages, supported-account controls and read-only detail/fill reconciliation.
- [x] Add direct OKX client-ID recovery for reviewed cash spot orders, with creation-window and immutable-detail checks and preserved uncertain outcomes on misses.
- [x] Add Bybit UTA open/recent cash spot discovery with native pagination and bounded retention.
- [x] Add Bybit UTA client-ID recovery with a durable history fallback.
- [x] Add KuCoin Classic client-ID recovery with HF and legacy detail reads.
- [x] Import KuCoin Classic open and selected-pair recent spot orders with restart-safe native checkpoints.
- [x] Import Bitstamp's account-wide open spot orders and disclose its open-only discovery scope.
- [x] Add direct client-ID recovery for verified Gemini spot GTC orders.
- [x] Discover account-wide Gemini open spot limit orders.
- [x] Discover Gate open and recent finished cash spot orders with native page checkpoints.
- [x] Recover uncertain Gate GTC spot orders by client ID with a bounded finished-order fallback.
- [x] Discover Bitget Classic open and recent regular spot orders with durable native order-ID checkpoints.
- [x] Reconcile exact Bitget Classic spot fills through the shared execution ledger.
- [x] Recover reviewed Bitget Classic spot limits by exact `clientOid` with cancellation retention shown in Settings.
- [x] Discover MEXC account-wide open and selected-pair recent spot orders with durable timestamp-window checkpoints.
- [x] Recover reviewed MEXC spot GTC limits by exact pair and client ID within the native query window.
- [x] Reconcile MEXC exact-order fills through the shared ledger with reported native fees.
- [x] Reconcile Gate cash spot orders through exact native parent and execution reads with durable seven-day query checkpoints.
- [x] Discover HTX open spot orders across the verified wallet with native order-ID checkpoints.
- [x] Discover selected-pair HTX recent orders through bounded 48-hour windows with explicit cancellation retention.
- [x] Recover reviewed HTX GTC spot limits by exact client ID and verified wallet and original terms.
- [x] Reconcile HTX exact-order executions using native internal IDs, parent-wallet validation and explicit fee-deduction uncertainty.
- [x] Discover CoinEx account-wide open cash spot orders with native page checkpoints.
- [x] Discover recent CoinEx finished orders by filtering creation time across bounded native pages.
- [x] Recover reviewed CoinEx spot GTC limits through client-filtered pending and bounded finished-order scans.
- [x] Reconcile exact CoinEx native fills and reported fees with order-scoped deal identities.
- [x] Discover BitMart v4 open cash spot orders with explicit bounds covering older native orders.
- [x] Discover recent BitMart finished orders through durable capped-window splits.
- [x] Recover BitMart spot GTC limits by exact client ID and verified original terms.
- [x] Reconcile BitMart exact-order executions with native trade IDs and explicitly reported fee currency.
- [x] Discover Poloniex account-wide open cash spot orders with exact native ID checkpoints.
- [x] Discover recent Poloniex terminal orders using frozen update-time bounds, including older orders updated recently.
- [x] Recover Poloniex cash spot GTC limits through exact client-ID details and verified original terms.
- [x] Reconcile Poloniex exact-order executions with verified cash parents, exact native identities and reported fees.
- [x] Import Poloniex selected-market cash fills with frozen seven-day queries, native pageId checkpoints and one-day incremental overlap.
- [x] Discover Upbit Korea regular open spot orders with resumable numbered pages and reserved-order exclusions.
- [x] Discover Upbit Korea recently created closed orders with durable timestamp splits and explicit saturation limits.
- [x] Recover Upbit Korea regular GTC limits through exact identifier lookup and verified original terms.
- [x] Discover account-wide Bitfinex ordinary cash open orders with explicit margin/flagged-order exclusions.
- [x] Discover Bitfinex recent cash orders through durable creation-time splits and correct historical partial-fill status.
- [x] Recover Bitfinex regular GTC limits by saved int45 cid through complete bounded open/closed checks.
- [x] Reconcile Bitfinex exact-order cash executions with native IDs, signed fee effects and documented ten-day query coverage.
- [x] Import Bitfinex selected-market exchange-wallet fills through frozen 90-day queries, saved timestamp splits and incremental overlap.
- [x] Discover Phemex selected-pair open spot orders with required-pair controls and explicit cash endpoint scope.
- [x] Discover Phemex recent spot orders with fixed creation bounds and saved native offsets.
- [x] Recover Phemex base-sized spot GTC limits through exact clOrdID details and verified original terms.
- [x] Reconcile Phemex exact-order executions with shared UUIDs and verified native value scales.
- [x] Import Phemex selected-pair cash fills through resumable seven-day queries and incremental overlap.
- [x] Import Gate selected-market cash executions with verified native parents and restart-safe numbered pages.
- [x] Import HTX selected-market spot executions through wallet-verified 48-hour windows and durable saturation splits.
- [x] Reconcile Upbit Korea native individual executions without guessing per-fill fees from aggregate paid_fee.
- [x] Import Upbit Korea regular-order executions through saved open/closed listings and execution UUID checkpoints, with older closed-order limits explicit.
- [x] Discover Gemini recent closed spot limits, including unfilled cancellations, with an explicit 500-order saturation limit.
- [x] Discover Crypto.com Exchange regular cash open orders with explicit native execution-flag exclusions.
- [x] Discover Crypto.com Exchange selected-pair recent terminal orders through saved native day ranges and nanosecond saturation splits.
- [x] Recover Crypto.com Exchange ordinary cash GTC limits through exact client_oid details and verified original terms.
- [x] Reconcile Crypto.com Exchange individual cash executions with native trade IDs, parent account proof and signed fee observations.
- [x] Import Crypto.com Exchange selected-market cash history through resumable seven-day queries, one-day overlap and shared exact-order identities.
- [x] Add reviewed Bitfinex cash EXCHANGE MARKET buys/sells with signed base quantities and saved int45 client IDs.
- [x] Add reviewed Phemex ByBase spot IOC market buys/sells without quote-budget substitution.
- [x] Add reviewed Crypto.com Exchange SPOT IOC market buys/sells with native base quantity and client_oid.
- [x] Recover uncertain Bitfinex ordinary cash market submissions by saved cid, native original size and complete bounded open/closed evidence.
- [x] Recover uncertain Phemex base-sized IOC market submissions by exact clOrdID and original baseQtyEv evidence.
- [x] Recover uncertain Crypto.com base-sized cash IOC market submissions by exact client_oid and native original quantity.
- [x] Recover resting Bitstamp spot GTC limits by exact client order ID, with original size and price corroborated by the selected pair’s open-order snapshot.
- [ ] Review MEXC cash market buys and sells with native base quantity, per-pair market support and client-ID recovery. Extend the same review to Gate, Bitget Classic, HTX, CoinEx, BitMart, Poloniex and Upbit where venue sizing matches Trade.
- [ ] Extend Bitstamp recovery to closed and market orders when original terms can be verified. Review recent Bitstamp order-event coverage separately.
- [ ] Extend capped Gemini closed-order history and Upbit older closed-order coverage where native pagination can preserve every order.
- [ ] Extended native order instructions and amendment support, with actual capabilities only.
- [x] Native Binance/Testnet, Coinbase Advanced and Kraken private order signals with persisted reconnect/restart REST wakeups and periodic backstops.
- [ ] Broader private account/balance streams and complete sequence-gap recovery; scheduling is not reconciliation completion.
- [x] Reviewed Binance Spot read weights/observed minute IP ceilings, conservative Kraken private counters and Coinbase Exchange Sandbox buckets; safe native metadata/header evidence, pre-sign deferral, passive diagnostics and native Technician help.
- [ ] Broader quota/tier/profile and endpoint coverage, cross-process coordination and live venue-specific acceptance.

## 3. Strategies

- [x] Account/base-asset strategy exposure caps, sampled rolling-loss windows with persistent latches, and optional stop-distance entry-risk sizing.
- [x] On-demand base-asset balance comparisons, native dust facts, reviewed manual adoption/release and atomic exact-account/pair new-run handoff with original basis, flow-neutral shared P&L and inherited correction guards.
- [x] Flow-adjusted lifetime return estimates, exact-feed historical fee evidence, archive/restore for reconciled flat runs and exact-native-ID provenance for recorded Sibyl manual orders.
- [x] Reviewed and version-bound third-currency fees in exchange strategy budget admission, equity and shared losses. Exact historical rate evidence survives restart and native fee revisions.
- [x] Bounded, explicitly approved liquidation plans reuse the native close pipeline with sequential reconciliation, a fixed sell floor and durable stop/restart behavior.
- [x] Reviewed cost-basis repair across executed ownership descendants, with original receipt quantities, dated cash flows and restart-safe audit history.
- [x] Replay corrected handoff quantities and paired reference cash flows through executed descendants when the corrected units still cover subsequent sales and releases.
- [x] Review and repair underfunded local releases, including zero-unit outcomes and restoration up to their original approved amounts. Show the exact remaining shortfall for venue sales.
- [x] Approve historical funding for reconciled sale shortfalls using asserted basis and origin, preserving native cash/fills, archived receipts and revision guards.
- [x] Link reconciled earlier buys as historical sale funding evidence, including exact venue-discovered orders, proportional basis and bounded aggregate reservations.
- [x] Retain Coinbase Exchange Sandbox settlement observations in the shared fill ledger and require them for further strategy orders and linked funding.
- [x] Import Gemini trade breaks in available spot history and exact-order reads, preserving audit revisions and voiding fully busted fills in accounting.
- [ ] Verify continuous unmanaged custody and placement channels, reconcile Gemini's separate manual adjustments and extend venue settlement/bust coverage.
- [ ] Authenticated partial-fill/cancel races, late corrections and outage recovery across additional venues. See [the exchange acceptance record](exchange-acceptance.md#automated-strategy-acceptance).
- [x] Native optional Optuna TPE/random numeric distributions, causal trusted-plugin validation and one-off pinned research jobs, with bounded trial/test evidence and exact version-pinned replay.
- [x] Multi-asset historical target-allocation studies with exact common inputs, post-cost sizing, interval/drift rebalancing, cost-matched benchmarks, interactive/paged evidence and version/fingerprint-checked offline reruns.
- [ ] Explicitly approved multi-asset paper/exchange execution and coordinated allocation/venue policies.
- [ ] Separate causal ML/RL training/evaluation pipelines and optional Freqtrade integration.

## 4. Agents and messaging

- [x] Optional native durable investigations, human questions, exact local-note approvals, immutable team snapshots and native observed-note reconciliation. Native group continuation/retention gaps are documented.
- [ ] Broader evidence/grounding/adversarial evaluation.
- [x] Opt-in Telegram documents, local photo OCR and bounded speech transcription, retained citations and native specialist routing; external processors are optional and their live accuracy remains an acceptance check.
- [x] Discord private HTTP DMs, Slack Socket Mode and local Signal bridge clients with checked recipient binding, encrypted setup, durable inbox/outbox and native ProtoLink requests.
- [x] Signed WhatsApp Cloud API webhooks and paired TLS IMAP/SMTP email clients using the shared private inbox/outbox.
- [x] Six-channel private alert delivery through checked native clients, future-only policies, shared durable receipts, cancellation uncertainty and exact provider IDs.
- [x] Six-channel scheduled briefings with one checked recipient, acceptance-time route controls, version-scoped withdrawal, native source/privacy projections and shared message review.
- [ ] Additional media beyond Telegram and live external-service/processor acceptance.

## 5. Research and forecasting

- [x] Forecast drift monitoring and explicit retained-source candidate recalibration policies, with native Chronos evidence and opt-in local schedules.
- [x] Add trained fixed-scale Huber autoregression, validated delta, training diagnostics and existing chronological/rolling/portable/recalibration workflows.
- [x] Native statsmodels nonseasonal ARIMA(p,1,q) with explicit bounded orders, training-only scaling/fit, fixed-context causal filtering, real diagnostics and existing rolling/portable/recalibration contracts.
- [x] Optional weekly native SARIMA with a seven-day autoregressive term, held-out and rolling evidence, recipe-preserving reruns and portable refits.
- [ ] Additional neural/model families, other seasonal orders, exogenous inputs and larger real-market validation.
- [x] Optional OpenAI/Mistral embeddings through native ProtoLink OpenAIEmbedder, independent encrypted keys, explicit hosted-text permission, checked response identity and revision-fenced indexing/evaluation.
- [x] Owner-labeled semantic cutoff experiments with separate fit/validation questions, exact corpus/index bindings, reviewed activation, top-one abstention, stale/concurrent-change fencing and native read-only quality evidence.
- [ ] Additional hosted providers, live provider/model relevance/grounding and forward-quality acceptance, and evaluated finance/entity sentiment.
- [ ] Licensed article ingestion and configurable research integrations.
- [x] Durable Bitcoin output watches with spend and inclusion change evidence, private inbox/export, bounded retry and restore quarantine.
- [x] Optional same-sample Theil–Sen versus OLS return comparison with scatter and native Analyst evidence.
- [x] Historical Bitcoin block lookup with hash-pinned transaction pages, indexer chain status, transaction drill-down and native Explorer evidence.
- [x] Complete local Bitcoin Explorer scope with transaction-inclusion verification against the selected block header.
- [ ] Additional chains, bulk historical datasets, independent chain validation, disclosure archives and interpretable advanced analytics.

## 6. Operations and distribution

- [x] Durable local job scheduling with cancellation, restart semantics and native domain integration.
- [x] Retained sampled worker incidents with an independent local observer, confirmed progress recovery, unresolved restart boundaries, observation gaps and local inbox notices.
- [ ] Broader cross-request tracing, diagnostics and external process/host outage monitoring.
- [x] Audited credential/key rotation with safe recovery.
- [x] Additional private alert delivery routes through the existing Discord, Slack, Signal, WhatsApp and email clients.
- [x] Native launchd/systemd-user/Windows Task Scheduler CLI management with preview, ownership-protected definitions, loopback/port checks, private rotating logs and read-only UI/Technician status.
- [ ] Broader real OS login/logout/upgrade acceptance and additional installers; generic outbound webhooks and native push remain optional expansions.
- [ ] Release/registry/signing and live external-service acceptance where access is available.

## Completion rules

Every delivered capability needs domain code, HTTP/UI where relevant, tests, native agent guidance, user/developer docs and a changelog entry. Credentials stay in the local encrypted vault. Existing execution permissions remain in force; no real-money orders are placed as implementation tests. A provider response timeout must not cause an automatic duplicate write. A code adapter does not establish production acceptance, licence rights, signing or publication.
