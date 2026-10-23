# Strategy monitor

Open **Strategies → Monitor**, then choose **Open monitor** on any run. Starting a paper strategy opens its monitor automatically. You can also open paused, completed, and stopped runs. The run URL is shareable within your local workspace: `/strategies?view=monitor&job=RUN_ID`.

## Find and open a run

Search the run table by strategy name, market, or run ID. Filter by status. Each row shows creation time, source market/timeframe, paper equity, return, and last worker check. The header counts running and total jobs. The selector inside a monitor switches directly between runs; **All strategy runs** returns to the list.

The **Build & backtest** and **Monitor** tabs share the workspace, preserving the current builder form while you inspect a run.

## Live view

The header identifies the strategy, run, paper execution mode, data source, candle interval, creation time, status, and last worker check. Four account cards show:

- Paper equity: cash plus the open position valued at the most recently observed quote.
- Total P&L: equity minus the original virtual capital, including recorded simulated fees and slippage. It does not deduct hypothetical fees for a future exit.
- Available virtual cash in the market's quote currency.
- Open spot position in the base currency.

The chart offers **Price**, **Equity**, and **Drawdown**. Price uses actual worker observations from the selected source; demo observations are synthetic fixtures and stay labeled. BUY and SELL markers come from persisted fills, with their execution prices and timestamps. Optional skipped-signal markers show decisions that did not create fills. Hover the reference-price line for the observed sample; use the journal for each execution's full details.

Enable **Show simulated slippage** to display the reference price and fill-price difference. Slippage is `fill_price − reference_price`. Positive is adverse for buys; negative is adverse for sells. These are configured paper execution assumptions, not measurements of an exchange fill. Fees are separate.

Choose the most recent 100, 300, 1,000, or 2,000 samples, and export the displayed observations. No earlier quotes are invented. The drawdown chart measures percentage decline from the peak **within the displayed observation window**. It is distinct from the closed-candle risk metric's sample.

## Refresh and evaluation are separate

The browser polls monitor data every five seconds while auto-refresh is on. The server worker checks each running job every 30 seconds and records one current-price/equity observation per successful check. It evaluates the algorithm **at most once per newly closed candle**.

A daily strategy may therefore have many price observations but only one decision per day. Turning auto-refresh off pauses the browser view; the server job continues. Manual refresh only reads persisted state and never runs a strategy. Old observations and read errors are identified visibly.

The older one-second/15-second runtime options are not reintroduced as fabricated OHLC intervals. Current strategy decisions follow supported closed candles (minimum one minute), independent of how often you refresh the view.

## Decision journal

The journal saves every evaluated candle and lifecycle change. Each decision records observation time, candle opening timestamp/close, original algorithm signal, action/reason, reference and fill price, signed slippage, fee, quantity, and resulting cash/position/equity.

| Action                        | Meaning                                                                        |
| ----------------------------- | ------------------------------------------------------------------------------ |
| BUY / SELL                    | A simulated fill changed the paper account                                     |
| HOLD                          | No entry or exit signal on this closed candle                                  |
| SKIP BUY                      | An entry signal was blocked, for example because the strategy was already long |
| SKIP SELL                     | An exit signal arrived while the strategy had no position                      |
| ERROR                         | A worker evaluation failed; no partial paper fill is committed                 |
| START / PAUSE / RESUME / STOP | A lifecycle transition                                                         |
| MONITORING STARTED            | Detailed observations began for an earlier run                                 |
| RECOVERED                     | Observations resumed after an error without a new decision                     |

Risk exits can override the original signal; the journal retains both signal and resulting action. Reaching a round-trip limit completes the run and is recorded in the final decision's reason. Skipped actions are intentionally separated from failures: the paper engine does not submit a duplicate order merely to mark it invalid.

Filter all activity, fills, hold decisions, skipped entries/exits, errors, pauses, or stops. Older pages use stable event cursors and stay fixed while you read. **Back to latest** restores the newest page. **Export matching logs** downloads all matching recorded events chronologically, including events older than the visible page. Exports include run ID, symbol, quote currency, and source. Numeric slippage and fees keep their signs and quote-currency units.

