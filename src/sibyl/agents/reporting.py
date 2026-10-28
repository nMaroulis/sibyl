"""Display native tool outcomes and available metrics without raw execution data."""

import math


def number(value):
    """Keep unknown metrics unknown, rejecting booleans and nonfinite values."""
    return (
        value
        if isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
        else None
    )


def run_details(report) -> dict:
    """Summarize native call receipts, preserving estimation and missing-cost semantics."""
    calls, seen = [], set()
    for event in report.events:
        if event.type != "llm.call.completed" or event.event_id in seen:
            continue
        seen.add(event.event_id)
        data = {**event.payload.get("metadata", {}), **event.payload}
        metrics = data.get("metrics")
        if not isinstance(metrics, dict):
            metrics = {}
        usage = metrics.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        cost = metrics.get("cost")
        cost = cost if isinstance(cost, dict) else {}
        total_cost = number(cost.get("total_cost"))
        calls.append(
            {
                "agent": event.agent_name,
                "provider": metrics.get("provider") or data.get("provider"),
                "model": metrics.get("model") or data.get("model"),
                "latency_ms": number(metrics.get("latency_ms", data.get("latency_ms"))),
                "input_tokens": number(usage.get("input_tokens")),
                "output_tokens": number(usage.get("output_tokens")),
                "total_tokens": number(usage.get("total_tokens")),
                "estimated": bool(usage.get("estimated")) or usage.get("source") != "provider",
                "source": usage.get("source") or "unknown",
                "cost": {
                    "total": total_cost,
                    "currency": str(cost.get("currency") or "Unknown")[:12],
                    "estimated": cost.get("estimated") is not False,
                }
                if total_cost is not None
                else None,
            }
        )
    known = [row["total_tokens"] for row in calls if row["total_tokens"] is not None]
    return {
        "run_id": report.context.run_id,
        "calls": calls,
        "tokens": {
            "total": sum(known) if known else None,
            "known_calls": len(known),
            "calls": len(calls),
            "estimated": any(row["estimated"] for row in calls if row["total_tokens"] is not None),
        },
        "tools": [
            {
                "id": item.action_id,
                "agent": item.agent_name,
                "tool": item.tool_name,
                "outcome": item.outcome,
                "duration_seconds": item.duration_seconds,
            }
            for item in report.tool_evidence
        ],
    }
