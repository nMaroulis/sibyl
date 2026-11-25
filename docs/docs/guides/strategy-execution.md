# Exchange strategy execution

Strategies supports isolated paper runs and explicitly approved exchange runs. Exchange execution is implemented for **Binance, Binance.US, Binance Testnet, Coinbase Advanced Trade, Coinbase Exchange Sandbox, Kraken, OKX, Bybit and KuCoin**. Other providers remain unavailable for automation until native execution imports and submission are implemented. Adapter tests do not replace authenticated provider acceptance.

## Start a run

1. Connect and activate an account in **Settings → Exchanges**. Use spot trading and order/fill read permissions. Keep withdrawals and transfers disabled. Prefer an exchange test environment for acceptance testing.
2. Turn on **Exchange strategy execution** in **Settings → Workspace**. Production and test accounts both use this permission. Changes take effect immediately and are saved locally.
3. In **Strategies → Build & backtest**, choose an algorithm card, then select **Run on an exchange**. The **Exchange account** field groups production and test connections. Choose its exact spot pair and timeframe. Expand **Algorithm settings** to edit the signal and exit parameters. The execution exchange supplies its own candles and order book; the research feed and Demo input are never used for real exchange execution.
4. Set an allocated budget in the pair's **quote asset**, an order cap and a loss-pause threshold. Choose **Cancel unfilled orders after**: one minute to one day, or GTC with no automatic expiry. The UI starts at five minutes; the approval explicitly includes this policy. Open **Advanced execution** for rolling 24-hour order count, spread, limit-price allowance and fee reserve. Native quote budgets can be fractional, including BTC/ETH quote assets.
5. Select **Review exchange strategy**. This reads balances and market evidence without placing an order. Check the account, test/production badge, pair, budget and limits. Type the displayed confirmation and approve the two-minute review. One review creates one run, including when the start request is repeated.

Approval allows future orders within that fixed scope without reviewing each order. The run primes the current closed candle and waits for the next one; it does not immediately trade an old signal. An AI model is not needed. Broker can explain the run's evidence but cannot approve or submit orders.

## Halt automation across accounts

The **Exchange automation** control above the workspace is available in both Build & backtest and Monitor. Select **Halt automation** to pause every running exchange strategy and block new automatic entries/exits across all accounts, including exchange test environments. The halt persists after backend restart and works even when exchange access is unavailable. Paper strategies and backtests continue normally.

Wait for the active-halt confirmation. A request can wait for an already admitted provider operation, and an in-flight order may finish before the action returns. The halt does not cancel orders or sell holdings. Existing orders can still fill; native reconciliation, approved order-expiry policies, manual Trade and separately reviewed position exits/cancellations keep their existing permissions.

Open **Review & release** to inspect the control history and type `RELEASE STRATEGY HALT`. Releasing leaves every run paused. Review each run's orders, fills and current ownership, then Resume individually. The normal account, loss, reconciliation and fresh-candle checks still apply. Old unused Start reviews and unsent signal orders remain invalid; create a fresh review when starting a new run.

**Controls** shows the newest 20 changes, their notes, exact paused-run links and timestamps. The backend retains the newest 200 changes, and each affected run keeps its own journal pause event. Agents can explain this state but cannot change it. This manual submission control is independent of the opt-in [portfolio limits](portfolio-limits.md), which enforce shared capital/exposure and observed daily-loss policies separately for production/test funds. See the [developer contract](../developers/strategy-controls.md).

## Execution and risk controls

Every decision uses the latest closed candle from the exact exchange pair. Missing, stale or discontinuous data block execution. Fresh two-sided order-book reads determine a reference midpoint and spread. A native book timestamp is validated when provided; otherwise freshness is the local request observation, not a guarantee about the venue's internal book age.

Signals create **price-capped GTC limit orders**, with rounded-down base quantities, exact venue precision and minimum/maximum checks. Buy limits are bounded above the observed ask; sell limits are bounded below the observed bid by the approved price allowance. A limit can remain unfilled. There is one pending order per run; open, partially filled, uncertain or incompletely reconciled orders block any further order. Manage individual orders in **Trade → Executions**, which identifies strategy orders and links back to their monitor.

