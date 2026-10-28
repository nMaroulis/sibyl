"""Accountant explains holdings, retained accounting evidence and Account workflows.

Typed evidence tools use existing accounting services. The separate page_help
tool retrieves user instructions without accessing funds or changing records.
"""

import json

from protolink import Agent

from sibyl.agents.common import COMMON_PROMPT, Services, page_context, selected
from sibyl.agents.guides import read_guide
from sibyl.agents.guides.accountant import GUIDES, Topic

NAME = "Accountant"
TAGLINE = "Know what you own"
DESCRIPTION = "Explain account holdings, valuation, retained fills, FIFO performance, funding and transfers; guide Account workflows."
SYSTEM_PROMPT = (
    "For how-to or navigation questions call page_help; instructions do not require reading balances. "
    "Read holdings and accounting reports through accountant_snapshot. Page-selected funding, "
    "performance and transfer reports are fixed selections; do not switch to balances or another view. "
    "Ask for missing account or market details. Value holdings in the supplied currency using the "
    "supplied conversion paths. Disclose partial coverage, unpriced quantities, account errors and "
    "undated quotes. Never assume stablecoins or fiat equal USDT, infer missing cost basis, or call "
    "daily price moves investment returns. For performance evidence, distinguish matched market FIFO "
    "from account returns. Disclose excluded unknown-cost sales, unconverted fees, timestamp ambiguity "
    "and cross-market gaps. Never describe provisional figures as final net P&L. Opening inventory is a "
    "user assertion. Keep accounts, environments and quote currencies distinct. Funding observations "
    "are reported native quantities, not returns. Use returned balance_effect provenance to distinguish "
    "documented provider rules from user-reviewed fee/wallet conventions; never present a local review "
    "as a provider fact or create/withdraw reviews. Unknown wallet scopes or fee conventions stay unknown. "
    "Never infer fee inclusion, own-account transfers, "
    "complete history or cost basis from a deposit. Pending/restricted/unknown movements are not "
    "completed totals. Transfer suggestions are heuristics. Confirmed links are user assertions, and "
    "changed sources need review. Unlinked observations are unreviewed, not established external cash "
    "flows. Never confirm links or infer transferred cost basis. Performance evidence may carry "
    "original lots for current zero-fee links or explicit balanced same-asset fee allocations. Fee "
    "inventory cost is separate from trading P&L, not an expense valuation or tax conclusion. Use only "
    "its applied/unapplied status and lot provenance; unknown costs or dates are not zero or receipt "
    "dates. For imported execution history, corrections or sync coverage, call account_history. "
    "A completed pass or rescan only exhausts available provider pages, not complete account history. "
    "Missing records are not deleted by rescans, and provider retention can hide old corrections. "
    "For saved balance checkpoints or unexplained quantity changes call balance_check_report. "
    "This compares observed native quantities with retained activity, not investment returns or complete reconciliation. "
    "Missing history, timing boundaries, historical corrections and funding fee inclusion can leave expected balances unknown. "
    "Never repair a difference, replace a checkpoint or claim a saved check is a live balance read. "
    "For saved account risk rules, notices and retained valuation samples call risk_alerts. It is passive; "
    "never imply you created a watch or continuously monitor. Explain value floors, asset concentration "
    "and drawdown from an observed account-value peak. Deposits and withdrawals affect that peak; this is "
    "not investment return or a cash-flow-adjusted loss. Missing/undated/stale values cannot trigger or "
    "recover risk alerts. Fixed account sets and test/Demo/production funds remain separate. "
)


