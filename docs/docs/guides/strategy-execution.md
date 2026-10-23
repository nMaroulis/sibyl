# Exchange strategy execution

Strategies supports isolated paper runs and explicitly approved exchange runs. Exchange execution is implemented for **Binance, Binance.US, Binance Testnet, Coinbase Advanced Trade, Coinbase Exchange Sandbox, Kraken, OKX, Bybit and KuCoin**. Other providers remain unavailable for automation until native execution imports and submission are implemented. Adapter tests do not replace authenticated provider acceptance.

## Start a run

1. Connect and activate an account in **Settings → Exchanges**. Use spot trading and order/fill read permissions. Keep withdrawals and transfers disabled. Prefer an exchange test environment for acceptance testing.
2. Enable both `SIBYL_ALLOW_LIVE_TRADING=true` and `SIBYL_ALLOW_STRATEGY_EXECUTION=true` on the Python backend and restart it. Both default to false; test environments also require them. Agents cannot change these flags or approve execution.
3. In **Strategies → Build & backtest**, choose the algorithm and indicator/risk-exit settings. Expand **Run on a connected exchange**. Choose an account, its exact spot pair and execution timeframe. The execution exchange supplies its own candles and order book; the research feed and Demo input are never used for real exchange execution.
4. Set an allocated budget in the pair's **quote asset**, an order cap and a loss-pause threshold. Choose **Cancel unfilled orders after**: one minute to one day, or GTC with no automatic expiry. The UI starts at five minutes; the approval explicitly includes this policy. Expand execution limits for rolling 24-hour order count, spread, limit-price allowance and fee reserve. Native quote budgets can be fractional, including BTC/ETH quote assets.
5. Select **Review exchange strategy**. This reads balances and market evidence without placing an order. Check the account, test/production badge, pair, budget and limits. Type the displayed confirmation and approve the two-minute review. One review creates one run, including when the start request is repeated.

Approval allows future orders within that fixed scope without reviewing each order. The run primes the current closed candle and waits for the next one; it does not immediately trade an old signal. An AI model is not needed. Broker can explain the run's evidence but cannot approve or submit orders.

## Execution and risk controls

Every decision uses the latest closed candle from the exact exchange pair. Missing, stale or discontinuous data block execution. Fresh two-sided order-book reads determine a reference midpoint and spread. A native book timestamp is validated when provided; otherwise freshness is the local request observation, not a guarantee about the venue's internal book age.

Signals create **price-capped GTC limit orders**, with rounded-down base quantities, exact venue precision and minimum/maximum checks. Buy limits are bounded above the observed ask; sell limits are bounded below the observed bid by the approved price allowance. A limit can remain unfilled. There is one pending order per run; open, partially filled, uncertain or incompletely reconciled orders block any further order. Manage individual orders in **Trade → Executions**, which identifies strategy orders and links back to their monitor.

## Order lifetime and cancellation

An approved lifetime starts when the shared pipeline commits its submission attempt. The deadline persists before the native write, including when its response is lost. At expiry, the backend reads the exact native order and uses the shared cancellation pipeline once. This is **best-effort local policy**, not native time-in-force: the backend must be running, the account must be active, and both execution flags must permit automatic expiry writes. The strategy worker normally checks every 30 seconds; outages, provider limits and errors can delay cancellation. A partial fill remains owned; only the unfilled remainder can be canceled.

The approved policy continues while the run is paused, stopped or awaiting explicit Resume after restart. Existing jobs and API requests with no `risk.order_lifetime_seconds` have **no automatic expiry**; they gain no new cancellation authority. API clients may explicitly choose `null` or an integer from 60 through 86,400 seconds.

**Stop & cancel orders** is a separate monitor action with a two-minute typed review. It permanently stops future submissions before queuing this run's outstanding orders. An in-flight submission can finish before Stop commits and is included. Prepared, unsubmitted intents are abandoned. This action requires the live-trading flag and active account access for cancellation; the strategy-submission flag can be off. Stop still commits if cancellation is blocked, with progress visible in the monitor. Neither this action nor expiry sells holdings.

Cancellation requests and unknown outcomes are not confirmation. A durable attempt is never automatically resent, including after process loss or a prior manual cancellation. Native reads continue when order-writing flags are disabled, provided the saved account remains active and accessible. If the native order remains open, inspect it in Trade and make a fresh manual cancellation review if appropriate. No replacement is submitted automatically.