## Order lifetime and cancellation

An approved lifetime starts when the shared pipeline commits its submission attempt. The deadline persists before the native write, including when its response is lost. At expiry, the backend reads the exact native order and uses the shared cancellation pipeline once. This is **best-effort local policy**, not native time-in-force: the backend must be running, the account must be active, and Exchange strategy execution must permit automatic expiry writes. The strategy worker normally checks every 30 seconds; outages, provider limits and errors can delay cancellation. A partial fill remains owned; only the unfilled remainder can be canceled.

The approved policy continues while the run is paused, stopped or awaiting explicit Resume after restart. Existing jobs and API requests with no `risk.order_lifetime_seconds` have **no automatic expiry**; they gain no new cancellation authority. API clients may explicitly choose `null` or an integer from 60 through 86,400 seconds.

**Stop & cancel orders** is a separate monitor action with a two-minute typed review. It permanently stops future submissions before queuing this run's outstanding orders. An in-flight submission can finish before Stop commits and is included. Prepared, unsubmitted intents are abandoned. This action requires the live-trading flag and active account access for cancellation; the strategy-submission flag can be off. Stop still commits if cancellation is blocked, with progress visible in the monitor. Neither this action nor expiry sells holdings.

Cancellation requests and unknown outcomes are not confirmation. A durable attempt is never automatically resent, including after process loss or a prior manual cancellation. Native reads continue when order-writing flags are disabled, provided the saved account remains active and accessible. If the native order remains open, inspect it in Trade and make a fresh manual cancellation review if appropriate. No replacement is submitted automatically.

The monitor shows the deadline, cancellation state, native outcome and reconciliation progress. Confirmed terminal orders require **three matching status checks** (next due worker pass, then approximately +60 and +240 seconds). A check counts only when native totals agree with complete retained fills and fees. Mismatched totals do not consume those checks. If the native outcome/totals or imported fills/fees change, the count restarts against the new evidence, including after restart. Reimporting identical executions leaves the count alone.

While these checks are incomplete, a running strategy shows **waiting cancellation** and submits no new signal order; a separately reviewed exit also remains blocked. The submission transaction checks the evidence again, so a correction arriving after a quote was prepared can still refuse that order. Account-history imports and exact-order reconciliation share this behavior. Shared native fill imports continue independently. A current match is not final settlement: bounded follow-ups cannot discover every future venue correction. Cancellation transitions appear in the journal and CSV.

For Coinbase Exchange Sandbox, a filled terminal order also needs venue-reported settlement on every fill before another strategy order can proceed. The monitor points to **Trade → Executions** for on-demand checks. Changes to settlement also reopen checks for previously reconciled cancellations and block reuse of affected historical funding. Unfilled terminal orders need no settlement report.

The quote budget is local accounting, **not a reservation or a separate exchange wallet**. Existing account holdings are not adopted automatically; [reviewed ownership](strategy-ownership.md) can attribute them explicitly. Buy sizes fit the remaining allocated cash and order cap, with the selected fee reserve. Sell sizes use only strategy-owned base units, leaving a reserve for possible base-asset fees. Precision/fee residuals remain owned and valued; a residual below native order minimums is labeled dust and can accompany a later entry. Unrelated manual activity and other bots can consume available account funds; use a dedicated account/subaccount when available. Creation checks the free quote balance against other active/paused strategy cash allocations. Another retained run cannot own the same account/pair.

The order cap excludes actual fees. The loss threshold compares allocated cash plus the owned position at the latest observed midpoint, less approved other-asset fees, against the original budget plus net reviewed ownership reference flows. Reaching it permanently latches a pause for that approval. Spread, stale evidence, insufficient funds, incomplete fees and a rolling 24-hour order limit block new submissions. These controls do not guarantee a maximum loss and do not cancel an existing order or liquidate holdings. Stop-loss/take-profit signals are close-based software decisions, not native protective orders. The backtest's `max_trades` setting counts **completed exit orders** in exchange mode, including partial position reductions; paper/backtest runs count round trips.

