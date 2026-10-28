"""Account and retained accounting workflows; these instructions never read funds."""

from typing import Literal

from sibyl.agents.guides import Guide

Topic = Literal[
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
            "Inspect a holding's valuation details for its reference feed, conversion path and provider time.",
            "Review unpriced assets and account errors; the displayed total only covers quantities that can be valued.",
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
            "Choose Performance in Account history and select an account, exact market and environment.",
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
        ),
        (
            "Completed totals exclude pending, restricted and failed observations. Funding records do not establish investment returns or acquisition cost.",
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
            "Choose a value floor, asset concentration or observed-value drawdown threshold, then explicitly arm the rule.",
            "Use View evidence for retained valuation details and Inbox for notices. Edits save paused; Resume starts a new observation window.",
        ),
        (
            "Rules require complete usable valuation coverage. Drawdown includes cash movements and is not cash-flow-adjusted return. Alerts do not control trading.",
        ),
    ),
}
