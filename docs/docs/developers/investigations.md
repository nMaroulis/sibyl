---
title: Investigation reports
description: Report admission and persistence around the existing native ProtoLink runtime.
---

# Investigation reports

`sibyl.investigations` adds saved research around the existing coordinator. It introduces no second agent runtime, keyword routing or model adapter.

| File | Responsibility |
| --- | --- |
| `contracts.py` | Questions, starting selections, idempotent run IDs and final-answer schema |
| `repository.py` | Definitions, bounded version admission, immutable outcomes and restart interruption |
| `service.py` | Freeze settings, execute native coordinator requests, validate report projections and drain accepted tasks |
| `evidence.py` | Project native receipts into bounded previews, links and fingerprints |
| `api/investigations.py` | Private report endpoints under existing authentication/origin controls |

## Native execution and evidence

The service freezes `models.for_turn('sibyl')` before queued admission. Only provider/model/selection metadata is saved; credential-bearing configuration remains in memory and private ProtoLink context. `AgentNetwork.ask` reuses the shared semaphore, native `AgentGroup` handles, budgets, request audit, sessions and cancellation.

Starting context is inherited by owned specialists through `request_context`. It supplies defaults, not authorization restrictions. A fresh conversation isolates every version. `Task.create_infer(output_schema=...)` carries the report schema; the application validates the returned domain report with Pydantic. No custom JSON-repair loop or fallback model is introduced.

Sources derive from completed exposed `RunReport.tool_evidence`, read from the retained redacted native store. They retain native action/task/delegation identifiers, tool ownership, retrieval time, actual returned links, a SHA-256 fingerprint and a preview bounded to 16,000 characters. Model-generated URLs are never fetched. Malformed links and credential-bearing authorities are not offered as source links.

Finding references use `agent_id.tool_name`. An unmatched reference rejects publication. Empty references stay uncited; no receipts means no source-grounding claim. Matching receipts do not verify entailment or freshness. ProtoLink retains full execution history; the domain database stores only the report projection and bounded evidence needed for reopening/export.

Sibyl’s read-only `investigation_reports` tool finds saved questions, lists version IDs and reads dated reports, labeled historical model interpretations. Native discovery/delegation remains unchanged.

## Lifecycle and retention

SQLite `BEGIN IMMEDIATE` and a partial unique index admit one active run per investigation. A caller-generated 32-character request ID is idempotent within that investigation and cannot be reused by another. Capacity is four pending investigations, two executing requests through the shared coordinator semaphore, 100 definitions and 50 runs per definition.

Accepted runs continue after browser navigation. Stop cancels the exact request or queue waiter, drains its task and preserves completed receipts. Terminal results reject late updates. Shutdown drains investigations before closing the native group; startup marks unfinished attempts interrupted without replay.

Active investigations cannot be deleted. Report deletion keeps independently saved conversations. Conversation deletion preserves completed report projections but can remove native details. Reruns resolve current defaults and model choices; they do not replay immutable market inputs. Scheduling, workflow resumption and external delivery remain pending.

## API

All endpoints send `Cache-Control: no-store` and use existing workspace authentication/origin controls.

| Method | Path under `/api/v1/investigations` | Behavior |
| --- | --- | --- |
| GET / POST | empty | List metadata or save a question without inference |
| GET / DELETE | `/{id}` | Read a definition/version list or remove its reports |
| POST | `/{id}/runs` | Accept an explicit run with `request_id`; return 202 |
| GET | `/{id}/runs/{run_id}` | Read the exact report and safe progress |
| GET | `/{id}/runs/{run_id}/export` | Export selected version and source projections |
| POST | `/{id}/runs/{run_id}/cancel` | Stop the exact attempt; return 202 |

Tests keep native discovery, delegation, tools and storage real while controlling provider I/O. They cover model/context isolation, source references, privacy, idempotence, versions, cancellation, restart recovery and survival after conversation deletion.
