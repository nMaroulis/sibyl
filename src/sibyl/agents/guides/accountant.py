"""Account and retained accounting workflows; these instructions never read funds."""

from typing import Literal

from sibyl.agents.guides import Guide

Topic = Literal[
    "basket_risk",
    "returns",
    "overview",
    "accounts",
    "valuation",
    "history",
    "performance",
    "funding",
    "transfers",
    "risk",
    "balance_checks",
]
GUIDES = {
    "basket_risk": Guide(
        "Explore historical basket risk",
        "/account",
        (
            "Expand Historical basket risk, select up to eight priced current holdings and a history window, then Calculate & save risk study. Multiple connected accounts follow the current Account scope; Demo/reference sources stay labeled.",
            "Inspect annualized volatility, empirical daily VaR/shortfall, sample size, subset coverage and historical dates. Expand correlations/variance contributions or the hypothetical basket path; open saved studies without provider reads or export their full inputs.",
        ),
        (
            "Current weights are renormalized within the selected basket and hypothetically rebalanced daily without costs. This is not measured account performance, an optimized allocation or a forecast. All conversion legs require common consecutive closed daily history; unpriced/failed accounts or excluded holdings can materially change whole-account risk.",
        ),
    ),
    "returns": Guide(
        "Measure investment performance",
        "/account",
        (
            "Open Investment performance in Account, choose the desired view and capture a fresh opening valuation.",
            "Later capture closing values, import/review funding, and confirm complete nonduplicated coverage.",
            "Review per-account and combined Modified Dietz estimates, blockers, source assertions and exports.",
        ),
        (
            "Historical principal conversions and completeness are user assertions. Missing or stale evidence leaves returns unavailable; this is separate from market FIFO and raw account-value changes.",
        ),
    ),
    "balance_checks": Guide(
        "Compare balances with imported activity",
        "/account",
        (
            "In Account, open Balance checks below Account balances and choose one account.",
            "Capture starting balances, import subsequent trade/funding activity in Trade → Account history, then compare with current balances.",
            "Review per-asset differences and missing evidence. Capture a new starting checkpoint only after reviewing gaps; earlier reports remain saved.",
        ),
        (
            "Checks compare native asset quantities, not P&L. Partial history, uncertain funding fees and activity near balance observations can prevent a comparison. Demo/test/production accounts stay separate.",
        ),
    ),
    "overview": Guide(
        "Understand your Account",
        "/account",
        (
            "Open Account for holdings, allocation and valuation across active exchange accounts.",
            "Expand Diversification in Allocation for HHI, effective asset count, largest asset and top-three value weight. Incomplete valuation means unavailable metrics. This measures value spread, including cash/stablecoins separately, not independent risk factors.",
            "Choose all accounts, one exchange or one account in the account selector; inspect pricing warnings before interpreting totals.",
            "For imported fills, accounting and funding, open Trade → Account history.",
        ),
    ),
    "accounts": Guide(
        "Combine or separate exchange accounts",
        "/settings?tab=exchanges",
        (
            "Connect and activate one or several accounts in Settings → Exchanges.",
            "Open Account and choose the combined view, an exchange or an individual account.",
            "With no active account, use Connect exchange accounts or the smaller Just exploring? → Preview with Demo option.",
        ),
        (
            "Demo is explicit virtual data and switches off when an actual account is active. Test environments remain labeled separately.",
        ),
    ),
    "valuation": Guide(
        "Understand prices and incomplete totals",
        "/account",
        (
            "Account view selects which exchange or account supplies balances. Valuation price feed is the workspace-wide source of reference prices; selecting Coinbase does not switch a configured Binance price feed.",
            "Select the source name in Valuation price feed, or open Settings → Market data, to select the reference feed used across account views.",
            "Inspect a holding's valuation details for its reference feed, conversion path and provider time.",
            "In the compact Account summary, Partial marks an incomplete value. Expand Details below the metrics to read pricing and account warnings, then View valuation notes for asset-level exclusion reasons.",
            "Use Export holdings to retain the displayed quantities and valuation evidence.",
        ),
        (
            "Stablecoins and fiat are not assumed equal to USDT. Daily asset price changes are not your investment returns.",
        ),
    ),
    "history": Guide(
        "Find and import account history",
        "/trade?tab=history",
        (
            "Open Trade → Account history → Fills & imports.",
            "Choose an active supported account and exact spot market, then Sync market history.",
            "Filter retained fills and inspect fees, native IDs and import coverage. Pause/resume keeps progress; Rescan available history checks older available records.",
        ),
        (
            "Provider retention and supported markets limit coverage. Caught up does not mean complete account history.",
        ),
    ),
    "performance": Guide(
        "Review retained FIFO performance",
        "/trade?tab=history",
        (
            "Choose Performance in Account history. By market retains exact-pair reports; Across pairs combines acquisition lots for each account/asset in a chosen reporting unit, with separate environments.",
            "Across pairs uses retained closed candles for dated conversion, at most 24 hours old, and reported execution ratios. Import missing conversion history in Market history; no stablecoin parity or missing acquisition basis is assumed. Opening asset saves an audited assertion before retained executions.",
            "Expand Calculation details for matched results, fees, exclusions and disposal calculations; Export summary retains the report.",
            "Use Opening inventory only for holdings acquired before retained fills, with an asserted quantity, optional cost and acquisition date.",
            "Recalculate uses local history. Refresh current marks separately reads active account balances and reference prices.",
        ),
        (
            "Matched market FIFO is not complete account return. Unknown-cost sales, unresolved fees and cross-market gaps keep results provisional; blank cost is unknown, not zero.",
        ),
    ),
    "funding": Guide(
        "Inspect deposits, withdrawals and transfers",
        "/trade?tab=history",
        (
            "Open Account history → Funding, select an active supported account, offered streams and a range shorter than 90 days, then Import range.",
            "Filter retained movements by account, asset, type, status or environment; inspect amounts and fees in their native currencies.",
            "In Wallet balance effect, distinguish Provider rule from Your review. Use Review balance effect for ambiguous records, verify the affected wallet and amount convention against your statement, then save an evidence note. You can withdraw a review; native records stay unchanged.",
            "Pause/resume preserves progress. Rescan range revisits available records for corrections; Export this page downloads displayed rows.",
            "For Binance deposits/withdrawals or Bybit on-chain withdrawals, select the account and enable Pending updates per stream. Choose 5 minutes, 15 minutes or 1 hour. Check now explicitly retries missing records; Turn off stops future checks.",
            "Expand Recent history sync to choose a 24-hour, 7-day or 30-day lookback and enable scans for an implemented Binance/Kraken/Bybit stream. Scan now queues a fresh window. Use a record's Source record → Observed versions to inspect locally observed changes.",
        ),
        (
            "Completed totals exclude pending, restricted and failed observations. Funding records do not establish investment returns or acquisition cost.",
            "Pending updates only revisit existing unfinished records. Five exhausted misses require review, not a completion/cancellation assumption. Pausing imports or deactivating the account disables updates. Kraken's source contains posted entries, not pending requests. Recent history sync or manual range imports handle completed corrections and new funding separately.",
            "Recent sync can find new funding and completed corrections inside its chosen window. Older/late-outside-window records and provider retention remain gaps. Missing records are retained, and observed revisions are not a complete native correction history. Unfetched intervals remain flagged until a completed import/scan covers them; this is not settlement verification.",
            "Kraken posted ledger effects subtract the same-asset fee from the signed amount. Other fee conventions require explicit review. Changed source facts invalidate a local review. Reviews affect new Balance checks, not transfer ownership or FIFO basis.",
        ),
    ),
    "transfers": Guide(
        "Review transfers between your own accounts",
        "/trade?tab=history",
        (
            "From Funding, choose Reconcile transfers and inspect a suggestion or use Match records.",
            "Compare both source records before Confirm own-account transfer; unusual timing or differing amounts require a review note.",
            "For fee-bearing links use Review amount & fee allocation. Recalculate Performance to inspect carried lots and unapplied links.",
            "For splits/merges open Split & merged transfers → Create group. Select 3–16 same-asset funding records, explain fee inclusion, enter the principal matrix and preview its exact conservation. Confirm ownership, configured-wallet scope and your evidence note before saving. Use Performance → Across pairs for group lot carryover; open Review for changed facts or withdraw the group to release records.",
        ),
        (
            "Suggestions are heuristics and confirmations are user assertions. Changed sources need review; an unmatched deposit is not automatically external cash flow or known basis.",
        ),
    ),
    "risk": Guide(
        "Create account-value and concentration alerts",
        "/alerts?tab=risk",
        (
            "Open Alerts → Account risk and pin a fixed set of active accounts in one environment plus a reference feed.",
            "Choose a value floor, asset/top-three/HHI concentration, observed-value drawdown, or hourly historical basket volatility/95% daily expected shortfall. For historical watches choose up to eight currently held assets and 60/90/180 days, then arm the rule. Evidence retains dated basket weights and subset coverage; it is not account performance or a future loss guarantee.",
            "Use View evidence for retained valuation details and Inbox for notices. A rule’s Delivery control can opt into Telegram, Discord, Slack, Signal, WhatsApp or email notifications with a checked private recipient, cooldown and freshness window. Edits save paused; Resume starts a new observation window.",
        ),
        (
            "Rules require complete usable valuation coverage. Drawdown includes cash movements and is not cash-flow-adjusted return. Alerts do not control trading.",
        ),
    ),
}