The monitor shows the deadline, cancellation state, native outcome and reconciliation progress. Confirmed terminal orders receive three bounded follow-up native status reads (next due worker pass, then approximately +60 and +240 seconds) to catch a fill that raced cancellation. Shared native fill imports continue independently. A current match is not final settlement; later corrections can change retained ownership. Cancellation transitions appear in the journal and CSV.

The quote budget is local accounting, **not a reservation or a separate exchange wallet**. Existing account holdings are not adopted. Buy sizes fit the remaining allocated cash and order cap, with the selected fee reserve. Sell sizes use only strategy-owned base units, leaving a reserve for possible base-asset fees. Precision/fee residuals remain owned and valued; a residual below native order minimums is labeled dust and can accompany a later entry. Unrelated manual activity and other bots can consume available account funds; use a dedicated account/subaccount when available. Creation checks the free quote balance against other active/paused strategy cash allocations. Another retained run cannot own the same account/pair.

The order cap excludes actual fees. The loss threshold compares allocated cash plus the owned position at the latest observed midpoint against the original budget. Reaching it permanently latches a pause for that approval. Spread, stale evidence, insufficient funds, incomplete fees and a rolling 24-hour order limit block new submissions. These controls do not guarantee a maximum loss and do not cancel an existing order or liquidate holdings. Stop-loss/take-profit signals are close-based software decisions, not native protective orders. The backtest's `max_trades` setting counts **completed exit orders** in exchange mode, including partial position reductions; paper/backtest runs count round trips.

## Real accounting and recovery

Acknowledgments and cumulative order quantities do not credit the strategy with a position. The shared order reconciliation worker imports native fill IDs and fees into the account ledger. Strategy ownership is rebuilt from the fills of its linked orders only. Duplicate reads do not duplicate balances, and later corrections recompute cash, base units, weighted cost basis and realized P&L.

Base fees reduce owned units and quote fees reduce allocated cash. Fees in another currency remain visible in their native units and **pause further orders**; no conversion is invented. Unknown costs/fees also block new orders. The monitor reports allocated equity at the last observed exchange midpoint and completed-exit returns on disposed cost basis. It is not whole-account exchange P&L. Retained chart observations are historical observations and are not rewritten when late fees arrive. Accounting is bounded to 10,000 native fills per run; exceeding that limit requires review and a new run.

The order plan and deterministic request key are saved before order preparation. The shared order pipeline persists a client order ID and `submitting` state before its single native write. Timeouts never trigger a resubmission. Binance/Binance.US/Testnet, Coinbase Advanced/Sandbox and Kraken have implemented client-ID recovery. Other execution providers require venue inspection for an uncertain submission; without reconciled identity/evidence the strategy cannot resume.

**Backend startup pauses all running exchange strategies.** Existing order reads, native fill imports and approved expiry/cancellation policies can continue. Explicit Resume requires active account access, resolved order evidence and valued base/quote fees, then primes the current candle; missed signals are not replayed. An unsubmitted plan is abandoned rather than retried. Pause/Stop serialize with local submission, so an in-flight native write may finish before the control returns. A stopped run is terminal, but native orders can still fill and imported executions continue updating its retained ownership. Ordinary Pause/Stop request no immediate cancellation; approved expiry still applies. Use the separate **Stop & cancel orders** review for immediate cleanup. Holdings remain tracked and are never flattened by these controls.

## Close a retained position

**Close position** in the monitor is a separate one-order sell approval. It is implemented for the same nine execution provider/environment variants. It never restarts the strategy or adopts unrelated account holdings.

1. Permanently stop submissions. Use **Stop & cancel orders** if orders remain open, then resolve any uncertain native identity in Trade. Wait for matching fills/fees and all three cancellation follow-up checks. The closing dialog explains readiness and refreshes it every five seconds.
2. Choose an exit lifetime (five minutes initially, or GTC with no local expiry). Advanced options set the sell-price allowance below the current bid, maximum spread and conservative base-fee reserve. **Review exit order** reads a fresh native book, precision/limits and free base balance; it places no order and requires no candle history.
3. Check the account/environment, owned units, exact sell quantity, limit floor, proceeds at that floor before fees, base-fee reserve and estimated residual. The review lasts 60 seconds. Type the displayed `CLOSE TEST/LIVE …` phrase and select **Approve & submit sell**.
4. Follow the **Reviewed position exit** state and its tagged **Exit** order in the monitor. Acknowledgments do not reduce ownership. Native fills update cash, retained units, weighted cost basis and realized P&L; later fee corrections recompute them. The chart's retained observations and last midpoint valuation are not rewritten.