## Real accounting and recovery

Acknowledgments and cumulative order quantities do not credit the strategy with a position. The shared order reconciliation worker imports native fill IDs and fees into the account ledger. Strategy ownership is rebuilt from the fills of its linked orders and separately reviewed [ownership receipts](strategy-ownership.md). Duplicate reads do not duplicate balances, and later corrections recompute cash, base units, weighted cost basis and realized P&L.

Base fees reduce owned units and quote fees reduce allocated cash. Fees charged in another asset stay visible in their native units. Missing costs, missing fees and other-asset fees without [approved historical prices](#review-fees-charged-in-another-asset) pause further orders. The monitor reports allocated equity at the last observed exchange midpoint and completed-exit returns on disposed cost basis. It is not whole-account exchange P&L. Retained chart observations are historical observations and are not rewritten when late fees arrive. Accounting is bounded to 10,000 native fills per run; exceeding that limit requires review and a new run.

The order plan and deterministic request key are saved before order preparation. The shared order pipeline persists a client order ID and `submitting` state before its single native write. Timeouts never trigger a resubmission. Binance/Binance.US/Testnet, Coinbase Advanced/Sandbox and Kraken have implemented client-ID recovery. Other execution providers require venue inspection for an uncertain submission; without reconciled identity/evidence the strategy cannot resume.

**Backend startup pauses all running exchange strategies.** Existing order reads, native fill imports and approved expiry/cancellation policies can continue. Explicit Resume requires active account access, resolved order evidence and complete native fees, including approved historical prices for any other-asset fees, then primes the current candle; missed signals are not replayed. An unsubmitted plan is abandoned rather than retried. Pause/Stop serialize with local submission, so an in-flight native write may finish before the control returns. A stopped run is terminal, but native orders can still fill and imported executions continue updating its retained ownership. Ordinary Pause/Stop request no immediate cancellation; approved expiry still applies. Use the separate **Stop & cancel orders** review for immediate cleanup. Holdings remain tracked and are never flattened by these controls.

## Review fees charged in another asset

For a fee charged in a third asset, such as BNB on a BTC/USDT fill, open **Lifetime performance → Review fee prices**. First pause the run and reconcile its native orders and any outstanding cancellation checks. Sibyl lists the signed fee or rebate, its fill time and each historical conversion leg. When a price is missing, import candles through **Markets → Candle history** using the run’s connected account and environment. A conversion uses up to three observed legs with closed candles no newer than the fill and no more than 24 hours old.

Approve the displayed batch of up to 25 fills. Sibyl checks the current fee facts and price evidence again before saving. The **Decision journal → Approved fee prices** filter shows each immutable receipt, even after a native revision. Revised fee amounts need a new review. Later candle backfills leave approved marks in place.

Approved prices affect marked equity and strategy loss limits. Positive charges reserve quote budget for new entries. Rebates improve marked P&L without increasing quote buying power. Native quote cash and acquisition or disposal basis stay tied to actual fills. Review and Resume remain separate actions.

## Turn off exchange automation

Switch off **Exchange strategy execution** in Workspace to pause running exchange strategies and end active liquidation plans. Orders already sent to an exchange stay there until filled or cancelled. Inspect or cancel open orders in Trade. Turn the switch back on and explicitly resume each paused run. Merely enabling the switch leaves the global halt and portfolio risk controls in place.

## Close a retained position

**Close position** in the monitor is a separate one-order sell approval. It is implemented for the same nine execution provider/environment variants. It never restarts the strategy or adopts unrelated account holdings.

1. Permanently stop submissions. Use **Stop & cancel orders** if orders remain open, then resolve any uncertain native identity in Trade. Wait for matching fills/fees and all three cancellation follow-up checks. The closing dialog explains readiness and refreshes it every five seconds.
2. Choose an exit lifetime (five minutes initially, or GTC with no local expiry). Advanced options set the sell-price allowance below the current bid, maximum spread and conservative base-fee reserve. **Review exit order** reads a fresh native book, precision/limits and free base balance; it places no order and requires no candle history.
3. Check the account/environment, owned units, exact sell quantity, limit floor, proceeds at that floor before fees, base-fee reserve and estimated residual. The review lasts 60 seconds. Type the displayed `CLOSE TEST/LIVE …` phrase and select **Approve & submit sell**.
4. Follow the **Reviewed position exit** state and its tagged **Exit** order in the monitor. Acknowledgments do not reduce ownership. Native fills update cash, retained units, weighted cost basis and realized P&L; later fee corrections recompute them. The chart's retained observations and last midpoint valuation are not rewritten.

The sell quantity is capped by reconciled strategy ownership, the base-fee reserve, native amount/cost maxima and the shared quantity bound. It is **not guaranteed to flatten the position**: base fees, precision, native caps or a partial/canceled fill can leave units. They remain visible, including tradable residuals and dust. For additional individually reviewed sells, use **Close position** again. A separate [liquidation plan](#run-a-bounded-liquidation-plan) can authorize a sequence up front. Native fees are unknown until reported. A quote-fee allowance is illustrative, not a fee quote or guaranteed net proceeds.

Residual ownership keeps the account/pair assigned to this retained run, so it can block a new strategy on that same account/pair. Dust below native minimums cannot currently be sold. Use [Position ownership](strategy-ownership.md) for separately reviewed release to unmanaged holdings or original-basis handoff to a new run; units are never silently discarded or adopted.

This explicit exit approval has its own limits. It can exceed the original automated entry-order value cap. A one-off reviewed exit needs a connected active account and either **Manual spot trading** or **Exchange strategy execution** enabled in Workspace. It can still be reviewed with the strategy halt or loss guard active. Ownership, account/environment, flags and review expiry are rechecked immediately before committing the shared `submitting` boundary. A ledger change invalidates the review. Unrelated manual account activity can still consume funds; the exchange has the final balance/permission check.

Closing reviews never execute by themselves. Repeated confirmations return retained progress and never send another native write. After process loss an unsubmitted prepared exit is abandoned; a submitted or uncertain one only rejoins status/recovery/fill reads. The earlier Stop & cancel approval **does not cancel a later closing order**. Its separately approved expiry can cancel its remainder, with active account access and either trading permission. Ordinary expiry timing/uncertainty limitations still apply. Manual cancellation remains available in Trade.

Readiness and a current reconciliation match do not establish final settlement. Later fills, fee changes, exchange busts and manual account changes can require further inspection; no finality is invented.

## Run a bounded liquidation plan

For a stopped or completed exchange run, choose **Liquidation plan** in its monitor. This workflow requires **Exchange strategy execution** in Workspace. Resolve outstanding orders, fee valuations and cancellation follow-ups first.

1. Set the plan’s maximum order count (2–5), duration (5–60 minutes), optional maximum base units per sell, and per-order safeguards. **Review sell sequence** reads the exact account’s book and balances. The review shows the fixed sell limit, first-order cap, total owned units, spread guard, fee reserve and expiry.
2. Type the displayed confirmation. Approval grants the worker authority to start the sequence. Each GTC limit uses the same price floor, expires individually after 60–300 seconds, and can only sell within remaining reconciled ownership and the approved size. The venue may fill at a better price.
3. Follow each order from the plan dialog or **Decision journal → Liquidation plans**. A further sell requires progress on the last one, confirmed terminal status, matching native fills and fees, and any late cancellation checks. The worker sends up to one new sell per cycle. It never retries an uncertain submission.

The plan ends at its order, size or time bound. It also ends when the bid falls below the approved floor, ownership evidence changes or the previous sell has zero fills. Precision, fees and native trade limits can leave residual units. A global halt, backend restart or **Stop future sells** withdraws future-sell authority. Submitted orders retain their approved expiry and reconciliation. To request cancellation, use a fresh **Stop & cancel** review or cancel the linked order in Trade. A venue or backend outage can delay expiry handling.

The plan covers one run, one account and one spot pair. It is independent of the signal loss/exposure policy and is available for a stopped run with a loss latch. Standalone exits and ownership changes need the plan to end first.

## Review lifetime performance

In a run's monitor, open **Lifetime performance** for its flow-adjusted return estimate, quote-valued gain and recorded capital flows. Terminal flat runs with reconciled execution evidence can be archived there. See [lifetime performance and archiving](strategy-ownership.md#lifetime-performance-and-archiving) for marks, fee evidence and eligibility.

## Pending

Initial [Binance Testnet strategy acceptance](../developers/exchange-acceptance.md#automated-strategy-acceptance) covers real entry/exit orders, duplicate approvals, native fill/fee accounting, paused restart, shared capital rejection, global halt and controlled entry-response loss with client-ID recovery. These checks used virtual funds and left the main workspace's execution flags disabled.

Observed partial fills, cancellation races, late corrections, real connectivity failures, broader sandbox/production acceptance, placement-channel and historical custody verification, definitive settlement/bust handling, broader shared risk-policy options and additional providers remain on the [implementation checklist](../developers/backend-roadmap.md). Do not interpret a supported adapter badge as successful private-account verification.

The code is in `src/sibyl/strategies/execution/`: `contracts.py`, `approvals.py`, `venue.py`, `accounting.py`, `cancellation.py`, `stop_reviews.py`, `closing.py`, the modular `ownership/` package and `runner.py`. Cancellation progress lives on each owned order intent; the persisted stop policy and deadlines reconstruct work after restart. Closing reviews persist separately; their deterministic request keys and linked intents protect duplicate confirmations. A domain guard compares a coherent ownership digest within the shared submission transaction. Host locks precede per-intent locks, matching the submission pipeline. Equal native fill timestamps use local order creation order as the causal tiebreaker for this serialized strategy. It reuses `ExchangeTrading`, order recovery and native fill reconciliation rather than introducing another exchange client. Native limit-order reference: [Binance Spot trading API](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/trading-endpoints).

| Method | `/api/v1` path | Purpose |
| --- | --- | --- |
| GET | `/strategies/exchange/options` | Implemented providers, account activation and workspace permission |
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
| GET | `/strategies/exchange/jobs/{id}/performance` | Retained lifetime estimate, capital flows and historical fee evidence |
| POST | `/strategies/exchange/jobs/{id}/performance/mark` | Save an exact venue midpoint for the lifetime report |
| POST | `/strategies/exchange/jobs/{id}/archive` | Archive or restore a flat, reconciled terminal run |
| GET / POST | `/strategies/exchange/jobs/{id}/fee-review` | Read a historical fee batch or approve its exact prices |
| GET | `/strategies/exchange/jobs/{id}/fee-review/{review_id}` | Read an immutable approval receipt |
| GET | `/strategies/exchange/jobs/{id}/liquidation` | Read the latest authorized plan and its child orders |
| POST | `/strategies/exchange/jobs/{id}/liquidation/preview` | Review a fixed-price, bounded sell sequence |
| POST | `/strategies/exchange/jobs/{id}/liquidation/{plan_id}/confirm` | Authorize the exact plan for the worker |
| POST | `/strategies/exchange/jobs/{id}/liquidation/{plan_id}/stop` | Withdraw future-sell authority |
| GET / POST | `/strategies/exchange/jobs/{id}/ownership/repair` | Discover repair requirements or approve an exact replay |
| POST | `/strategies/exchange/jobs/{id}/ownership/repair-preview` | Preview a repair using the supplied sale funding assertions |
| GET | `/strategies/exchange/jobs/{id}/ownership/repairs/{repair_id}` | Read the approved basis changes through an affected run |
