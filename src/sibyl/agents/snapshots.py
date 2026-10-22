"""Deterministic tool selection and presentation when no model is configured."""

from sibyl.models import AgentRequest


def tool_arguments(request: AgentRequest) -> dict:
    """Map the page's validated selection to the module's explicit native tool arguments."""
    context = request.context
    if request.module == "accountant" and context.transfer_view:
        return {
            "transfer_view": True,
            "account_id": context.funding_account_id or "",
            "asset": context.funding_asset or "",
            "environment": context.funding_environment or "",
            "example": bool(context.transfer_example),
        }
    if request.module == "accountant" and context.funding_view:
        return {
            "funding_view": True,
            "account_id": context.funding_account_id or "",
            "asset": context.funding_asset or "",
            "kind": context.funding_kind or "",
            "status": context.funding_status or "",
            "environment": context.funding_environment or "",
            "example": bool(context.funding_example),
        }
    if request.module == "accountant" and context.performance_view:
        return {
            "performance_view": True,
            "account_id": context.performance_account_id or "",
            "symbol": context.symbol or "",
            "environment": context.performance_environment or "",
            "example": bool(context.performance_example),
            "transfers_example": bool(context.performance_transfer_example),
            "fee_example": bool(context.performance_fee_example),
        }
    if request.module in {"oracle", "accountant"}:
        return {"scope": context.portfolio_scope or "all"}
    if request.module == "wiki":
        if context.crypto_id:
            return {"crypto_id": context.crypto_id}
        return {"query": context.query or request.message}
    if request.module in {"analyst", "chronos"}:
        args = {"symbol": context.symbol or "BTC/USDT"}
        if request.module == "analyst":
            args.update(timeframe=context.timeframe or "1d", limit=context.limit or 180)
            if context.market_source:
                args["source"] = context.market_source
        if request.module == "chronos":
            args["horizon"] = context.horizon or 14
        return args
    if request.module == "stocks":
        return {"symbol": context.equity_symbol or "AAPL"}
    if request.module == "broker":
        if context.job_id:
            return {"job_id": context.job_id}
        if context.parameters:
            return {"parameters": context.parameters.model_dump()}
        return {"symbol": context.symbol or "BTC/USDT"}
    if request.module == "reporter":
        return {
            "article_id": context.article_id or "",
            "mode": context.news_mode or "",
            "publisher": context.news_publisher or "",
            "asset": context.news_asset or "",
            "sentiment": context.news_sentiment or "",
            "q": context.query or "",
            "days": context.news_days if context.news_days is not None else 7,
        }
    return {}