The sell quantity is capped by reconciled strategy ownership, the base-fee reserve, native amount/cost maxima and the shared quantity bound. It is **not guaranteed to flatten the position**: base fees, precision, native caps or a partial/canceled fill can leave units. They remain visible, including tradable residuals and dust. Each further sell requires a fresh review; no replacement or multi-order liquidation is automatic. Native fees are unknown until reported. A quote-fee allowance is illustrative, not a fee quote or guaranteed net proceeds.

Residual ownership keeps the account/pair assigned to this retained run, so it can block a new strategy on that same account/pair. Dust below native minimums cannot currently be sold. A reviewed handoff/release of residual ownership to a new run is still pending; the app does not silently discard or adopt those units.

This explicit exit approval has its own limits. It can exceed the original automated entry-order value cap and is available with a latched loss guard or strategy-submission permission off; `SIBYL_ALLOW_LIVE_TRADING=true` and active account access are still required. Ownership, account/environment, flags and review expiry are rechecked immediately before committing the shared `submitting` boundary. A ledger change invalidates the review. Unrelated manual account activity can still consume funds; the exchange has the final balance/permission check.

Closing reviews never execute by themselves. Repeated confirmations return retained progress and never send another native write. After process loss an unsubmitted prepared exit is abandoned; a submitted or uncertain one only rejoins status/recovery/fill reads. The earlier Stop & cancel approval **does not cancel a later closing order**. Its separately approved expiry can cancel its remainder, with active account access and live-order permission, even while strategy-submission permission is off. Ordinary expiry timing/uncertainty limitations still apply. Manual cancellation remains available in Trade.

Readiness and a current reconciliation match do not establish final settlement. Later fills, fee changes, exchange busts and manual account changes can require further inspection; no finality is invented.

## Pending

Authenticated sandbox/production acceptance, automatic multi-order liquidation, adoption/reconciliation of manually changed positions, third-currency fee valuation, full settlement/bust handling, global kill controls, portfolio-wide exposure/daily-loss policies and additional providers remain on the [implementation checklist](../developers/backend-roadmap.md). Current residual exits require fresh approvals. Do not interpret a supported adapter badge as successful private-account verification.

The code is in `src/sibyl/strategies/execution/`: `contracts.py`, `approvals.py`, `venue.py`, `accounting.py`, `cancellation.py`, `stop_reviews.py`, `closing.py` and `runner.py`. Cancellation progress lives on each owned order intent; the persisted stop policy and deadlines reconstruct work after restart. Closing reviews persist separately; their deterministic request keys and linked intents protect duplicate confirmations. A domain guard compares a coherent ownership digest within the shared submission transaction. Host locks precede per-intent locks, matching the submission pipeline. Equal native fill timestamps use local order creation order as the causal tiebreaker for this serialized strategy. It reuses `ExchangeTrading`, order recovery and native fill reconciliation rather than introducing another exchange client. Native limit-order reference: [Binance Spot trading API](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/trading-endpoints).

| Method | `/api/v1` path | Purpose |
| --- | --- | --- |
| GET | `/strategies/exchange/options` | Implemented providers, account activation and execution flags |
| GET | `/strategies/exchange/markets/{account_id}` | Exact spot pairs and available timeframes |
| POST | `/strategies/exchange/preview` | Read-only, expiring account/budget review |
| POST | `/strategies/exchange/reviews/{id}/start` | Typed approval of the immutable review |
| GET | `/strategies/jobs/{id}` | Retained observations, native fill markers, orders and policy |
| POST | `/strategies/jobs/{id}/pause`, `/resume`, `/stop` | Run controls; no immediate cancellation or liquidation; approved expiry continues |
| POST | `/strategies/exchange/jobs/{id}/stop-cancel-review` | Read local fixed-run scope; no exchange call or state change |
| POST | `/strategies/exchange/stop-reviews/{id}/confirm` | Typed approval; stop submissions and persist the cancellation queue |
| GET | `/strategies/exchange/jobs/{id}/close-position` | Local readiness/blockers, owned units and retained exit state |
| POST | `/strategies/exchange/jobs/{id}/close-preview` | Fresh native reads and 60-second fixed sell review; no native write |
| POST | `/strategies/exchange/close-reviews/{id}/confirm` | Typed approval of one strategy-owned sell; never replayed |
