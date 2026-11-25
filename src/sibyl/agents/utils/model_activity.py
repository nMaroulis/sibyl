"""Deployment activity derived from retained native run reports."""

from protolink import RunReport, SQLiteRunStore

from sibyl.agents.utils.reporting import number

REPORT_LIMIT = 40
REQUEST_LIMIT = 5
SOURCES = {"app", "telegram", "discord", "slack", "whatsapp", "signal", "email", "investigation"}


def deployment_activity(store: SQLiteRunStore, deployment: str) -> dict:
    """Summarize recent attributed attempts and model calls without conversation content."""
    requests, metrics = [], []
    for record in store.list_report_records(limit=REPORT_LIMIT):
        context = record.report.get("context") or {}
        activity = (context.get("metadata") or {}).get("sibyl_activity")
        if not activity or context.get("parent_run_id"):
            continue
        models = activity["models"]
        deployed = {agent: model for agent, model in models.items() if model["deployment"] == deployment}
        if not deployed:
            continue
        report = RunReport.from_dict(record.report)
        calls = [
            call
            for call in report.metrics
            if (call.get("agent_name") or "").removeprefix("sibyl-") in deployed
        ]
        root = activity["root"]
        if root not in deployed and not calls:
            continue
        metrics.extend(calls)
        model_ids = list(dict.fromkeys(call["model"] for call in calls if call.get("model")))
        if not model_ids and root in deployed and deployed[root]["model"]:
            model_ids = [deployed[root]["model"]]
        outcome = (report.final_task or {}).get("state")
        source = activity.get("source")
        requests.append(
            {
                "id": record.run_id,
                "at": record.created_at,
                "source": source if source in SOURCES else "app",
                "agent": root,
                "models": model_ids,
                "status": outcome
                if outcome in {"completed", "failed", "canceled", "rejected"}
                else "recorded",
            }
        )
    usage = RunReport(metrics=tuple(metrics)).usage()
    return {
        "report_limit": REPORT_LIMIT,
        "requests": len(requests),
        "failed": sum(row["status"] in {"failed", "rejected"} for row in requests),
        "calls": usage.calls,
        "reported_tokens": number(usage.reported.total_tokens),
        "estimated_tokens": number(usage.estimated.total_tokens),
        "unknown_calls": usage.unknown_calls,
        "recent": requests[:REQUEST_LIMIT],
    }
