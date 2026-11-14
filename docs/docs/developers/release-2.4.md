# v2.4.0 implementation plan

This release is being implemented in six dependency-ordered batches. Entries below are engineering work, not a claim of authenticated acceptance. Provider-specific limitations remain in the capability inventory. Multi-user hosting and cited web research remain deferred.

## 1. Accounting and reconciliation

- [x] Account/asset FIFO across trading pairs, historical reporting-currency conversion and third-currency fees/rebates, with unknown-basis and ordering evidence.
- [x] Audited fill correction history, source revisions and atomic ledger/checkpoint behavior.
- [x] Reviewed asset openings, existing documented/reviewed funding effects and cross-market one-to-one transfer lot carryover with immutable evidence.
- [x] Audited split/merged transfer groups with exact principal matrices, pair/group reservation conflicts, current source/review checks and whole-group cross-pair FIFO carryover.
- [ ] Additional fee conventions and independently verified external-flow classifications.
- [x] Bybit same-UID UNIFIED wallet transfer history with native pagination, local revision evidence and optional background checks.
- [ ] Wider funding/history adapters and account balance reconciliation.

## 2. Exchange infrastructure

- [x] Reviewed manual GTC limit/cancel adapters for the eleven remaining configured production providers, with captured native request contracts.
- [ ] Broader market execution, discovery/recovery and historical pagination adapters.
- [ ] Extended native order instructions and amendment support, with actual capabilities only.
- [x] Native Binance/Testnet, Coinbase Advanced and Kraken private order signals with persisted reconnect/restart REST wakeups and periodic backstops.
- [ ] Broader private account/balance streams and complete sequence-gap recovery; scheduling is not reconciliation completion.
- [x] Reviewed Binance Spot read weights/observed minute IP ceilings, conservative Kraken private counters and Coinbase Exchange Sandbox buckets; safe native metadata/header evidence, pre-sign deferral, passive diagnostics and native Technician help.
- [ ] Broader quota/tier/profile and endpoint coverage, cross-process coordination and live venue-specific acceptance.

## 3. Strategies

- [x] Account/base-asset strategy exposure caps, sampled rolling-loss windows with persistent latches, and optional stop-distance entry-risk sizing.
- [x] On-demand base-asset balance comparisons, native dust facts, reviewed manual adoption/release and atomic exact-account/pair new-run handoff with original basis, flow-neutral shared P&L and inherited correction guards.
- [ ] Reviewed repair/reversal across executed ownership descendants, verified manual-trade classifications and cash-flow-adjusted lifetime return statistics.
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
- [ ] Additional chains, historical datasets, local chain verification, disclosure archives and interpretable advanced analytics.

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
