# Retained worker incidents

**Settings → Workspace → Background activity → Retained worker incidents** shows sampled stalls, delayed work and failures after they occur. It remains useful when the browser was closed. Local attention/resumption notices also appear in the notification inbox; acknowledgment does not restart a worker or close an incident.

An owned watchdog thread samples real worker lifecycle state every two seconds. It does not depend on browser requests or the async API event loop. A blocking async task can therefore be observed while Python threads still run. Existing configured worker deadlines and expected next-run times determine `stalled` and `overdue`; an observed exception can produce `failed` or `retrying`. The watchdog never cancels or retries domain operations.

## Interpret the evidence

- **Needs attention:** one active incident per worker and observer. Subsequent issue samples update the same incident rather than repeating notices.
- **Progress resumed:** a later successful worker iteration advanced the recorded completion counter. A heartbeat, a mere `running` state or a user acknowledgment cannot establish recovery. This proves local progress, not exchange access or successful trading.
- **Recovery unknown:** observation ended or a new process found an unfinished incident. Shutdown/restart is not represented as success. Its exact recovery/end time remains unknown.
- **Observation gaps:** actual sample spacing exceeded the observer tolerance. Earlier intervals are unobserved; the app does not reconstruct host uptime or a precise outage duration from them.

First detection and last observation are sample times, not exact outage boundaries. A short stall between samples may be missed. An in-process observer cannot report its own process death in real time, run while the host is suspended or guarantee sampling during all GIL/OS stalls. Use an external service monitor for host/process availability requirements.

Normal close joins the observer before cancelling workers. Restored workspaces leave automatic observation unstarted until the reviewed restart. Observer failures expose only a count; provider responses and raw exceptions are excluded. Existing worker fault history remains a separate exception-type record.

## Retention and privacy

The workspace retains at most 200 recent closed incidents plus active incidents, 50 recent observation gaps and 20 observer sessions. The UI pages 20 incidents. Notifications have the separate existing inbox acknowledgment/export/retention policy, so pruning an incident cannot silently acknowledge or remove its notice. Workspace notifications are local only; they do not inherit a financial alert's Telegram delivery permission.

Evidence allowlists fixed worker IDs, known lifecycle phases, numeric counters/deadlines and aware timestamps. It excludes credentials, account identifiers, private labels, exception messages, request/response bodies and domain content. Technician's native `worker_incidents` tool reads five recent incidents with freshness and gaps; it cannot restart/cancel work.

## Implementation and checks

`operations/watchdog.py` owns the observation thread and persistent incident boundaries. `WorkerHealth.observations()` supplies real progress without resource/database probes. `GET /api/v1/workspace/incidents?offset=0` is a passive, no-store read. Opening that endpoint or the UI does not create a sample. Notification export supports `kind=workspace`.

Tests deliberately block an async worker while the separate observer detects the stall, then require a real completed iteration for recovery. They also cover repeated samples, restart uncertainty, sample gaps, fault privacy, bounded retention, thread draining, passive HTTP reads and separate inbox acknowledgment/export.