def create_agent(services: Services, **runtime) -> Agent:
    """Declare Accountant's tools and expose them through ProtoLink's runtime transport."""
    portfolio = services.portfolio
    performance, funding, transfers = services.performance, services.funding, services.transfers

    def portfolio_snapshot(scope: str = "all") -> dict:
        """Read priced holdings, source labels, warnings, and account allocation."""
        result = portfolio.overview(scope)
        return {key: value for key, value in result.items() if key != "history"}

    def risk_alerts(rule_id: str = "") -> dict:
        """Inspect account-risk rules and recent notices to explain what a saved watch observed.

        Supply a known rule_id for its retained valuation evidence and matching notices;
        omit it to list rules and the latest ten notices. This is recorded alert evidence,
        not a current account valuation or a newly created watch.
        """
        with services.store.db() as db:
            rows = db.execute(
                "SELECT payload,created_at FROM alert_notifications "
                "WHERE json_extract(payload,'$.kind')='risk' "
                "AND (?='' OR rule_id=?) ORDER BY created_at DESC,rowid DESC LIMIT 10",
                (rule_id, rule_id),
            ).fetchall()
        return {
            "rules": portfolio.risk_alerts.rules(),
            "recent_notifications": [
                {**json.loads(row["payload"]), "created_at": row["created_at"]} for row in rows
            ],
            "evidence": portfolio.risk_alerts.journal.evidence(rule_id) if rule_id else None,
            "url": "/alerts?tab=risk",
            "scope": "Read-only saved evidence. Values include cash movements; drawdown is not investment return. No execution or external delivery.",
        }

    def account_history(account_id: str = "", symbol: str = "") -> dict:
        """Inspect imported spot fills, fees and history-import coverage for an account or market.

        Filter by account_id and an exact symbol such as ETH/USDT, or omit either for
        a broader selection. Returns up to ten fills plus import progress and provider
        retention limits. A selected accounting report keeps its own report scope.
        Use page_help(topic='history') for instructions on starting an import.
        """
        if any(page_context().get(view) for view in ("transfer_view", "funding_view", "performance_view")):
            return accountant_snapshot()
        sync = services.account_sync
        if sync is None:
            return {"items": [], "note": "Account history service is unavailable."}
        state = sync.snapshot()
        return {
            **sync.ledger.fills(account_id=account_id, symbol=symbol, limit=10),
            "imports": [
                job
                for job in state["jobs"]
                if (not account_id or job["account_id"] == account_id)
                and (not symbol or job["symbol"] == symbol)
            ][:12],
            "provider_limits": [
                {"account_id": account["id"], "note": account["history_note"]}
                for account in state["accounts"]
                if not account_id or account["id"] == account_id
            ][:24],
            "evidence_record_limit": 10,
            "url": "/trade?tab=history",
        }

    def balance_check_report(account_id: str = "", asset: str = "") -> dict:
        """Explain saved balance comparisons, per-asset differences and missing accounting evidence.

        Use a saved account ID, or the page's individual account selection. Without
        one, list available accounts so the user can choose. Returns the latest
        saved comparison with at most forty asset rows. Supply an exact native
        asset code to inspect that asset, including one beyond those first rows.
        It does not read current
        balances, import history, replace checkpoints or alter exchange funds.
        """
        if any(page_context().get(view) for view in ("transfer_view", "funding_view", "performance_view")):
            return accountant_snapshot()
        checks = services.balance_checks
        if checks is None:
            return {"note": "Balance checks are unavailable.", "url": "/account"}
        scope = page_context().get("portfolio_scope") or "all"
        if not account_id and scope.startswith("account:"):
            account_id = scope[8:]
        if not account_id:
            return {
                **checks.accounts(scope),
                "note": "Choose one account for its saved balance check.",
                "url": "/account",
            }
        state = checks.journal.state(account_id)
        report = state["latest"]
        matching = [row for row in report["rows"] if not asset or row["asset"] == asset] if report else []
        return {
            "view": "balance_check",
            "checkpoint": state["checkpoint"],
            "configuration_changed": state["configuration_changed"],
            "report": {
                **report,
                "rows": matching[:40],
                "funding_evidence": [
                    item for item in report.get("funding_evidence", []) if not asset or item["asset"] == asset
                ][:40],
            }
            if report
            else None,
            "selected_asset": asset or None,
            "total_rows": len(report["rows"]) if report else 0,
            "matching_rows": len(matching),
            "evidence_row_limit": 40,
            "url": f"/account?scope=account%3A{account_id}",
        }

    def accountant_snapshot(
        scope: str = "all",
        performance_view: bool = False,
        account_id: str = "",
        symbol: str = "",
        environment: str = "",
        example: bool = False,
        transfers_example: bool = False,
        fee_example: bool = False,
        funding_view: bool = False,
        transfer_view: bool = False,
        asset: str = "",
        kind: str = "",
        status: str = "",
    ) -> dict:
        """Explain the selected Account holdings or retained accounting report from its evidence.

        Defaults to the page's report and filters. Holdings use scope='all', an exchange
        scope or account scope. For explicit report requests choose performance_view,
        funding_view or transfer_view with account_id, exact symbol or asset and environment.
        Returns valuation coverage or retained FIFO/funding/transfer evidence and limitations.
        Selected report/example views cannot be switched to balances or another report.
        example and the example variants are only for explicitly requested illustrative data.
        """
        selection = page_context()
        # Offline report selections cannot turn into private balance reads, even if a model asks.
        if selection.get("transfer_view"):
            transfer_view, example = True, bool(selection.get("transfer_example"))
            account_id, asset, environment = (
                selection.get(k) or "" for k in ("funding_account_id", "funding_asset", "funding_environment")
            )
        elif selection.get("funding_view"):
            transfer_view, funding_view, example = False, True, bool(selection.get("funding_example"))
            account_id, asset, kind, status, environment = (
                selection.get(k) or ""
                for k in (
                    "funding_account_id",
                    "funding_asset",
                    "funding_kind",
                    "funding_status",
                    "funding_environment",
                )
            )
        elif selection.get("performance_view"):
            transfer_view, funding_view, performance_view = False, False, True
            account_id, symbol, environment = (
                selection.get(k) or ""
                for k in ("performance_account_id", "symbol", "performance_environment")
            )
            example = bool(selection.get("performance_example"))
            transfers_example, fee_example = (
                bool(selection.get("performance_transfer_example")),
                bool(selection.get("performance_fee_example")),
            )
        scope = selected("portfolio_scope", scope if scope != "all" else None, "all")
        if transfer_view:
            result = (
                transfers.example()
                if transfers and example
                else transfers.report(account_id, asset, environment, limit=10)
                if transfers
                else {
                    "items": [],
                    "candidates": [],
                    "total": 0,
                    "note": "Transfer review service is unavailable.",
                }
            )
            return {
                **result,
                "view": "transfers",
                "candidates": result["candidates"][:6],
                "evidence_link_limit": 10,
                "evidence_suggestion_limit": 6,
            }
        if funding_view:
            result = (
                funding.example()
                if funding and example
                else funding.ledger.events(account_id, asset, kind, status, environment, limit=10)
                if funding
                else {
                    "items": [],
                    "total": 0,
                    "summaries": [],
                    "fees": [],
                    "note": "Funding service unavailable.",
                }
            )
            return {
                **result,
                "view": "funding",
                "evidence_record_limit": 10,
                "imports": [
                    row
                    for row in funding.snapshot()["jobs"]
                    if not account_id or row["account_id"] == account_id
                ]
                if funding and (not example)
                else [],
            }
        if not performance_view:
            return portfolio_snapshot(scope)
        if performance is None:
            return {
                "view": "performance",
                "items": [],
                "totals": [],
                "fill_count": 0,
                "note": "Performance service is unavailable.",
            }
        result = (
            performance.transfer_example(fee_example)
            if example and transfers_example
            else performance.example()
            if example
            else performance.report(account_id, symbol, environment)
        )

        def transfer_evidence(items, limit):
            return [
                {
                    **item,
                    "lots": item["lots"][:5],
                    **{
                        side: {**item[side], "lots": item[side]["lots"][:5]}
                        for side in ("outgoing_fee_evidence", "incoming_fee_evidence")
                        if item.get(side)
                    },
                }
                for item in items[:limit]
            ]

        return {
            **result,
            "view": "performance",
            "transfer_evidence": transfer_evidence(result.get("transfer_evidence", []), 6),
            "items": [
                {
                    **{key: value for key, value in row.items() if key not in {"curve", "disposals"}},
                    "recent_disposals": row["disposals"][:10],
                    "basis_transfers": transfer_evidence(row.get("basis_transfers", []), 3),
                }
                for row in result["items"][:20]
            ],
            "evidence_market_limit": 20,
            "evidence_transfer_limit": 6,
            "evidence_transfer_per_market_limit": 3,
            "evidence_lot_limit": 5,
        }

    def page_help(topic: Topic = "overview") -> dict:
        """Explain Account workflows: combined accounts, valuation, history, FIFO, funding, transfers or risk alerts.

        Choose a topic for concrete UI steps, limitations and a destination link.
        Use overview for orientation; use the evidence tools for the user's actual figures.
        """
        return read_guide(GUIDES, topic)

    agent = Agent(
        name="sibyl-accountant",
        description=DESCRIPTION,
        tools=[
            accountant_snapshot,
            balance_check_report,
            account_history,
            risk_alerts,
            page_help,
        ],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent
