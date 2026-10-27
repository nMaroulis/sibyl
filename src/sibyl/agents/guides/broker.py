"""Manual trading and strategy workspace instructions, separate from recorded evidence."""

from typing import Literal

from sibyl.agents.guides import Guide

TradeTopic = Literal[
    "overview", "accounts", "orders", "history", "executions", "tracking", "cancel", "recovery"
]
StrategyTopic = Literal[
    "overview", "backtest", "results", "validation", "paper", "exchange", "monitor", "stop", "halt", "limits"
]

TRADE = {
    "overview": Guide(
        "Use the trading workspace",
        "/trade",
        (
            "Trade contains three tabs: Trade for order entry, Executions for local fills and exchange orders, and Account history for imported fills and accounting.",
            "Select the account and exact market before reviewing an order; Demo, test and production funds are separate.",
        ),
    ),
    "accounts": Guide(
        "Connect an account or explore with Demo",
        "/settings?tab=exchanges",
        (
            "Connect and activate an account in Settings → Exchanges. Inspect its implemented feature support before enabling spot permissions.",
            "With no active account, Trade offers Connect exchange accounts and a smaller Preview with Demo option.",
            "Demo uses a virtual wallet; activating an actual account disables it. An active account alone does not enable exchange order submission.",
        ),
        (
            "API keys belong only in Settings. Live execution also requires backend enablement and an explicit order review.",
        ),
    ),
    "orders": Guide(
        "Review a spot order",
        "/trade",
        (
            "Choose the account, exact spot pair, side and base quantity. Select Market or a supported Limit · GTC and enter the limit price.",
            "Review the environment, reference notional, precision and funds checks, then type the displayed confirmation phrase.",
            "The review expires after 60 seconds. After submission, inspect the order monitor for actual status, fills and fees.",
        ),
        (
            "A review reserves no exchange funds. Market fills can differ from reference prices; GTC orders remain open until filled or canceled. Settings → Exchanges shows each provider's supported features.",
        ),
    ),
    "history": Guide(
        "See account history",
        "/trade?tab=history",
        (
            "Open Trade → Account history → Fills & imports.",
            "Choose an active supported account and exact spot market, then Sync market history; saved progress supports pause/resume and later Sync again.",
            "Filter retained fills and inspect native IDs and fees. Pause active work before Rescan available history to revisit older available fills and corrections.",
            "Use Performance for retained market FIFO, Funding for deposits/withdrawals, and Reconcile transfers within Funding for own-account links.",
        ),
        (
            "Executions is local order activity; Account history is the retained exchange fill ledger. Provider retention limits imports; completed passes do not prove full coverage.",
        ),
    ),
    "executions": Guide(
        "Find fills and order records",
        "/trade?tab=executions",
        (
            "Open Executions and filter by account, symbol, record ID, mode, side, status or date.",
            "Use Order monitor for submitted orders and their filled/remaining quantities. Open Executions on an order for retained fill and fee evidence.",
            "Use Sync exchange orders to discover supported open/recent orders placed outside Sibyl. Imported · read-only orders are managed at the exchange.",
        ),
        (
            "A preview reference is not a fill or realized P&L. Refresh records reloads local data; Check exchange performs a provider read.",
        ),
    ),
    "tracking": Guide(
        "Track and reconcile an order",
        "/trade?tab=executions",
        (
            "Find the order in Order monitor and inspect status, cumulative filled quantity and remaining quantity.",
            "Check exchange reads status; Check executions imports retained native fills and fees. Enable tracking to continue supported background reads.",
            "Inspect incomplete pages, missing fees and differing evidence before treating an order as reconciled.",
        ),
        (
            "Pausing tracking does not cancel an order. Partially filled orders can still be open. Bounded follow-up checks do not guarantee final settlement.",
        ),
    ),
    "cancel": Guide(
        "Cancel a supported order",
        "/trade?tab=executions",
        (
            "Open Cancel… on the order and review its latest observed native state.",
            "Type the displayed cancellation phrase, then inspect the resulting status and execution evidence.",
            "If the result is uncertain, inspect the exchange before taking another action.",
        ),
        (
            "A cancellation acknowledgment is not proof of cancellation; a fill may win the race. Uncertain cancellation writes are not automatically retried.",
        ),
    ),
    "recovery": Guide(
        "Handle an uncertain submission",
        "/trade?tab=executions",
        (
            "Inspect an unknown/submitting record and check the exchange before creating any replacement order.",
            "Where offered, Recover order looks for one verified match using the saved client ID; Continue lookup advances unfinished pages.",
            "If no verified match is available, inspect the order directly at the venue. Settings → Exchanges explains the selected provider's recovery limits.",
        ),
        ("No match does not prove there is no order. Recovery never resubmits the original order.",),
    ),
}

