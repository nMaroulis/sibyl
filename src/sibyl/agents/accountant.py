"""Accountant explains holdings, retained accounting evidence and Account workflows.

Typed evidence tools use existing accounting services. The separate page_help
tool retrieves user instructions without accessing funds or changing records.
"""

import json
from typing import Annotated

from protolink import Agent, Tool, ToolRejectedError
from pydantic import Field

from sibyl.accounting.executions.service import ASSET
from sibyl.agents.guides import read_guide
from sibyl.agents.guides.accountant import GUIDES, Topic
from sibyl.agents.utils.common import COMMON_PROMPT, Services, page_context, selected

NAME = "Accountant"
TAGLINE = "Know what you own"
DESCRIPTION = "Explain account holdings, valuation, retained fills, FIFO performance, funding and transfers; guide Account workflows."
SYSTEM_PROMPT = (
    "Use account_asset_books for cross-pair account/asset FIFO and dated fee conversions; unknown basis and approximate candle marks remain qualified. "
    "Use basket_risk for saved current-weight historical covariance/tail studies. These are frictionless daily-rebalanced basket descriptions, not measured account performance, optimized allocations or future risk probabilities. Disclose subset coverage, dates and sample size. "
    "Use investment_returns for cash-flow-adjusted measured periods. Source-bound values and completeness reviews are user assertions, not audited provider guarantees. Missing coverage, stale reviews or ambiguous boundaries mean the return is unavailable; do not substitute raw value growth or FIFO profit. "
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
    "Recent funding sync covers only its selected rolling window. Explain local observed changes as "
    "observations, not a provider's complete revision log; missing records are not cancellation proof. "
    "A completed pass or rescan only exhausts available provider pages, not complete account history. "
    "Missing records are not deleted by rescans, and provider retention can hide old corrections. "
    "For saved balance checkpoints or unexplained quantity changes call balance_check_report. "
    "This compares observed native quantities with retained activity, not investment returns or complete reconciliation. "
    "Missing history, timing boundaries, historical corrections and funding fee inclusion can leave expected balances unknown. "
    "Never repair a difference, replace a checkpoint or claim a saved check is a live balance read. "
    "Account allocation includes value-weighted HHI, top-three concentration and effective asset count only when all selected accounts/assets are priced. These combine duplicate assets, include cash/stablecoins separately and are not correlation-adjusted diversification or investment risk scores. "
    "For saved account risk rules, notices and retained valuation samples call risk_alerts. It is passive; "
    "never imply you created a watch or continuously monitor. Explain value floors, per-asset/top-three concentration, HHI on a 0–100 scale "
    "and drawdown from an observed account-value peak. Deposits and withdrawals affect that peak; this is "
    "not investment return or a cash-flow-adjusted loss. Missing/undated/stale values cannot trigger or "
    "recover risk alerts. Fixed account sets and test/Demo/production funds remain separate. "
)


