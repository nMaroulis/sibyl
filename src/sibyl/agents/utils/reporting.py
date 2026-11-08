"""Display native tool outcomes and available metrics without raw execution data."""

import math

from protolink import RunReport


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
    """Format native deduplicated metrics/rollups; retain unknown and estimated values."""
    # Normalize historical reports using the current SDK's own receipt pairing.
    report = RunReport.from_events(report.events, context=report.context)
    calls = []
    for metric in report.metrics:
        usage = metric.get("usage") or {}
        cost = metric.get("cost") or {}
        total_cost = number(cost.get("total_cost"))
        calls.append(
            {
                "id": metric.get("call_id"),
                "run_id": metric.get("run_id"),
                "agent": metric.get("agent_name"),
                "provider": metric.get("provider"),
                "model": metric.get("model"),
                "latency_ms": number(metric.get("latency_ms")),
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

    def usage_view(scope):
        result = report.usage(scope=scope).to_dict()
        # Defensive JSON display validation, including older provider receipts.
        # Totals and coverage are calculated only by ProtoLink.
        for group in ("reported", "estimated"):
            for name in ("input_tokens", "output_tokens", "total_tokens"):
                result[group][name] = number(result[group][name])
        for cost in result["costs"]:
            for name in ("input_cost", "output_cost", "total_cost"):
                cost[name] = number(cost[name])
        return result

    return {
        "run_id": report.context.run_id,
        "calls": calls,
        "usage": {scope: usage_view(scope) for scope in ("tree", "root", "children")},
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
