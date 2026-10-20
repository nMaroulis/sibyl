# Portfolio

Portfolio is the home screen. It combines portfolio value, allocation, holdings, recent activity, valuation notes, per-account balances, and the contextual Accountant assistant.

## Read the source first

In **demo mode**, the portfolio reads the connected Demo account through the same backend account interface as real providers. It uses the persistent paper wallet. The initial virtual balances are 24,850 USDT, 0.84 BTC, 8.2 ETH, 74 SOL, and 210 LINK. Paper trades change these quantities. The seed balances and price fixtures are defined in the Python backend, and React displays the API results. Disconnecting Demo hides it from the portfolio without deleting its wallet; reconnect it in Settings to restore the view.

In **live mode**, the portfolio aggregates total spot balances from your saved exchange connections. Multiple accounts per exchange are supported. A failed account read is identified and excluded; the dashboard never substitutes virtual balances.

## Valuation

Public quotes come from the configured market exchange. USDT, USDC, USD, and DAI are approximately valued at 1 USDT. This simplification does not model depegging or USD/USDT conversion. Holdings outside the supported quote watchlist are listed as **unpriced**, rather than represented as zero-valued assets.

The displayed daily price move applies the asset's price change to today's quantities. It is not realized profit, cost-basis P&L, or a time-weighted investment return. Transfers, fees, and changing positions affect account value.

## History

The demo chart reconstructs the value of **current** paper quantities at historical sample prices. It is illustrative valuation, not historical portfolio performance.

Live mode records one actual portfolio observation per UTC hour when the portfolio is read. The first observation starts an honest history; earlier balances are not invented. Deposits and withdrawals affect this history.

Use 1W, 1M, 3M, or ALL to change the displayed slice. The chart uses daily demo observations or collected live observations, so a newly connected workspace can initially show very little history.

## Controls

- **Export** downloads holdings and their source as CSV.
- **Hide balances** obscures marked monetary values and portfolio value charts visually. It is a presentation aid, not access control; the data remains in the page and accessibility tree.
- **Sort assets** switches between value and daily price movement.
- Selecting an asset opens its market analysis.
- **Ask Accountant** opens an in-page dialog and invokes the Accountant agent's native read-only tool through ProtoLink.

Paper cash belongs to the virtual ledger. Connected exchange funds are never added to that ledger.

## Navigation

Use the floating dock on the left to switch between Portfolio, Markets, Trade, Strategies, Agents, Forecasting, News, and Settings. The dock stays vertically centered and sits apart from the window edge. A fine line and a matching page-edge marker follow the selected button, and pages unfold from that point. **More** unfolds a small horizontal dock to the right with Research, Trading report, and Coming soon. Its links slide into view without a modal or backdrop. Click More again, click elsewhere, or press Escape to close it. Keyboard users can press Right from More to enter the links, then use Left/Right, Home, or End to move between them. Press **⌘K** (or **Ctrl+K**) to search pages and supported assets.

Multi-section pages use a matching floating tab bar at the top. Its selected pill slides between sections and the content gently reveals. Arrow keys, Home, and End switch tabs; reduced-motion preferences disable the animations. [Settings](./settings.md) brings exchange accounts, AI models, other APIs, and workspace access into one destination.

## Separate account balances

Open **Portfolio → Account balances** for each account's available (`free`), reserved (`used`), and total spot quantity. Choose an account and filter assets. A missing provider balance component displays a dash, rather than an invented zero. Account read errors are marked explicitly.

Valuations use the six-asset reference watchlist and USD-stablecoin parity. Choose USDT, USD, BTC, or ETH when a reference conversion rate exists. Conversion is for display/export, not a currency trade. Assets without a supported price remain visible and are excluded from the priced account total. Demo mode shows the manual paper wallet; strategy jobs have separate virtual accounts in their console.

CSV exports the currently filtered rows and selected valuation currency. Private balances cache for 30 seconds; the panel polls once a minute. Disconnecting an account clears its cached adapter and account balances.
