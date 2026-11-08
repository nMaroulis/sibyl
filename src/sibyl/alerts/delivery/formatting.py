"""Plain-text summaries from retained alert evidence; no model call or provider refresh."""


def alert_text(notice):
    """Explain the observed trigger, source, time and data environment without trading advice."""
    kind = notice.get("kind", "price")
    lines = ["Sibyl alert · " + (notice.get("label") or kind.title())]
    if kind == "price":
        comparison = {
            "above": "at or above",
            "below": "at or below",
            "crosses_above": "crossed to or above",
            "crosses_below": "crossed to or below",
        }[notice["condition"]]
        lines += [
            f"{notice['symbol']} {comparison} {notice['threshold']:g}",
            f"Observed price: {notice['price']:g}",
        ]
    elif kind == "risk":
        metric = {
            "volatility": "Basket annualized historical volatility",
            "tail_loss": "Basket historical daily 95% expected shortfall",
            "value_floor": "Account value floor",
            "concentration": "Asset concentration",
            "drawdown": "Observed-value drawdown",
            "hhi": "Asset concentration HHI",
            "top_three": "Top-three asset concentration",
        }[notice["metric"]]
        unit = (
            notice.get("currency", "USDT")
            if notice["metric"] == "value_floor"
            else "/ 100"
            if notice["metric"] == "hhi"
            else "%"
        )
        lines += [
            f"{metric} · {notice['action']}",
            f"Observed: {notice['metric_value']:g} {unit}",
            f"Limit: {notice['threshold']:g} · recovery: {notice['reset_threshold']:g} {unit}",
        ]
        if notice.get("basket_assets"):
            evidence = notice["basket"]
            lines += [
                "Selected basket: " + ", ".join(notice["basket_assets"]),
                f"{evidence['observations']} daily returns · {evidence['tail_observations']} tail observations · {notice['history_days']} requested days",
                f"History: {evidence['start']} → {evidence['end']} (end exclusive)",
                evidence["coverage_note"],
            ]
        if notice.get("asset"):
            lines.append("Asset: " + notice["asset"])
        lines.append("Accounts: " + ", ".join(account["label"] for account in notice["accounts"]))
        if notice["metric"] == "drawdown":
            lines.append("Observed value includes cash movements; this is not investment return.")
    elif kind == "strategy":
        lines += [
            f"{notice['name']} · {notice['symbol']} · {notice['timeframe']}",
            f"{notice['action']} · {notice['mode']} run {notice['job_id'][:8]}",
            notice.get("reason", "")[:1000],
        ]
    elif kind == "order":
        lines += [
            f"{notice['symbol']} · {notice['action'].replace('_', ' ')}",
            "Observation: " + notice["type"],
            f"Cumulative filled: {notice.get('filled')}"
            if notice["type"] == "order"
            else f"Imported execution quantity: {notice['quantity']}",
            "Imported fills may describe older executions; order totals and individual fills are distinct observations.",
        ]
    else:
        description = (
            "Read failures observed" if notice["action"] == "failing" else "Successful reads resumed"
        )
        lines += [f"{description} · {notice['operation']}", notice.get("reason", "")[:1000]]
    lines += [
        "",
        "Source: " + notice["source_label"],
        "Environment: " + notice["environment"],
        "Observed: " + notice["observed_at"],
        "Recorded: " + notice["created_at"],
        "",
        "Full evidence: Sibyl → More → Alerts → Inbox.",
        "This notification does not submit orders or change account settings.",
    ]
    return "\n".join(lines)[:12000]
