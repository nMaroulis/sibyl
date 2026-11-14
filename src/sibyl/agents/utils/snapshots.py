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
            "mode": context.news_mode,
            "publisher": context.news_publisher or "",
            "asset": context.news_asset or "",
            "sentiment": context.news_sentiment or "",
            "q": context.query or "",
            "days": context.news_days if context.news_days is not None else 7,
        }
    return {}


def snapshot_answer(module: str, evidence) -> str:
    """Format actual tool output when language-model inference has not been configured."""
    if (
        isinstance(evidence, dict)
        and isinstance(evidence.get("calibration"), dict)
        and evidence["calibration"].get("abstained")
    ):
        return "Search withheld its evidence. " + evidence["calibration"].get(
            "note",
            "The leading passage did not meet the cutoff. This does not establish that the claim is false.",
        )
    if isinstance(evidence, dict) and evidence.get("kind") == "account_asset_books":
        assets = sum(row["asset_count"] for row in evidence["reports"])
        return f"Cross-pair FIFO: {evidence['fill_count']} retained dependency fills across {assets} account/asset books, reported in {evidence['currency']}.\n\n{evidence['note']}\n{evidence['url']}"
    if isinstance(evidence, dict) and evidence.get("kind") == "basket_risk_study":
        if "observations" not in evidence:
            return f"{len(evidence.get('items', []))} saved historical basket risk studies. Calculate a new study explicitly in Account.\n{evidence['url']}"
        return f"Historical basket risk: {evidence['observations']} consecutive daily returns. Annualized volatility {evidence['annualized_volatility_pct']:.2f}%; empirical daily 95% VaR {evidence['historical_var_95_pct']:.2f}%.\n{evidence['coverage_note']}\nCurrent-weight hypothetical basket, not measured account performance or a forecast.\n{evidence['url']}"
    if isinstance(evidence, dict) and evidence.get("kind") == "retrieval_calibration":
        result = evidence.get("calibration")
        if result:
            validation = result["validation"]
            return f"Semantic calibration: {validation['correct_accepts']}/{validation['answerable']} relevant held-out questions accepted; {validation['incorrect_accepts']} incorrect accepts. Cutoff {result['threshold']!r}. This is empirical retrieval evidence, not answer confidence. Activation is separate.\n{evidence['url']}"
        return f"Calibration {evidence.get('state', 'catalog')}; no completed cutoff evidence.\n{evidence['url']}"
    if isinstance(evidence, dict) and evidence.get("kind") == "retrieval_evaluation":
        if "state" not in evidence:
            return f"{len(evidence.get('items', []))} saved retrieval evaluations. Open Retrieval quality lab to label passages or inspect a report.\n{evidence['url']}"
        methods = ", ".join(evidence["methods"])
        return f"{evidence['title']}: {evidence['state']} · {evidence['completed']}/{evidence['total']} queries · top {evidence['k']} · {methods}.\n\n{evidence['note']}\n{evidence['url']}"
    if isinstance(evidence, dict) and evidence.get("kind") == "account_return_period":
        result = evidence["result"]
        if result:
            ratio = f"{result['return_pct']:.2f}%" if result["return_pct"] is not None else "unavailable"
            return f"{evidence['label']}: gain {result['gain']:.2f} USDT, net external cash flow {result['net_external_flow']:.2f} USDT. Modified Dietz estimate: {ratio}.\n\n{evidence['note']}\n{evidence['url']}"
        return "Return unavailable. " + " ".join(evidence["blockers"]) + "\n" + evidence["url"]
    if isinstance(evidence, dict) and evidence.get("kind") == "forecast_outcomes":
        if "points" in evidence:
            return f"Live forecast outcomes: {evidence['observed']} targets observed, {evidence['pending']} awaiting actuals. Metrics are available only for observed targets.\n{evidence['note']}\n{evidence['url']}"
        return f"{len(evidence['items'])} tracked prospective forecasts. Historical research and live observations stay separate.\n{evidence['url']}"
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
    if module == "analyst" and evidence.get("granger"):
        result = evidence["granger"]
        readings = []
        for item in result["items"]:
            detail = (
                item["reason"] if item["p_value"] is None else f"adjusted p {item['adjusted_p_value']:.4g}"
            )
            held = item.get("held_out")
            if held and held["skill_vs_own_lags_pct"] is not None:
                detail += f", later-target MAE improvement {held['skill_vs_own_lags_pct']:.1f}% vs own lags"
            readings.append(f"{item['reference']} → {item['target']}: {detail}.")
        return (
            f"Granger lag research · order {result['lags']} · {result['observations']} consecutive returns · source {evidence['source_label']}.\n"
            + "\n".join(readings)
            + "\nClassical inference assumptions remain unverified. Request-family adjustment does not cover repeated experiments. Lag predictability is not causation or a profitable strategy."
        )
    if module == "analyst" and evidence.get("regression", {}).get("robust"):
        result = evidence["regression"]
        lines = []
        for item in result["items"]:
            fit = item.get("theil_sen")
            label = f"{item['target']} vs {item['reference']}"
            if fit:
                lines.append(f"- {label} · OLS beta {item['beta']:.3f} · Theil–Sen beta {fit['beta']:.3f}")
            else:
                lines.append(f"- {label} · {item['status'].replace('_', ' ')}")
        return (
            f"Same-interval return fit · {result['observations']} aligned observations · {evidence['source_label']}.\n"
            + "\n".join(lines)
            + "\n"
            + result["note"]
        )
    if module == "analyst":
        if "rsi" not in evidence:
            return f"{evidence['symbol']}: {evidence['price']:,.4f}. Source: {evidence['source_label']}. {evidence['note']}"

        def reading(value):
            return f"{value:.1f}" if value is not None else "unavailable"

        statistics = evidence["statistics"]
        assessment = statistics["assessment"]
        score = (
            f"{assessment['score']}/100 ({assessment['label'].lower()})"
            if assessment["score"] is not None
            else f"unavailable: {assessment['reason']}"
        )
        return (
            f"{evidence['symbol']}: technical bias {score}; RSI {reading(evidence['rsi'])}, "
            f"annualized return volatility {reading(evidence['volatility'])}%, "
            f"sample maximum drawdown {reading(statistics['risk']['max_drawdown_pct'])}%. "
            f"Source: {evidence['source']}; {evidence['timeframe']}; "
            f"{statistics['sample']['observations']} consecutive candles. "
            + " ".join(statistics["sample"]["warnings"])
            + " Higher bias means more bullish, not safer. These historical readings are not a trade recommendation."
        )
    if (
        module == "wiki"
        and isinstance(evidence, dict)
        and ("passages" in evidence or "document_id" in evidence)
    ):
        source = evidence.get("source", evidence)
        items = evidence.get("passages", [evidence])
        snippets = "\n\n".join(f"Page {part['page']}: {part['text']}\n{part['url']}" for part in items[:2])
        return f"Retained source: {source.get('title', 'Research document')}.\n\n{snippets}\n\nThis is a source excerpt, not an AI interpretation or verified fact. Open the reader for more passages; configure a model in /settings?tab=models for a reasoned answer."
    if module == "wiki" and isinstance(evidence, dict) and "retrieval" in evidence:
        excerpts = "\n\n".join(
            f"{item['source'].get('title', 'Retained source')} · page {item['page']}\n{item['text']}\n{item['url']}"
            for item in evidence["items"]
        )
        return (
            (
                excerpts
                or "No matching retained passages. An empty match does not establish that a claim is false."
            )
            + "\n\n"
            + evidence.get("note", "Exact excerpts, not AI interpretation or verified facts.")
        )
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
    if module == "chronos" and evidence.get("kind") == "rolling_evaluation":
        report = evidence["report"]
        score = report["aggregate"]["mae_skill_vs_naive_pct"]
        skill = "undefined" if score is None else f"{score:.2f}%"
        return (
            f"Saved rolling evaluation on {report['symbol']}: {len(report['folds'])} folds, "
            f"{report['aggregate']['samples']} held-out targets and pooled MAE skill vs naive {skill}. "
            f"Source: {report['source']}. Recorded: {report['created_at']}. "
            "Each fold refits the recipe; historical accuracy is not investment return or live forward performance."
        )
    if module == "chronos":
        point = evidence["points"][-1]
        if evidence.get("trained"):
            return (
                f"Trained research model v{evidence['model_version']} on {evidence['symbol']}: "
                f"the {evidence['horizon']}-day estimate is {point['value']:,.4f}, with a nominal 90% "
                f"empirical band of {point['lower']:,.4f}–{point['upper']:,.4f}. "
                f"Observation origin: {evidence['origin']}. Source: {evidence['source']}. "
                "Inspect the model's held-out test results; future coverage and profitable trades are not guaranteed."
            )
        return f"The {evidence['horizon']} day log-return baseline ends at {point['value']:,.2f}, with an approximate interval of {point['lower']:,.2f}–{point['upper']:,.2f}. Source: {evidence['source']}. This is an uncalibrated statistical baseline, not a trained model."
    if module == "broker" and evidence.get("kind") == "portfolio_backtest":
        label = "Demo · synthetic prices" if evidence["source"] == "demo" else "Recorded historical prices"
        return f"{label}. Portfolio study across {len(evidence['parameters']['legs'])} assets and {evidence['window']['count']} common candles: {evidence['return_pct']:+.2f}% net return, {evidence['rebalance_count']} executed rebalances and {evidence['fees']:.4f} {evidence['quote']} simulated fees. Difference versus buy-and-hold: {evidence['excess_return_pct']:+.2f} percentage points. Historical simulation; no running strategy or exchange orders."
    if module == "broker" and evidence.get("simulation"):
        label = (evidence.get("plugin") or {}).get("name", evidence["strategy"])
        return (
            (
                "Demo · synthetic input. "
                if evidence.get("source") == "demo"
                else "Recorded historical research. "
            )
            + f"{label} on {evidence['symbol']}: {evidence['return_pct']:+.2f}% net return, "
            + f"{evidence['trades']} simulated round trips and {evidence['fees']:.4f} fees. "
            + "These are saved simulated fills, not live account performance or established future profitability."
        )
    if module == "broker" and evidence.get("selected_adaptive"):
        study = evidence["selected_adaptive"]
        summary = study["summary"]
        result = summary["mean_return_pct"]
        performance = (
            f"Mean independent-window return: {result:.2f}%."
            if result is not None
            else "No eligible candidate produced an independent test result."
        )
        return f"Recorded {study['sampler']['name']} study on {study['dataset']['symbol']}. {summary['evaluated_windows']} tested windows. {performance} Training-only suggestions and later cash-reset tests are historical research, not a forecast or live deployment. Open the retained trial evidence in Strategies."
    if module == "broker" and evidence.get("selected_validation"):
        study = evidence["selected_validation"]
        plan = study.get("search")
        selection = (
            (
                f"{plan['method']} search, {plan['evaluated_candidates']} of {plan['space_size']} configurations evaluated"
                + (f", seed {plan['seed']}" if plan["seed"] is not None else "")
            )
            if plan
            else "recorded parameter search"
        )
        return (
            ("Demo study. " if study["dataset"]["source"] == "demo" else "")
            + f"{selection}. Mean later-window return: {study['summary']['mean_return_pct']:+.2f}%. "
            "These windows reset virtual cash; the mean is not a compounded account return. "
            "Inspect training rankings and untested combinations; repeated experiments can overfit."
        )
    if module == "broker" and evidence.get("selected_run"):
        run = evidence["selected_run"]
        selected = evidence["selected_parameters"]
        mode = run.get("mode")
        if mode not in {"paper", "exchange"}:
            return f"{selected['strategy']} on {selected['symbol']}: {run['status']}. Execution mode is unavailable; inspect the retained monitor before treating these observations as paper or exchange activity."
        if mode == "exchange":
            environment = run.get("environment") or "unspecified environment"
            equity = (
                f"Retained strategy equity {run['equity']:,.4f}"
                if run.get("equity") is not None
                else "Strategy equity unavailable"
            )
            return (
                f"{selected['strategy']} on {selected['symbol']}: {run['status']} · exchange execution · {environment}. "
                f"{equity} {selected['symbol'].split('/')[1]}. "
                f"{len(evidence['recent_events'])} recent events are included. "
                f"Last worker check: {run.get('checked_at') or 'pending'}. "
                "These are retained strategy observations, not a fresh exchange balance or proof that orders are settled. "
                + ("Some native fees remain unvalued. " if run.get("unvalued_fees") else "")
            )
        return f"{selected['strategy']} on {selected['symbol']}: {run['status']} · paper execution. Current virtual equity {run['equity']:,.4f} {selected['symbol'].split('/')[1]}. {len(evidence['recent_events'])} recent events are included for inspection. Last worker check: {run['checked_at'] or 'pending'}."
    if module == "broker":
        selected = evidence["selected_parameters"]
        return f"Selected: {selected['strategy']} on {selected['symbol']}, {selected['candles']} candles and {selected['capital']:,.2f} {selected['symbol'].split('/')[1]} virtual capital. {len(evidence['catalog'])} strategies are available. {len(evidence['strategy_jobs'])} saved strategy runs and {len(evidence['backtests'])} recent backtests are recorded. Backtests use next-open fills with fees and slippage. Paper strategies use isolated virtual capital."
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
        if evidence.get("kind") == "transaction":
            item = evidence["transaction"]
            confirmations = item["status"]["confirmations"]
            return (
                f"{'Demo transaction. ' if evidence['source'] == 'demo' else ''}"
                f"{item['txid']}: {confirmations if confirmations is not None else 'Unknown'} observed confirmations; "
                f"fee {item['fee_sats']:,} sat ({item['fee_rate_sat_vb']:.2f} sat/vB). "
                f"{item['input_count']} inputs and {item['output_count']} outputs. Source: {evidence['source']}. "
                + evidence["note"]
            )
        if evidence.get("kind") == "address":
            item = evidence["address"]
            return (
                f"{'Demo address. ' if evidence['source'] == 'demo' else ''}"
                f"Confirmed balance: {item['confirmed_balance_sats']:,} sat; pending change: {item['pending_delta_sats']:+,} sat. "
                f"{item['chain_stats']['tx_count']} indexed confirmed transactions; {len(evidence['history']['items'])} shown. "
                f"Source: {evidence['source']}. " + evidence["note"]
            )
        return f"{len(evidence['items'])} recent Bitcoin blocks available. Latest displayed height: {evidence['items'][0]['height']:,}. Source: {evidence['source']}."
    return f"{evidence['name']} ({evidence['symbol']}): {evidence['price']:,.2f} {evidence['currency']}. Source: {evidence['source']}."
