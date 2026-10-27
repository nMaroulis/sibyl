# Account

Account is the home screen. It combines portfolio value, allocation, holdings, recent activity, valuation notes, per-account balances, and the contextual Accountant assistant.

## Connect and select accounts

A new workspace has **no active accounts**. Account and Trade show a setup screen explaining that you can connect one or many exchange accounts. Public Markets, news and research remain independently usable.

Use **Settings → Exchanges** to save a connection. Connecting activates it and automatically turns Demo off. Additional exchange accounts join the active selection, including multiple accounts at the same exchange. Each saved account has an **Active / Inactive** control. Deactivation keeps credentials, balances at the exchange, and retained history; it pauses imports and excludes the account from new account reads and order entry. Deactivating or disconnecting the last exchange account returns to setup. It never silently enables Demo.

The **Account view** picker offers **All exchanges**, **By exchange**, and **Individual accounts**. Totals, holdings, allocations, account balances and history use that same selection. Account cards show each constituent's value and open its individual view. Expand the account count beside a holding to see how its native quantity is split among accounts. The selected scope is shareable through the page's `scope` query parameter.

Production totals exclude test accounts. When only test accounts are active, the combined view is clearly labeled **Combined test accounts**. Individual test scopes remain available alongside production scopes, with test-funds labels. A failed account read is identified and excluded; it never becomes a zero balance.

## Optional Demo preview

**Preview with Demo** explicitly activates a local virtual wallet. A warm banner says **Demo preview is active**, the header shows **Demo preview**, and **Exit preview** returns to setup. Demo cannot be activated while exchange accounts are active. It uses the same backend account and valuation interface as exchanges, with no API key. Connecting an exchange turns it off automatically.

The persistent initial paper balances are 24,850 USDT, 0.84 BTC, 8.2 ETH, 74 SOL, 210 LINK, 1,200 ADA, 1,500 USDC, and 250 EUR. Previewing again keeps existing paper quantities and trades; it never resets the ledger. The virtual wallet is never added to exchange totals. Reference prices still follow Market data settings and are labeled separately.

## Valuation

Prices come from the workspace's selected **Market data** feed. Valuation discovers exact native pairs for your actual holdings, independently of your Markets watchlist. It tries direct and inverse pairs, then short paths through USDC, USD, BTC, ETH, EUR or DAI. For example, ADA → BTC → USDT multiplies the two observed rates; EUR → USD → USDT can invert a native USDT/USD quote.

Only USDT itself equals 1 USDT. Stablecoins and fiat need observed conversion rates, so a stablecoin away from its peg changes the value. Source coverage varies: public exchanges expose their active spot catalog; API adapters have a curated catalog. The service never switches feeds or invents parity to fill a gap.

Open the conversion caption beneath a holding's price to see every exact pair, direction, rate and provider/fetch time. Quotes older than five minutes or with invalid prices/timestamps are excluded. Undated quotes are usable but labeled **Undated**, with a warning that their age cannot be verified. Demo observations are synthetic and explicitly exempt from live quote-age checks.

**Valuation notes** shows priced/total asset coverage and a link to Market data settings. Unpriced holdings stay visible with their quantities and exclusion reasons. Failed account reads make coverage partial too. The total is labeled **Priced portfolio value** when coverage is incomplete; allocation describes only priced holdings. A finite request/time budget can leave assets temporarily unpriced. Refresh later or choose a feed with appropriate coverage.

The displayed daily price move composes each conversion leg's observed 24-hour change and applies it to today's quantities. It is unavailable if any held asset/account or required daily change is unavailable. It is not realized profit, cost-basis P&L, or a time-weighted investment return. Transfers, fees, and changing positions affect account value.

## History

The demo chart reconstructs the value of **current** paper quantities at historical sample prices. It is illustrative valuation, not historical portfolio performance.

Other selected-account/feed combinations record one complete portfolio observation per UTC hour when read. Incomplete reads never add or overwrite a history point. Histories are partitioned by account mode, selected feed and selected account IDs; the new valuation starts a separate series from earlier approximate totals. Earlier balances are not invented. Deposits and withdrawals affect this history.

