# Strategy ownership reviews

`strategies/execution/ownership/` separates strict native observations (`inspection.py`), typed consent (`contracts.py`), immutable evidence receipts (`ledger.py`) and review coordination (`service.py`). No agent/runtime abstraction or exchange sender is introduced.

## HTTP contract

All routes below are under `/api/v1/strategies/exchange` and return `Cache-Control: no-store`.

| Route                                  | Behavior                                                                                                                  |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `GET /jobs/{id}/ownership`             | Local receipts and last explicit position check; no provider read.                                                        |
| `POST /jobs/{id}/ownership/check`      | On-demand exact-account balance/book/minimum observation.                                                                 |
| `POST /jobs/{id}/ownership/preview`    | Fresh 60-second adoption/release review: action, positive base quantity, total cost basis for adoption only, and reason.  |
| `POST /ownership-reviews/{id}/confirm` | Exact typed confirmation with fresh native facts and SQLite evidence recheck; duplicate confirmation returns saved state. |

The existing strategy preview accepts optional `handoff_from`. It reviews a terminal, settled source on the exact account/environment/pair. Start atomically creates the successor, paired source/target receipts and the review acknowledgment. No cash is moved; the new budget is additional quote allocation. Competing or stale source reviews cannot duplicate units. Shared capital review accounts for retiring the source’s retained allocation and adding the successor’s budget plus reference value.

## Replay and concurrency

Receipts have signed units, signed cost basis, signed reference capital flow, source/target IDs, reason and immutable evidence pins. A receipt is applied after its recorded preceding fill IDs, rather than trusting provider wall-clock ordering against application time. Handoff carries inherited native evidence pins so source corrections invalidate descendants. Pins include prior order identities/economic observations and fee/cost fill facts, not later new orders or changing sync timestamps. They contain no credentials.

A source/correction mismatch marks accounting incomplete and prevents signal/exit approval. Old receipts are not silently rewritten; reviewed repair across executed descendants is pending. Immutable local receipts do not establish final venue settlement.

Review commits serialize with strategy controls through the runner lock and recheck all same-account base owners, account credential generation and native fill evidence under `BEGIN IMMEDIATE`. Confirmation re-reads total/free balances and the book, refuses balance changes or a reference-price shift above 0.5%, and expires after 60 seconds. Observation work is bounded to 30 seconds and 100 runs per account; each run allows up to 100 immutable ownership receipts; native fill replay retains its existing 10,000-fill limit.

Adoption uses `min(unassigned total, free)`; missing/invalid native balances stay unknown. Release carries proportional basis without sale proceeds. Cash is never invented by either action. Net reference flows adjust marked/shared P&L and the allocated-loss baseline; incoming reference value joins shared capital and exposure. Lifetime return/risk statistics are explicitly unavailable after a changed capital base. Native position exits retain their separate permission/approval contract.

Attributed runs verify aggregate base backing at Resume, evaluation and final signal admission; the latter checks a freshly read balance against the current ledger inside the native-write transaction. A separately reviewed exit checks backing before submission. No account read can prevent an external trade after the observation.

## Native agent integration and acceptance

Broker’s ordinary typed `position_ownership` tool reads the local projection. Native ProtoLink registration, request dependencies, streaming and evidence remain unchanged. The system prompt and `strategy_help(topic="ownership")` distinguish user assertions, local custody changes, native execution and incomplete history. Agents receive no mutation tool.

Controlled venue tests cover adoption/release replay, actual linked sell fills, original-basis handoff, cross-pair base reservation, native dust limits, stale credentials/fills, inherited corrections, duplicate/concurrent confirmation, restart, flow-neutral shared risk and HTTP privacy. These tests perform no real orders and do not claim authenticated venue acceptance.
