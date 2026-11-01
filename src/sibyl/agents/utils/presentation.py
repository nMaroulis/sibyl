"""Project native run events/evidence into Sibyl's chat and progress cards.

This is UI formatting only: ProtoLink owns execution, discovery, correlation,
tool receipts, cancellation and persistence of the complete run report.
"""

import json


class RunPresentation:
    """Keep the existing consultation cards while consuming one native event stream."""

    def __init__(self, network, handle, configuration, request):
        self.network, self.handle = network, handle
        self.configuration, self.request = configuration, request
        self.rows: dict[str, dict] = {}
        self.saved: set[str] = set()

    def progress(self):
        """Persist only UI progress, never chunks, raw prompts or private model context."""
        self.network.requests.update(
            self.request.request_id,
            phase="consulting"
            if any(row["status"] == "running" for row in self.rows.values())
            else "thinking",
            delegations=list(self.rows.values()),
        )

    def consume(self, event):
        """Render native delegation and child final-answer events; ignore raw action chunks."""
        payload = event.payload
        data = {**payload.get("metadata", {}), **payload}
        kind = payload.get("llm_event_type")
        action_id = event.delegation_id or event.parent_action_id or event.action_id
        if kind == "agent_call_start":
            module = data["agent"].removeprefix("sibyl-")
            role = self.network.roles.get(module)
            question = data["payload"]
            self.rows[action_id] = {
                "agent_id": module,
                "name": role[0] if role else data["agent"],
                "action_id": action_id,
                "task_id": "",
                "question": (
                    question.get("prompt")
                    or f"{question.get('tool')}({json.dumps(question.get('args', {}))})"
                )[:4000],
                "context": {},
                "status": "running",
                "started_at": event.timestamp,
                "finished_at": None,
                "mode": "tools" if data["action"] == "tool_call" else "llm",
            }
        row = self.rows.get(action_id)
        if row is None:
            return
        if event.task_id != self.handle.task.id:
            row["task_id"] = event.task_id
            if kind == "llm_final":
                row["answer"] = payload.get("content", "")
        if kind in {"agent_call_result", "agent_call_error", "agent_call_rejected"}:
            row.update(
                status="completed" if kind == "agent_call_result" else "unavailable",
                finished_at=event.timestamp,
            )
            if row["status"] == "completed":
                self.complete(action_id, row)
            else:
                row["error"] = "The specialist could not complete this consultation."
        self.progress()

    def complete(self, action_id, row):
        """Use native terminal ToolEvidence; never synthesize or log observations in tools."""
        evidence = [
            item
            for item in self.handle.report.tool_evidence
            if item.delegation_id == action_id or (row["task_id"] and item.task_id == row["task_id"])
        ]
        observations = self.network.observations(evidence)
        row["evidence"] = observations[0]["evidence"] if observations else {}
        if row["mode"] == "tools" and observations:
            row["answer"] = json.dumps(observations[0]["evidence"])
        row.setdefault("answer", "")
        config = self.configuration["_agents"].get(row["agent_id"])
        row.update(
            provider=config["provider"] if config else "",
            model=config["model"] if config else "",
            model_selection=self.configuration["_selections"].get(row["agent_id"], "external"),
        )
        if action_id not in self.saved:
            self.network.owner.store.record(
                "agent",
                {
                    **row,
                    "module": row["agent_id"],
                    "session_id": f"sibyl:{self.request.session_id}:{row['agent_id']}",
                    "engine": "ProtoLink",
                    "tool": observations[0]["tool"] if observations else "",
                    "observations": observations,
                    "run_id": self.handle.context.run_id,
                },
            )
            self.saved.add(action_id)

    def finish(self, result):
        """Close unfinished UI cards according to the actual terminal native run."""
        for row in self.rows.values():
            if row["status"] == "running":
                row.update(
                    status="cancelled" if result.status == "canceled" else "unavailable",
                    finished_at=result.report.created_at,
                )
        self.progress()
