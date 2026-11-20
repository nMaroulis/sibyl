# Cross-pair asset accounting

Trade → Account history → Performance → Across pairs derives account/asset FIFO books across all retained spot pairs. By market keeps the existing exact-pair report and its separate opening assertions. Neither report establishes complete account history or tax treatment.

## Units and lots

Choose a reporting unit and retained price feed. Every trade applies both assets and every reported fee/rebate asset. Acquisitions keep original dates, quantities and reporting-unit costs. Selling an asset on another pair consumes that same account/asset book. Accounts and Demo/test/production environments remain separate. Reporting-unit principal has identity cost; stablecoins and fiat are never treated as interchangeable.

Foreign fee debits consume their own lots and use an observed historical reporting value for purchase cost or sale proceeds. Rebates lower purchase cost/increase sale proceeds and create rebate-asset inventory. Missing fees or conversions retain unknown acquisition cost; unknown sold units are excluded from matched realized components. Retained quantity is derived lot inventory, not a fresh account balance. Missing inventory, timestamp ties and unresolved funding remain visible qualifications.

## Historical conversion

`accounting/executions/prices.py` reads only retained closed candles in the selected source/environment. A conversion uses at most three direct/inverse legs, each fully closed before or at the execution and no more than 24 hours old. An exact reported fill ratio may bridge its own two assets. A candle is an approximate historical mark, not a contemporaneous execution quote. Future closes and missing routes are excluded; no provider is contacted by the report or agent.

Reports hash the actual price snapshot with fills, funding, openings and transfer links. A retained candle correction changes the fingerprint. Reports calculate all inputs within the budgets: at most 20,000 fills, 20,000 funding records, 2,000 transfer pairs, 1,000 transfer groups and 100,000 conversion bars across 200 source series. Oversized work is rejected, never silently truncated. Public detail is capped at 500 disposals/conversions and 100 transfers per environment; counts disclose those limits.

## Funding and transfers

Funding uses existing documented/provider or source-version-bound local wallet/amount reviews. Unpaired incoming crypto has unknown acquisition cost; an outgoing movement removes lots without becoming sale proceeds. Neither implies an external-cash-flow classification. Missing posting dates and unresolved effects remain qualified.

Current confirmed one-to-one equal-amount/zero-fee links or explicitly balanced same-asset fee allocations carry original lots across account boundaries and trading pairs. Source corrections make links unavailable until reviewed. A receipt before dispatch, unsupported fee convention or an opening crossing a transfer boundary prevents carryover. Unapplied funding remains visible. Explicit [split/merged groups](transfer-groups.md) also carry lots through exact principal matrices; all group members must remain current and precede receipt. Additional-wallet coverage and broader fee policies remain pending.

## Opening assets and corrections

Opening asset assertions are independent of legacy pair-specific openings. Save an explicit quantity, reporting-unit cost (or unknown), timezone-aware date before every retained affected execution, and an evidence note. Edits require the displayed revision; withdrawals preserve their audit. An older import or corrected execution timestamp can invalidate an existing assertion; the report excludes it and displays a review reason.

`fill_versions` retains the complete normalized fill observation with its hash and revision in the same transaction as the shared fill and import checkpoint. Repeated identical imports add no versions. Pre-existing fills receive a labeled retained baseline on the first observation after this feature; unseen older corrections are not reconstructed. Rolling back an import rolls back its revisions and notification effects.

## API and native agents

- `GET /api/v1/account-books`: currency, source, optional account and environment filters. A destination view still loads source acquisitions needed for transferred lots.
- `GET /api/v1/account-books/openings`: current explicit assertions.
- `POST /api/v1/account-books/openings/{account_id}`: revision-checked opening assertion.
- `DELETE /api/v1/account-books/openings/{id}?revision=N`: audited withdrawal.
- `GET /api/v1/account-books/fills/{id}/versions`: bounded correction history.

Accountant's native `account_asset_books` returns scoped modeled components, actual conversion receipts and qualifications. It never reads current balances, fetches prices, imports history or edits assertions. The selected page works in factual mode without a model. Technician's exchange setup now returns concise feature statuses by default; `feature_details=true` reads full limitations. Full detail uses the existing native context-artifact mechanism; no custom LLM adapter is added.

Offline checks cover cross-pair cost, third-asset fee/rebate effects, inverse/bridge prices, future/stale/environment isolation, unknown basis, transfer origins, opening invalidation, correction rollback/idempotency and native Accountant routing. Complete provider history, accounting policy choice and authenticated venue acceptance remain separate.