STRATEGIES = {
    "limits": Guide(
        "Set shared strategy limits",
        "/strategies",
        (
            "Open Portfolio limits beside Exchange automation. Choose Production or Exchange test funds; their budgets and loss periods are separate.",
            "Enable the policy, choose a live reference feed and set maximum allocated capital, gross exposure and daily loss in reference USDT. Type SAVE STRATEGY LIMITS. Saving pauses affected runs; assess and Resume each deliberately.",
            "Refresh assessment to see all strategy contributions, retained holdings, outstanding buys and reference prices. Stale/incomplete evidence blocks new automatic orders.",
            "A daily-loss breach locks and pauses that environment. A previous day's lock can be released after a fresh assessment on a later UTC day by typing RELEASE DAILY LOSS LOCK; no run resumes automatically.",
        ),
        (
            "Daily loss is the net decline in observed strategy P&L, including unrealized positions and known native fees. The first assessment establishes the initial baseline; later UTC days carry the last observed P&L, not an exact midnight price. New run allocations are not profits.",
            "Exposure includes outstanding buys and stopped holdings; pending sells do not reduce it. Existing orders can fill. Manual Trade, separately approved Close position, cancellation and paper runs retain their own permissions. No maximum loss or automatic liquidation is guaranteed.",
        ),
    ),
    "overview": Guide(
        "Build and inspect a strategy",
        "/strategies",
        (
            "Choose a strategy, exact pair, timeframe, observations and initial virtual capital in the studio.",
            "Expand indicator, risk or execution settings only when needed. Backtest historical behavior before considering a paper or exchange run.",
            "Use Monitor to open a saved run and inspect its journal, observations and fills.",
        ),
    ),
    "backtest": Guide(
        "Run a reproducible backtest",
        "/strategies",
        (
            "Choose current feed or an immutable saved dataset under Research input, then configure the strategy and trading costs.",
            "Run the backtest and inspect the retained input provenance, fingerprint and engine version.",
            "Rerun exact input recomputes the same saved data/settings with the current engine; Load settings lets you edit a new experiment.",
        ),
        (
            "Signals use the previous closed candle and backtest fills use the next open, with configured fees/slippage. Historical simulation does not establish future profitability.",
        ),
    ),
    "results": Guide(
        "Inspect buys, sells and performance metrics",
        "/strategies",
        (
            "Open a saved experiment. Price & trades shows buy/sell markers; select a marker for quantity, price, fees and exit reason.",
            "Use the time brush to inspect an interval, Equity & benchmark to compare cost-aware buy-and-hold, and Drawdown for peak declines.",
            "Expand risk metrics and trade-by-trade accounting, export complete fills/equity, or compare runs with the same input fingerprint and capital.",
        ),
        (
            "Undefined ratios stay unavailable. Synthetic Demo inputs remain labeled; a simulated fill is not an exchange execution.",
        ),
    ),
    "validation": Guide(
        "Validate on later unseen candles",
        "/strategies",
        (
            "Expand Validate on unseen data and choose the bounded parameter search and chronological holdout/walk-forward windows.",
            "Inspect training rankings separately from later test-window metrics and fixed-settings/buy-and-hold comparisons.",
            "Open a saved study to inspect each window, reuse its exact input or export evidence.",
        ),
        (
            "Each test starts with separate virtual cash; results are not a continuously compounded account. Repeated searches can overfit; the best training score is not a test result.",
        ),
    ),
    "paper": Guide(
        "Run a monitored paper strategy",
        "/strategies",
        (
            "Choose current-feed input and review parameters before starting a paper run.",
            "Open its Monitor to inspect signals, virtual fills, equity, costs and events. Paper capital is separate from manual Demo wallet funds.",
            "Pause retains its virtual position. Completed/stopped paper runs cannot resume.",
        ),
        ("Paper runs spend no exchange funds and do not simulate venue queues or liquidity exactly.",),
    ),
    "exchange": Guide(
        "Review exchange-connected automation",
        "/strategies",
        (
            "Connect an active supported account, then expand Run on a connected exchange. The backend must enable both live trading and strategy execution.",
            "Review the exact account, environment, pair, budget, order caps, risk limits and any cancellation policy; type the displayed approval phrase.",
            "Inspect native order and fill evidence in Monitor. Check implemented capabilities in Settings → Exchanges and start with test funds where available.",
        ),
        (
            "Automation can spend exchange funds. Orders are price-capped GTC limits; local expiry is best-effort cancellation, not a native guarantee. Agents cannot approve or start runs.",
        ),
    ),
    "monitor": Guide(
        "Inspect a running strategy",
        "/strategies?view=monitor",
        (
            "Choose a run to open its monitor; a shared URL with view=monitor and job identifies that exact run.",
            "Inspect mode, account/environment, observations, journal, equity, native orders, fills and fee warnings before interpreting performance.",
            "Use Run alerts for future journal notifications; these do not change the strategy or replay older events.",
        ),
        (
            "Paper and exchange runs have different evidence. A paused run may still own holdings and resting orders.",
        ),
    ),
    "stop": Guide(
        "Pause, stop or close a strategy position",
        "/strategies?view=monitor",
        (
            "Inspect the selected run and its outstanding orders before using Pause or Stop; neither alone liquidates holdings.",
            "If separately approved, Stop & cancel requests cancellation. Verify native status and completed fill follow-ups.",
            "Close position is a new typed, one-order sell review for a stopped/completed exchange run after reconciliation. Inspect blockers and any residual units.",
        ),
        (
            "A cancel request or sell acknowledgment does not prove a position is flat. Residual ownership stays with the stopped run; automatic handoff to a new run is unavailable.",
        ),
    ),
    "halt": Guide(
        "Halt automatic strategy submissions",
        "/strategies?view=monitor",
        (
            "Use Halt automation above the strategy workspace to block new automatic orders across exchange accounts and pause their runs.",
            "Inspect existing orders and holdings: an already admitted request can finish before the halt returns.",
            "Review & release requires its displayed phrase. Release resumes no run; inspect and resume each run explicitly.",
        ),
        (
            "Halt is persistent, not liquidation. Manual Trade, separately reviewed exits, approved cancellation policies and paper runs retain their permissions.",
        ),
    ),
}
