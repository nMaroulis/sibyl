# Settings

Settings is the single home for exchange connections and workspace configuration. Open it from the floating dock. Its four top tabs share the dock's rounded style, sliding selection, and subtle content reveal. On smaller screens, the rail scrolls horizontally.

The selected tab is part of the URL, so you can bookmark a section and use browser Back/Forward. Arrow keys move between tabs; Home and End select the first and last. Animations respect reduced-motion preferences. Switching Settings tabs preserves unsaved drafts in memory. Leaving or reloading the page clears those drafts.

## Exchanges

Open `/settings?tab=exchanges` to add Binance, Coinbase, or Kraken accounts, verify read access, or disconnect a saved account. Multiple accounts per provider are supported. Credentials are encrypted in the local Python workspace, never included in agent context. See [Exchange connections](./exchanges.md) for permissions and credential formats.

## AI models

Open `/settings?tab=models` to inspect the current agent provider and model. **Tool mode** works without an LLM. To configure model reasoning, choose Ollama, OpenAI, Anthropic, or an OpenAI-compatible endpoint, then enter its model name and server URL where applicable.

**Download model configuration** produces a non-secret `sibyl-models.env` snippet. Preview the environment lines before downloading. Merge them into your server's `.env`, install the relevant optional Python dependencies, add provider keys on the server, and restart the API. Downloading alone does not change the running configuration. The current runtime card continues to show the actual server settings.

Provider keys use `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `OPENAI_COMPATIBLE_API_KEY`, as applicable. See [Module agents](./oracle.md). Downloading, quantizing, and deploying local models from the app is **Coming soon**.

## Other APIs

Open `/settings?tab=apis` to prepare a `sibyl-data.env` snippet for demo/live market data and the reference exchange. Apply it to the server's existing `.env` and restart the API. This does not enable exchange order execution.

The section also explains the built-in CoinDesk RSS, mempool.space, and optional Yahoo Finance integrations. CoinDesk and mempool.space need no API key. Live equity research requires the Python `stocks` extra. Cards describe supported sources; they are not connectivity checks. Demo fixtures remain explicitly labeled. Custom endpoint and API key management is **Coming soon**.

## Workspace

Open `/settings?tab=workspace` for the actual server configuration, browser session access token, documentation, API reference, and ProtoLink links. Saving a workspace token updates this tab's browser session; clearing it does not remove the API's server-side token requirement. Exchange credentials belong in Exchanges.

Manual exchange order permission is controlled separately by `SIBYL_ALLOW_LIVE_TRADING`. Paper strategy accounts always remain virtual. See [Configuration](../getting-started/configuration.md) and [Security](./security.md).