Use 1W, 1M, 3M, or ALL to change the displayed slice. The chart uses daily demo observations or collected live observations, so a newly connected workspace can initially show very little history.

## Controls

- **Export** downloads priced and unpriced holdings, quantities, values, source, pricing status, conversion paths, timestamps and exclusion reasons as CSV.
- **Hide balances** obscures marked monetary values and portfolio value charts visually. It is a presentation aid, not access control; the data remains in the page and accessibility tree.
- **Sort assets** switches between value and daily price movement.
- Selecting an asset opens its market analysis.
- **Ask Accountant** opens an in-page dialog and invokes the Accountant agent's native read-only tool through ProtoLink.

Paper cash belongs to the virtual ledger. Connected exchange funds are never added to that ledger.

## Navigation

Use the floating dock on the left to switch between Account, Markets, Trade, Strategies, Forecasting, News, Agents, and Settings. The dock stays vertically centered and sits apart from the window edge. A fine line and a matching page-edge marker follow the selected button, and pages unfold from that point. **More** unfolds a small horizontal dock to the right with Research and Coming soon. Trade includes its own Executions and Account history tabs. Its links slide into view without a modal or backdrop. Click More again, click elsewhere, or press Escape to close it. Keyboard users can press Right from More to enter the links, then use Left/Right, Home, or End to move between them. Press **⌘K** (or **Ctrl+K**) to search pages and supported assets.

Multi-section pages use a matching floating tab bar at the top. Its selected pill slides between sections and the content gently reveals. Arrow keys, Home, and End switch tabs; reduced-motion preferences disable the animations. [Settings](./settings.md) brings exchange accounts, AI models, other APIs, and workspace access into one destination.

## Long asset lists

Allocation, Holdings, unpriced assets in Valuation notes, and Account balances initially show ten rows. **Show more** reveals up to ten more at a time; **Show less** restores the compact view. A counter shows the visible and total rows. Hover/focus highlights the controls, and reduced-motion settings suppress animated movement. Sorting or changing balance filters starts a fresh compact view. Portfolio totals, allocation calculations and CSV exports still cover the entire selected dataset.

## Separate account balances

Open **Account → Account balances** for each account's available (`free`), reserved (`used`), and total spot quantity. This panel follows the Account view selection. You can further choose an account and filter assets. A missing provider balance component displays a dash, rather than an invented zero. Account read errors are marked explicitly.

Account balances use the same valuation engine as the overview. Choose USDT, USD, USDC, BTC, ETH or EUR when an observed conversion rate exists. Conversion is for display/export, not a currency trade. Assets without a supported price remain visible and are excluded from the priced account total. Failed account totals display a dash, not a zero balance. Conversion captions explain the USDT reference price; the selected display currency divides by its current USDT rate. If that currency becomes unavailable, the selector returns to USDT. Demo preview shows the manual paper wallet; strategy jobs have separate virtual accounts in their console.

CSV exports the currently filtered rows and selected valuation currency. Private balances cache for 30 seconds; the panel polls once a minute. Disconnecting an account clears its cached adapter and account balances.

For cost-basis results, open **Trade → Account history → Performance**. It computes retained market FIFO with opening inventory and optional balance-checked current marks. These results have explicit coverage limits and are separate from daily market moves and portfolio valuation history. See the [trading guide](trading.md#retained-account-performance).

Account uses the same wallet icon as the exchange cards’ Account overview category. Markets uses the same candlestick icon as Market data. The canonical dashboard URL is `/account`; existing `/portfolio` bookmarks preserve their query filters when redirected.

## Watch your own limits

**Risk alerts** opens setup for the current account view. Watches pin the accounts you review, with value floors, asset concentration or observed-value drawdown. They require complete fresh pricing and deliver in-app notices; they do not trade or enforce strategy risk policies. See [account risk alerts](account-risk.md).