def snapshot_answer(module: str, evidence) -> str:
    """Format actual tool output when language-model inference has not been configured."""
    if module in {"oracle", "accountant"}:
        if evidence.get("view") == "transfers":
            return (
                ("Example reconciliation. " if evidence.get("example") else "")
                + f"{evidence['total']} saved transfer links in this selection, with {len(evidence['candidates'])} suggestions included for review. "
                + evidence["note"]
            )
        if evidence.get("view") == "funding":
            return (
                ("Example movements. " if evidence.get("example") else "")
                + f"{evidence['total']} matching funding records. "
                + "; ".join(
                    f"{row['account']} / {row['environment']}: {row['quantity']:,.8f} {row['asset']} {row['kind']} ({row['direction']})"
                    for row in evidence["summaries"][:12]
                )
                + ". "
                + evidence["note"]
            )
        if evidence.get("view") == "performance":
            totals = "; ".join(
                f"{row['environment']} / {row['quote']}: "
                + (
                    f"net matched realized {row['net_matched_realized']:,.4f} {row['quote']}"
                    if row["net_matched_realized"] is not None
                    else "net matched realized unavailable; review coverage issues"
                )
                for row in evidence["totals"]
            )
            return (
                ("Example calculation. " if evidence.get("example") else "")
                + f"{evidence['fill_count']} retained fills. {totals or 'No retained market history.'} {evidence['note']}"
            )
        if not evidence.get("active", True):
            return "No accounts are active. Connect one or many exchange accounts in Settings, or explicitly enable Demo preview to explore virtual balances. Public markets and research remain available."
        top = evidence["holdings"][0] if evidence["holdings"] else None
        text = f"Your priced portfolio is {evidence['total']:,.2f} USDT across {len(evidence['holdings'])} assets. "
        if top:
            text += f"{top['name']} is the largest position at {top['allocation']:.1f}%. "
        return text + f"Data source: {evidence['source']}. " + " ".join(evidence["warnings"])
    if module == "analyst":
        if "rsi" not in evidence:
            return f"{evidence['symbol']}: {evidence['price']:,.4f}. Source: {evidence['source_label']}. {evidence['note']}"
        return f"{evidence['symbol']}: RSI {evidence['rsi']:.1f}, {evidence['trend'].lower()} EMA alignment, annualized return volatility {evidence['volatility']:.1f}%. Source: {evidence['source']}. These describe the observed sample and do not guarantee future moves."
    if module == "wiki" and isinstance(evidence, dict):
        asset = evidence["asset"]
        profile, history = (evidence.get("profile") or {}, evidence.get("history") or {})
        overview = (
            profile.get("description")
            or history.get("introduction")
            or "Source information is currently unavailable."
        )
        sections = history.get("sections", [])
        history_text = "\n\n" + sections[0]["title"] + ": " + sections[0]["text"][:1000] if sections else ""
        warnings = " ".join(item["error"] for item in evidence["sources"] if item.get("error"))
        return f"{asset['name']} ({asset['symbol']})\n\n{overview[:1800]}{history_text}\n\nSources: CoinPaprika / Wikipedia. {warnings}"
    if module == "wiki":
        return (
            "\n\n".join(f"{item['term']}: {item['text']}\n{item['url']}" for item in evidence)
            or "No glossary entries matched. Try RSI, diversification, backtesting, or API key permissions."
        )
    if module == "chronos":
        point = evidence["points"][-1]
        return f"The {evidence['horizon']} day log-return baseline ends at {point['value']:,.2f}, with an approximate interval of {point['lower']:,.2f}–{point['upper']:,.2f}. Source: {evidence['source']}. This is an uncalibrated statistical baseline, not a trained model."
    if module == "broker" and evidence.get("selected_run"):
        run = evidence["selected_run"]
        selected = evidence["selected_parameters"]
        return f"{selected['strategy']} on {selected['symbol']}: {run['status']} · paper execution. Current equity {run['equity']:,.4f} {selected['symbol'].split('/')[1]}. {len(evidence['recent_events'])} recent events are included for inspection. Last worker check: {run['checked_at'] or 'pending'}."
    if module == "broker":
        selected = evidence["selected_parameters"]
        return f"Selected: {selected['strategy']} on {selected['symbol']}, {selected['candles']} candles and {selected['capital']:,.2f} {selected['symbol'].split('/')[1]} virtual capital. {len(evidence['catalog'])} strategies are available. {len(evidence['paper_jobs'])} paper jobs and {len(evidence['backtests'])} recent backtests are recorded. Backtests use next-open fills with fees and slippage. Paper strategies use isolated virtual capital."
    if module == "reporter":
        selected = evidence.get("selected_article")
        items = [selected] if selected else evidence["items"][:3]
        briefing = (
            "\n\n".join(
                f"{item['title']}\n{item['summary']}\n{item['publisher']} · {item['published_at'] or 'Undated'}"
                + (f"\n{item['url']}" if item.get("url") else " · Sample story")
                for item in items
            )
            or "No stories match this selection."
        )
        return f"Source: {evidence['source']}. {evidence['total']} matching stories.\n\n{briefing}\n\n{evidence['sentiment']['note']}"
    if module == "technician":
        return f"{len(evidence['connections'])} connections saved. Market mode: {evidence['mode']}. {evidence['permissions']} Use the connection check to verify saved credentials."
    if module == "explorer":
        return f"{len(evidence['items'])} recent Bitcoin blocks available. Latest displayed height: {evidence['items'][0]['height']:,}. Source: {evidence['source']}."
    return f"{evidence['name']} ({evidence['symbol']}): {evidence['price']:,.2f} {evidence['currency']}. Source: {evidence['source']}."
