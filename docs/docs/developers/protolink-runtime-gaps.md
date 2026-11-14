# ProtoLink 0.8.4 application gaps

Sibyl uses the installed SDK's native execution primitives. These are scoped upstream API gaps, not reasons to add an application agent runtime.

## Resumed task and saved live report can diverge

A first `AgentGroup.run(..., store=SQLiteRunStore(...))` saves a live report at an input-required boundary. `RunManager.resume()` updates the agent's task snapshot, while `get_report(run_id)` can still return the earlier explicitly saved report. A minimal reproducer uses a durable agent with `ask_user_tool`, an initial model tool call, then a final answer after the question is answered:

```python
handle = group.run(agent, Task.create_infer("Ask my format"), store=store)
first = await handle.result()
manager = RunManager(agent)
pending = manager.inspect(handle.context.run_id)["interruption"]
continued = await manager.resume(
    handle.context.run_id,
    request_id=pending["request_id"],
    fingerprint=pending["fingerprint"],
    answer="JSON",
)
final = Task.from_dict(continued["task"])
assert final.state.value == "completed"
assert len(RunReport.from_task(final).tool_evidence) == 1
# The first saved report can still have zero completed tool receipts.
assert len(store.get_report(handle.context.run_id).tool_evidence) == 0
```

Sibyl uses **native `RunReport.from_task()`**, redaction and `save_report()` to retain the authoritative final cumulative report. A management response is intentionally bounded/redacted; trusted application code reads the full final Task from the native private checkpoint before validating a potentially longer structured report.

## Group continuation admission

`AgentGroup.run()` has root concurrency/FIFO limits and retained live handles. `RunManager.resume()`/`Agent.resume_task()` are separate native continuation APIs; the group has no corresponding public `resume` returning a managed handle. Consequently its initial-root admission/fanout does not automatically encompass manager continuations. Sibyl keeps its existing bounded investigation ownership and tracks/drains continuation tasks, using native leases to prevent competing execution of one checkpoint. It does not add another semaphore or claim native group-wide continuation admission. An eventual `group.resume(...)` could unify lifecycle, admission and answer/activity streams.

## Checkpoint retention and uncertain cancellation

`SQLiteDurableStore` provides native get/list/leased execution but no public protected deletion/retention contract. Sibyl does not mutate those private tables to manufacture cleanup. A public protected retention/export API could make long-lived local installations easier to manage.

`RunManager.cancel()` intentionally refuses uncertain effects. Exact local-note observations can be reconciled natively; a missing result remains unknown. An application-facing explicit abandon-interest contract could release UI ownership while preserving uncertainty without claiming rollback or stopping an already executing Python thread. That distinction needs to remain native and auditable.

## Protected peer-card budgets

Native discovery advertises peer skill descriptions and schemas as protected model input. `ContextPolicy` deliberately preserves these instructions; it cannot shrink a large team's cards by removing old conversations or offloading a tool result. A long enough team can therefore exceed the prompt allowance before the first model call. This is the documented protected-input behavior, not a reason to add a custom discovery tool or silently hide skills in Sibyl.

An offline reproducer verified against installed 0.8.4:

```python
import asyncio
from protolink import Agent, ContextPolicy, EvaluationCase, create_llm, evaluate

async def main():
    def make_tool(index):
        def read_record(limit: int = 1) -> dict:
            return {"items": [], "limit": limit}
        read_record.__name__ = f"read_record_{index}"
        read_record.__doc__ = "Read a retained record with source provenance. " * 15
        return read_record

    specialist = Agent(
        name="specialist", llm=None,
        tools=[make_tool(i) for i in range(20)],
    )
    root = Agent(
        name="root", subagents=[specialist],
        llm=create_llm("mock", default_response="Done"),
        context_policy=ContextPolicy(max_tokens=3000, reserve_tokens=100),
    )
    report = await evaluate(root, [EvaluationCase("peer-budget", "Hello")])
    assert "Protected model input" in report.samples[0].error

asyncio.run(main())
```

The recorded run needed about 8,465 estimated protected tokens for a 2,900-token prompt allowance and made zero model calls. Estimates can change with SDK rendering. Sibyl keeps model-facing tool descriptions concise, preserves operational details in its guides/tool evidence and tests native discovery/delegation at the configured context budget. A future **native budget-aware peer advertisement** policy could expose compact peer summaries and expand authoritative skill schemas on demand while preserving routing, authorization and the complete agent registry. That API is not available in 0.8.4; Sibyl does not imitate it with another runtime.
