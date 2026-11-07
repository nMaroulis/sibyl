# Native ProtoLink model usage

Sibyl uses ProtoLink 0.8.4's native report metrics and usage summaries. The earlier owned-agent metrics omission is resolved; no application telemetry shim or token estimator is needed.

```python
result = await handle.result()
tree = result.report.usage(scope="tree")
root = result.report.usage(scope="root")
children = result.report.usage(scope="children")
```

`tree` includes observed root and descendant model calls. `root` and `children` split them without counting delegation envelopes as additional calls. The SDK pairs dedicated metric events with call-completion receipts and deduplicates replayed event identities. Sibyl also uses `RunReport.from_events()` to normalize historical reports with the current SDK before displaying a summary.

Each `RunUsage` distinguishes provider-reported calls, estimated calls and calls whose usage is unknown. Input/output/total counts can remain `None` when coverage is incomplete. Costs retain their currency and estimated/reported flag; unpriced calls are counted separately. Missing remote observations cannot be inferred from a local report. These values are observations, not a billing guarantee.

**Run details** displays separate reported and estimated token counts, missing usage, root/delegated call counts and per-call prices. It never replaces a missing price with zero or adds currencies together. The API also exposes the native currency-grouped rollups. Prompts, model chunks and tool arguments/results are excluded from these summaries.

The full native report remains a sensitive diagnostic artifact; its availability does not make its entire contents appropriate for a progress view. Streaming uses `answer_events()` and `presentation_events()` instead.

`tests/test_agent_streaming.py` checks actual coordinator usage, native estimate labels, unknown values and currency separation. `tests/test_agent_replay.py` and the browser checks cover authoritative answers, progress and display. Earlier real-model acceptance records retain the SDK/model versions that were actually tested.
