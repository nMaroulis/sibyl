# Native resumable investigations

In **Sibyl → Investigations**, save a question and enable **Native checkpoints** before running it. Ordinary investigations and chats retain their existing request-driven read-only behavior. The optional workflow uses a separate configuration of the Sibyl coordinator with the same owned specialists and the accepted Sibyl model assignment.

## Native execution contract

`agents/sibyl.py` declares the workflow coordinator, prompt and tools. `ResearchWorkflows` supplies native `AgentGroup`, `SQLiteDurableStore`, `RunManager`, `request_context`, `RunBudget`, `CapabilityPolicy` and ordinary typed tools. It does not implement another reasoning loop, delegation protocol, checkpoint format or tool execution wrapper.

The coordinator starts with the app. Its model factory is lazy; startup contacts no paid provider. The application freezes the entire team's configuration before accepting a request. A private encrypted profile retains that snapshot across waits and restart; it is never Task/RunContext metadata or a tool parameter. Later model/profile changes apply to new versions, while continuations use the original accepted snapshot. Terminal versions clear their private credential snapshot.

Native budgets cap a workflow at 24 steps, 20 model calls, 20 tool calls and 1,200 execution seconds. The root yields after three model turns in a cooperative slice. Questions use native `ask_user_tool`; questions, approvals and cooperative yields are separate states. Waiting does not mean an answer or permission was supplied. The UI forwards only the owned native request ID/fingerprint and the corresponding response type.

The existing investigation repository retains report projections and admission bounds. Waiting workflows keep their one-active-version slot and cannot be pruned or deleted as completed work. ProtoLink owns committed observations, action receipts, leases, history and cumulative budget state.

## Local-note approval

`save_research_note(title, text)` is the workflow's only write. It is available only in this coordinator variant, requires the `research.note.write` capability with native `require_approval`, and writes an AI-labeled UTF-8 document to **My research**. The approval shows the complete bounded title/text. Answering a question does not approve a note. Declining stops the native execution without writing it.

The existing library deduplicates identical content. Native action receipts avoid replaying a committed tool. If an admitted write has an uncertain result, **Verify exact saved note** reads actual matching retained content and records that observation through `RunManager.reconcile`; it does not create a note or invent the original return. A missing match remains unknown. Other uncertain actions require inspection rather than an automatic retry. No exchange, strategy, settings or messaging action is added to this agent.

## Restart, cancellation and restore

Pending questions, approvals and cooperative waits survive restart without another model request. Resume is explicit. A hard interruption can expose a saved native boundary or uncertain action; the SDK decides whether it can continue safely. A graceful shutdown cancels/drains active attempts; a natively canceled/failed execution is terminal. This does not promise continuation after every failure or undo a note already committed by an admitted thread.

A live Stop cancels the owned attempt; a stopped unambiguous checkpoint uses native cancellation. The SDK refuses offline cancellation of uncertain effects. Such evidence must be inspected/reconciled first. Restored archives quarantine unfinished workflow versions and clear their private model snapshots; they cannot resume a stale backup cursor. Start a new reviewed version instead.

Native checkpoints are private owner-readable SQLite, containing questions and domain observations. Credentials belong only to the separate encrypted snapshot. Retained note documents have their existing library limits. This implementation intentionally does not delete native checkpoint rows through custom SQL: checkpoint-retention APIs and live-group continuation admission remain [upstream gaps](protolink-runtime-gaps.md).

## Evidence

Completed structured reports still validate source references against actual native tool evidence. Resumed cumulative reports use the public SDK's `RunReport.from_task()` from the final native task, then native redaction/persistence; the first slice's live report can otherwise remain older than the resumed task. Raw checkpoints and full management tasks are never exported as HTTP evidence. The report UI, JSON exports and specialist receipts retain their existing scopes.

Acceptance tests use controlled model I/O with real ProtoLink execution: questions, exact approvals, declined writes, duplicate continuation, specialist evidence, restart, credential isolation, frozen model choices, restore quarantine and exact-content reconciliation.
