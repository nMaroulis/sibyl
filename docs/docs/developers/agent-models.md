# Per-agent model selection

All eleven native ProtoLink agents remain registered for the application lifetime. A workspace default applies to agents without an override. Each override selects a provider and fixed model ID, reusing that provider profile's encrypted key and endpoint. Changing models does not replace agents, registry cards, tools, discovery or delegation.

## Storage and configuration

`services/llm_settings.py` resolves provider profiles and assignments. `agents/model_selection.py` owns the assignment contract, registered IDs/names and passive readiness checks. `Store.model_snapshot()` reads the selected provider, separately encrypted `llm_default_model`, encrypted provider profiles and encrypted `data:agent-models` settings from one SQLite read transaction.

The assignment document contains a revision and a map from agent ID to `{provider, model}`. `save_agent_model()` merges one assignment in a write transaction and compares the supplied revision. A stale editor receives HTTP 409; unrelated agent edits cannot silently overwrite each other. A null provider removes the override. Existing workspaces need no migration: a missing document means revision zero with all agents inheriting.

`POST /api/v1/settings/llm` accepts `activate` (strict boolean, default `true`). With `false`, the provider profile is encrypted/saved without changing the workspace default provider/model, even when editing that same provider. Legacy selections without a separate default-model row pin the previous model before a profile-only edit; an environment default keeps its configured model. Shared endpoint/key changes still apply to future requests using that provider. Saving endpoint/key changes affects future requests for every agent assigned to that provider. Models on explicit overrides stay fixed when the profile's default model changes. There is one shared endpoint/key per provider; multiple independent credentials/endpoints for the same provider are not implemented.

`GET /api/v1/settings/llm` adds `agent_revision` and an `agents` list with effective provider/model, optional explicit selection, inheritance, simulated status and configuration readiness/reason. It never returns credentials. `POST /api/v1/settings/llm/agents/{agent}` accepts:

```json
{
  "revision": 0,
  "provider": "ollama",
  "model": "an-installed-model-id"
}
```

Use `provider: null` and `model: ""` to inherit again, or `provider: "none"` with an empty model for tool mode. Unknown agents/providers/fields, noninteger revisions, control characters and IDs over 500 characters are rejected. Endpoint/key fields are prohibited in this contract. Nontrivial providers must have a saved profile or be the server's configured environment provider. Required keys and existing `.gguf` paths are checked when saving an override; missing optional dependencies remain visible setup states. No provider is contacted during save or passive metadata reads. Settings success/conflict responses use `Cache-Control: no-store` and the existing workspace token/origin checks.

## Frozen native requests

`ModelSettings.for_turn(agent)` freezes the effective configuration of **the whole team** before an application request queues for its semaphore slot. The private map contains keys and must never be serialized. It lives only in the request `ContextVar` alongside provider adapters and completed observations.

`WorkspaceLLM.call()` selects this agent's entry from the frozen map and lazily constructs its ProtoLink provider through `create_llm()`. The same mechanism covers direct page dialogs, Sibyl, delegated native child inference and top-level `AgentClient` inference. A native client request without an existing application turn creates its own private team snapshot. Delegation remains entirely owned by ProtoLink.

A profile, key or assignment edit during an answer affects the **next** request. Queued/running requests retain their original model/key/endpoint. A key removal therefore does not recall a request already queued with that key. No frozen keys or assignment maps are put into native task payloads, prompts, consultation records or history.

Sibyl's actual effective model determines its `/sibyl` readiness and Telegram's model-ready status. `/system` continues to describe the workspace default. The agents catalog, module replies and completed consultation records expose the relevant provider/model and default/override attribution. Externally discovered peers whose configuration Sibyl does not own are not attributed to the coordinator's model. Recorded attribution describes the selected adapter/model ID, not the provider's hidden routing, exact model revision or measured quality.

## Tool mode and failures

Direct module requests in tool mode retain their existing factual single-tool snapshot behavior. Native tool calls do not require a model. A tool-only specialist cannot complete an inference task; Sibyl may use its advertised tools instead. Setting Sibyl itself to tool mode makes conversational chat unavailable, with a settings link.

An override with a removed required key, missing dependency or missing embedded model stays assigned and reports the setup gap. It never silently inherits a different model or changes provider. Native inference fails without constructing a fallback adapter. A separate environment credential for the same provider remains eligible. Readiness is passive configuration inspection, not a connection check, model-access test, health guarantee or quality evaluation.

Messages, history and tool observations can be sent to the selected providers, including specialists consulted by Sibyl. Agents remain read-only. This feature adds no action approvals, mutation tools or external messaging clients.

Tests use actual ProtoLink agents/registry/clients with scripted provider I/O. They cover encrypted persistence, unchanged default, fixed versus inherited choices, stale/concurrent editors, rollback, native client inference, delegated attribution, mid-turn edits/key removal, tool mode, missing setup, access controls and absence of secrets from task payloads/history.
