# v2.4.0 implementation plan

This release is being implemented in six dependency-ordered batches. Entries below are engineering work, not a claim of authenticated acceptance. Provider-specific limitations remain in the capability inventory. Multi-user hosting and cited web research remain deferred.

## 1. Accounting and reconciliation

- [x] Account/asset FIFO across trading pairs, historical reporting-currency conversion and third-currency fees/rebates, with unknown-basis and ordering evidence.
- [x] Audited fill correction history, source revisions and atomic ledger/checkpoint behavior.
- [x] Reviewed asset openings, existing documented/reviewed funding effects and cross-market one-to-one transfer lot carryover with immutable evidence.
- [x] Audited split/merged transfer groups with exact principal matrices, pair/group reservation conflicts, current source/review checks and whole-group cross-pair FIFO carryover.
- [ ] Additional fee conventions and independently verified external-flow classifications.
- [ ] Wider funding/history adapters and account balance reconciliation.

## 2. Exchange infrastructure

- [x] Reviewed manual GTC limit/cancel adapters for the eleven remaining configured production providers, with captured native request contracts.
- [ ] Broader market execution, discovery/recovery and historical pagination adapters.
- [ ] Extended native order instructions and amendment support, with actual capabilities only.
- [x] Native Binance/Testnet, Coinbase Advanced and Kraken private order signals with persisted reconnect/restart REST wakeups and periodic backstops.
- [ ] Broader private account/balance streams and complete sequence-gap recovery; scheduling is not reconciliation completion.
- [ ] Provider quota policies, read diagnostics and venue-specific acceptance tools.

## 3. Strategies

- [x] Account/base-asset strategy exposure caps, sampled rolling-loss windows with persistent latches, and optional stop-distance entry-risk sizing.
- [x] On-demand base-asset balance comparisons, native dust facts, reviewed manual adoption/release and atomic exact-account/pair new-run handoff with original basis, flow-neutral shared P&L and inherited correction guards.
- [ ] Reviewed repair/reversal across executed ownership descendants, verified manual-trade classifications and cash-flow-adjusted lifetime return statistics.
- [x] Native optional Optuna TPE/random numeric distributions, causal trusted-plugin validation and one-off pinned research jobs, with bounded trial/test evidence and exact version-pinned replay.
- [ ] Multi-asset historical deployment/rebalancing and explicitly approved execution.
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
- [ ] Additional trained model families.
- [ ] Hosted embedding providers, calibrated retrieval abstention and evaluated finance/entity sentiment.
- [ ] Licensed article ingestion and configurable research integrations.
- [ ] Additional chain/history/watch support, disclosure archives and interpretable advanced analytics.

## 6. Operations and distribution

- [x] Durable local job scheduling with cancellation, restart semantics and native domain integration.
- [x] Retained sampled worker incidents with an independent local observer, confirmed progress recovery, unresolved restart boundaries, observation gaps and local inbox notices.
- [ ] Broader cross-request tracing, diagnostics and external process/host outage monitoring.
- [x] Audited credential/key rotation with safe recovery.
- [x] Additional private alert delivery routes through the existing Discord, Slack, Signal, WhatsApp and email clients.
- [ ] Additional installation/service support; generic outbound webhooks and native push are optional expansions.
- [ ] Release/registry/signing and live external-service acceptance where access is available.

## Completion rules

Every delivered capability needs domain code, HTTP/UI where relevant, tests, native agent guidance, user/developer docs and a changelog entry. Credentials stay in the local encrypted vault. Existing execution permissions remain in force; no real-money orders are placed as implementation tests. A provider response timeout must not cause an automatic duplicate write. A code adapter does not establish production acceptance, licence rights, signing or publication.