## Performance and run parameters

Recorded performance includes Sharpe, Sortino, Calmar, maximum drawdown, percentage-return profit factor, win rate, and average winning/losing trade. Risk metrics use up to 720 closed-candle equity observations and a preceding baseline. Short samples and gaps after pauses affect annualization. Undefined values display a dash. See [Strategy studio](./strategies.md) for formulas.

Execution details include recorded realized P&L, entry cost including fees, total simulated fees, completed round trips, and last evaluated candle. Realized P&L is recognized when a complete recorded position is sold; open positions are only marked to market. These calculations use this run's isolated virtual account.

**Run parameters** lists the stored configuration. Editing the builder does not mutate a running strategy. Start another run to test different parameters.

## Pause, resume, and stop

**Pause** suspends strategy evaluation and price sampling while retaining the virtual position. **Resume** continues from the latest available closed candle; it does not replay downtime. Duplicate candle processing is prevented across restart/resume.

**Stop** requires a confirmation within the app and is terminal. It retains the virtual position and history, performs no liquidation, and freezes the displayed valuation. Stopped and completed runs cannot resume. Start a fresh run instead. Terminal runs remain readable and exportable.

Changing the configured price source automatically pauses a running job; resume is refused until you return to that source or create a new run. At most ten paper jobs may run at once, including resumed jobs. Pause and Stop are accepted without waiting for an in-flight provider read; the worker rechecks the run state before committing any fill from that read. Use one API process/worker.

## Broker in the monitor

**Ask Broker** opens the existing in-page ProtoLink overlay with this run's ID. Its read-only tool retrieves the stored run, actual parameters, recent observations, and recent decisions. Questions about one run have a separate conversation from builder questions and other runs. The agent cannot start, pause, stop, or trade.

## Persistence and earlier runs

Job state, processed candle cursor, event, and observation commit atomically in SQLite. Decision/lifecycle events are retained completely for export. Quote observations retain the most recent 2,000 samples per run. The convenience `fills` array retains 100 fills; the journal retains all fills generated after detailed monitoring began.

Existing runs remain inspectable. Earlier retained fills appear in their own table and CSV. Unknown reference prices, prior decisions, and unavailable lifetime totals remain blank rather than being reconstructed. A notice identifies when detailed monitoring began.

This monitor supports isolated paper runs and [approved exchange strategies](strategy-execution.md). Exchange runs show account/environment, native orders, fill-derived ownership, fee currencies and approved order lifetime. Ordinary Pause/Stop prevent new submissions and request no immediate cancellation; an approved expiry policy continues, including after restart. **Stop & cancel orders** opens a separate typed review, stops submissions permanently and queues this run's outstanding orders. It never sells the position. Active account access and the live-trading flag are required for cancellation writes.

Order rows distinguish queued, blocked, requested, unknown, reconciling and currently reconciled cancellation states. Deadlines and bounded late native status checks remain visible. An acknowledgment is not a confirmed cancellation, and a terminal order still needs native fill/fee reconciliation. Unknown writes are only observed afterwards, never automatically resent. The journal and CSV include `STOP_CANCEL` and `CANCEL_*` transitions; select their filters to inspect the history. Retained native fills can still update a paused/stopped run; its price valuation may be stale.

**Close position** opens a separate [reviewed exit](strategy-execution.md#close-a-retained-position). The dialog explains any prerequisite, then previews owned/sell units, price floor, fee reserve and residual. Only typed approval submits the one sell. The **Reviewed position exit** section reports submitted, unknown, interrupted/rejected, reconciling or currently reconciled progress. Order rows mark these sells **Exit**. Partial fills update owned units and realized P&L; remaining units require a fresh review. Journal/CSV filters include every `CLOSE_*` transition and its review/order IDs. A stopped run remains terminal throughout.
