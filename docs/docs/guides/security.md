# Workspace security and privacy

Sibyl is designed as a single-user local application. Local storage helps you control the workspace, but it does not replace operating-system security, provider permissions, or network access controls.

## Credential vault

Credentials are encrypted with Fernet before SQLite insertion. The local `vault.key` and `sibyl.db` files are owner-readable/writable. The key is stored separately from the database in the same workspace directory. This protects a copied database without its key; it does not protect against someone who can read your full workspace or inspect the running process.

API responses select connection metadata, not secrets. Validation errors strip input values to prevent invalid credential payloads from being reflected. Exchange exceptions are converted to generic provider errors; raw provider request data is not returned to the browser.

Use read-only keys for portfolio access. Enable trading only for accounts you deliberately use with manual exchange execution. Never enable withdrawals for Sibyl.

## API access

The default API listens on loopback. Starting on a non-loopback host requires `SIBYL_API_TOKEN`. Versioned API requests then require a bearer token; the browser can save this token for its session in Settings. Cross-origin requests are restricted to configured origins and the API's own origin.

These checks do not establish separate users, roles, or account permissions. Everyone with the workspace token has access to the same saved accounts and history. Use TLS and an appropriate access proxy for network deployment. OpenAPI and health endpoints are public process metadata.

## Agents and external providers

All agent tools are read-only. They cannot retrieve exchange credentials or submit exchange orders. Model inference sends module observations and conversation context to the configured provider. Local model hosting keeps those model requests on your chosen host; hosted providers process them according to their own terms.

Agent history and native execution reports can contain portfolio values, messages, tool returns and internal action JSON. UI records live in the local database; ProtoLink histories/reports live in `agent-runtime.sqlite`. These records are not field-encrypted. Private model settings never enter task metadata; native reports additionally mask known provider keys. Backtests, paper activity, and order intents also persist. Protect and back up the entire workspace accordingly.

## Browser privacy

Hide balances is a visual blur, not data protection. The browser still contains the values. A workspace bearer token uses `sessionStorage`. Exchange credentials exist temporarily in the connection form, are submitted to your API, and are cleared after saving. They are not saved in browser storage by application code.

## Operations

Back up the database and vault key together, with the API stopped. Disconnecting an account removes its local record; revoke the provider key separately when necessary. Do not commit `.env`, workspace state, credentials, or vault keys to source control. The repository ignores these paths.

Use one API worker for paper scheduling. Exchange order outcomes can remain uncertain after a timeout or process crash. Reconcile using the exchange account and client order ID before preparing another order.

## Model provider keys

LLM profiles and API keys are encrypted using the same local vault as exchange credentials. The model settings API returns only metadata and key-presence flags with `Cache-Control: no-store`. Keys are not placed in browser storage, agent prompts, or saved conversations. Omitting a key during an edit preserves it; removal is explicit. A saved model selection overrides the environment, and each in-flight request keeps a consistent provider/model/key snapshot. Saving a profile does not contact a provider. Model inference sends module evidence to the selected provider as described in the [agent guide](./oracle.md).