def create_agent(services: Services, **runtime) -> Agent:
    """Register this specialist's evidence and help tools on a native Agent.

    Args:
        services: Workspace domain services; credentials stay in their owners.
        **runtime: AgentGroup configuration, including the lazy model factory,
            native state, worker defaults and context policy.

    Returns:
        An unstarted Agent. Static guides run inline; domain reads inherit the
        runtime's execution policy (bounded threads in Sibyl). AgentGroup owns
        startup and shutdown.
    """
    portfolio = services.portfolio
    performance, funding, transfers = services.performance, services.funding, services.transfers

    def investment_returns(
        period_id: str | None = None, flow_offset: Annotated[int, Field(ge=0, le=2000)] = 0
    ) -> dict:
        """Read a saved account return period with external-flow adjustments, boundary valuations and
        coverage. Omit period_id for the page selection. Returns actual missing-basis/price/flow
        evidence; incomplete inputs cannot establish investment performance. Never imports or
        classifies transactions.
        """
        if not performance:
            return {"available": False, "items": []}
        identity = selected("return_period_id", period_id)
        if not identity:
            return performance.returns.list(selected("portfolio_scope", None, "all"))
        try:
            report = performance.returns.detail(identity)
            result = {
                key: report[key]
                for key in (
                    "id",
                    "label",
                    "source",
                    "environment",
                    "method",
                    "result",
                    "account_results",
                    "blockers",
                    "note",
                    "coverage",
                    "evidence_fingerprint",
                )
            }
            result["valuations"] = {
                stage: {
                    account: {key: sample[key] for key in ("total", "currency", "started_at", "as_of")}
                    for account, sample in (report[stage] or {}).items()
                }
                for stage in ("opening", "closing")
            }
            return {
                "kind": "account_return_period",
                **result,
                "flows": report["flows"][flow_offset : flow_offset + 20],
                "flow_offset": flow_offset,
                "flow_limit": 20,
                "flow_count": len(report["flows"]),
                "url": f"/account?scope={report['scope']}&period={identity}",
            }
        except LookupError as exc:
            raise ToolRejectedError(
                "That measured period is not retained.",
                code="return_period_not_found",
                suggestion="List current periods instead of inventing an ID.",
            ) from exc

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
        evidence = portfolio.risk_alerts.journal.evidence(rule_id) if rule_id else None
        if evidence and (evidence.get("sample") or {}).get("basket"):
            # Full converted observations remain in the UI journal, outside the model context.
            evidence["sample"]["basket"].pop("converted_closes", None)
        return {
            "rules": portfolio.risk_alerts.rules(),
            "recent_notifications": [
                {**json.loads(row["payload"]), "created_at": row["created_at"]} for row in rows
            ],
            "evidence": evidence,
            "url": "/alerts?tab=risk",
            "scope": "Read-only saved evidence. Values include cash movements; drawdown is not investment return. Historical basket watches use current weights, dated consecutive daily history and empirical tails, never future loss guarantees. This tool cannot change rules, trade or send messages. Optional Telegram, Discord, Slack, Signal, WhatsApp or email delivery is selected separately for each rule with a checked private recipient.",
        }

    def account_history(account_id: str = "", symbol: str = "") -> dict:
        """Inspect imported spot fills, fees and history-import coverage for an account or market.

        Filter by account_id and an exact symbol such as ETH/USDT, or omit either for
        a broader selection. Returns up to ten fills plus import progress and provider
        retention limits. A selected accounting report keeps its own report scope.
        Use page_help(topic='history') for instructions on starting an import.
        """
        if any(
            page_context().get(view)
            for view in ("transfer_view", "funding_view", "performance_view", "account_books_view")
        ):
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
        """Read saved account balance reconciliation, explaining matched assets and missing
        historical/opening evidence. Omit account_id for the selected account. Differences do not
        prove a missing deposit or authorize an adjustment. Never refreshes balances or changes the
        ledger.
        """
        if any(
            page_context().get(view)
            for view in ("transfer_view", "funding_view", "performance_view", "account_books_view")
        ):
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
        group_id: Annotated[str | None, Field(pattern=r"^[a-f0-9]{32}$")] = None,
        asset: str = "",
        kind: str = "",
        status: str = "",
    ) -> dict:
        """Read the selected combined, exchange or individual account view and its valuation evidence.
        Omit scope to follow the page. Demo/test funds, missing prices and incomplete totals are
        explicit. Uses active accounts; setup instructions need no account read. Never trades or
        activates accounts. Set group_id from observed evidence to inspect a split/merged transfer review.
        """
        if group_id:
            group = transfers.groups.detail(group_id)
            reviewed = group["reviewed"]
            return {
                "view": "transfer_group",
                "id": group["id"],
                "status": group["status"],
                "revision": group["revision"],
                "review_note": group["review_note"],
                "changed_members": group["changed_members"],
                "reviewed": {
                    **{
                        key: reviewed[key]
                        for key in (
                            "asset",
                            "environment",
                            "source_debit",
                            "destination_credit",
                            "fee_quantity",
                            "lot_order",
                            "edges",
                            "warnings",
                            "note",
                        )
                    },
                    **{
                        side: [
                            {
                                "event_id": leg["event"]["id"],
                                "account": leg["event"]["account"],
                                "reported_quantity": leg["event"]["quantity"],
                                "amount": leg["amount"],
                                "fee": leg["fee"],
                                "wallet_quantity": leg["wallet_quantity"],
                                "principal": leg["principal"],
                            }
                            for leg in reviewed[side]
                        ]
                        for side in ("outgoing", "incoming")
                    },
                },
            }
        selection = page_context()
        if selection.get("account_books_view") and not any(
            selection.get(view) for view in ("transfer_view", "funding_view", "performance_view")
        ):
            return account_asset_books()
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
                "groups": [
                    {
                        "id": group["id"],
                        "status": group["status"],
                        "asset": group["reviewed"]["asset"],
                        "source_debit": group["reviewed"]["source_debit"],
                        "destination_credit": group["reviewed"]["destination_credit"],
                        "fee_quantity": group["reviewed"]["fee_quantity"],
                        "changed_members": group["changed_members"],
                        "note": group["reviewed"]["note"],
                    }
                    for group in transfers.groups.report(account_id, asset, environment, limit=5)["items"]
                ]
                if transfers and not example
                else [],
                "evidence_group_limit": 5,
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
                "pending_updates": [
                    {
                        key: row[key]
                        for key in (
                            "account_id",
                            "stream",
                            "enabled",
                            "interval_minutes",
                            "status",
                            "last_checked_at",
                            "error",
                        )
                    }
                    for row in funding.refresh.ledger.snapshot()
                    if (not account_id or row["account_id"] == account_id)
                    and (not kind or row["stream"] == kind)
                    and (not environment or row["environment"] == environment)
                ][:10]
                if funding and not example
                else [],
                "pending_update_policy_limit": 10,
                "recent_sync": [
                    {
                        key: row[key]
                        for key in (
                            "account_id",
                            "stream",
                            "enabled",
                            "interval_minutes",
                            "lookback_days",
                            "status",
                            "last_checked_at",
                            "inserted",
                            "updated",
                            "uncovered_gap_count",
                            "error",
                        )
                    }
                    for row in funding.scans.ledger.snapshot()
                    if (not account_id or row["account_id"] == account_id)
                    and (not kind or row["stream"] == kind)
                    and (not environment or row["environment"] == environment)
                ][:10]
                if funding and not example
                else [],
                "recent_sync_policy_limit": 10,
            }
        if not performance_view:
            result = portfolio.overview(scope)
            return {key: value for key, value in result.items() if key != "history"}
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

    def account_asset_books(
        currency: Annotated[str | None, Field(pattern=ASSET)] = None,
        source: str | None = None,
    ) -> dict:
        """Explain retained cross-pair asset FIFO, fee conversions, transfer lots and unknown basis in one reporting unit."""
        page = page_context()
        if any(page.get(view) for view in ("transfer_view", "funding_view", "performance_view")):
            return accountant_snapshot()
        if page.get("account_books_view"):
            currency, source = (
                page.get("account_books_currency", "USDT"),
                page.get("market_source", "binance"),
            )
        if not performance:
            return {"available": False, "url": "/trade?tab=history&history_view=performance"}
        result = performance.account_books.report(
            selected("performance_account_id", None, ""),
            selected("performance_environment", None, ""),
            selected("account_books_currency", currency, "USDT"),
            selected("market_source", source, "binance"),
        )
        return {
            **{
                key: result[key]
                for key in (
                    "currency",
                    "source",
                    "method",
                    "as_of",
                    "input_fingerprint",
                    "fill_count",
                    "funding_count",
                    "note",
                    "complete_history",
                )
            },
            "reports": [
                {
                    "environment": group["environment"],
                    "items": group["items"][:30],
                    "asset_count": len(group["items"]),
                    "disposals": group["disposals"][:12],
                    "conversions": group["conversions"][:12],
                    "transfers": group["transfers"][:6],
                }
                for group in result["reports"]
            ],
            "kind": "account_asset_books",
            "url": "/trade?tab=history&history_view=performance",
        }

    agent = Agent(
        name="sibyl-accountant",
        description=DESCRIPTION,
        tools=[
            accountant_snapshot,
            balance_check_report,
            account_history,
            risk_alerts,
            Tool.from_callable(page_help, sync_execution="inline"),
            investment_returns,
            account_asset_books,
        ],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )

    @agent.tool
    def basket_risk(study_id: str | None = None) -> dict:
        """Read or list saved historical basket-risk studies using study_id/page scope.

        Explain volatility, correlations, variance contributions and historical tails.
        Disclose weights, coverage, dates and assumptions: these are neither measured
        account returns nor future-loss guarantees. Setup: page_help(basket_risk).
        """
        identity = selected("risk_study_id", study_id, "")
        if not identity:
            return {
                "kind": "basket_risk_study",
                **portfolio.risk.list(selected("portfolio_scope", None, "all")),
                "url": "/account",
            }
        result = portfolio.risk.get(identity)
        return {
            "kind": "basket_risk_study",
            **{
                key: value
                for key, value in result.items()
                if key not in {"inputs", "valuation", "daily_returns", "accounts"}
            },
            "url": "/account",
        }

    agent.card.capabilities.delegation = False
    return agent
