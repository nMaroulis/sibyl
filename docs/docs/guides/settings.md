# Settings

Settings is the single home for exchange connections and workspace configuration. Open it from the floating dock. Its four top tabs share the dock's rounded style, sliding selection, and subtle content reveal. On smaller screens, the rail scrolls horizontally.

The selected tab is part of the URL, so you can bookmark a section and use browser Back/Forward. Arrow keys move between tabs; Home and End select the first and last. Animations respect reduced-motion preferences. Switching Settings tabs preserves unsaved drafts in memory. Leaving or reloading the page clears those drafts.

## Exchanges

Open `/settings?tab=exchanges` to add Binance, Coinbase, or Kraken accounts, verify read access, or disconnect a saved account. Multiple accounts per provider are supported. Credentials are encrypted in the local Python workspace, never included in agent context. See [Exchange connections](./exchanges.md) for permissions and credential formats.

## AI models

Open `/settings?tab=models` to select **API** or **Local**, then choose a provider by its icon. One saved provider/model is shared by all ten module agents. **Tool mode** works without an LLM.

| API                                                                              | Local                                                                       |
| -------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| OpenAI, Anthropic, Google Gemini, DeepSeek, xAI, Hugging Face, OpenAI compatible | Ollama, LM Studio, vLLM, llama.cpp server, llama.cpp embedded, Mock runtime |

Choose a model from the provider's presets or select **Custom model…** and enter an exact model ID. Presets are suggestions, not a fetched list of models available to your account. Local server presets must match a model already installed or loaded. The embedded llama.cpp adapter requires an existing `.gguf` file on the Python server; enter its file path. The Mock runtime is for testing and returns a labeled simulated answer.

For an API provider, enter its API key. Local servers and custom endpoints can also save a key if authentication is required. Enter the server URL where shown. **Save & use** encrypts the provider profile in the local vault and makes it effective for new agent requests immediately, without restarting the API. Saving does not send a test request or verify provider access. Install any optional dependency shown by the editor before asking the agents to use that adapter.

Keys stay with their provider when you switch. Leaving the key field blank preserves its saved value; entering a new key replaces it. Saved keys are never returned by the API or placed in browser storage, prompts, or agent run records. The editor shows only whether a key is saved or supplied by the server environment. **Remove saved key** deletes the stored key; an independently configured environment key remains available. If the active provider requires a key and none remains, agents return to tool mode.

**Use tool mode** disables model inference while keeping provider profiles. Requests already in progress keep their original provider/model/key snapshot. Saved workspace selections take precedence over the environment after a restart. See [Module agents](./oracle.md) for setup and data boundaries. Downloading, quantizing, and deploying local models from the app is **Coming soon**.

### Model catalogs

Preset families were reviewed against provider documentation on October 19, 2026. Local server IDs are examples and may need to be replaced by the alias exposed by your runtime. Account access, retirement dates, and server model aliases can differ. The custom option remains available for new IDs.

- [OpenAI](https://developers.openai.com/api/docs/models), [Anthropic](https://platform.claude.com/docs/en/models/overview), [Gemini](https://ai.google.dev/gemini-api/docs/models)
- [DeepSeek](https://api-docs.deepseek.com), [xAI](https://docs.x.ai/developers/models), [Hugging Face](https://huggingface.co/inference/models)
- [Ollama](https://ollama.com/library), [LM Studio](https://lmstudio.ai/docs), [vLLM](https://docs.vllm.ai), [llama.cpp](https://github.com/ggml-org/llama.cpp)

## Other APIs

Open `/settings?tab=apis` to prepare a `sibyl-data.env` snippet for demo/live market data and the reference exchange. Apply it to the server's existing `.env` and restart the API. This does not enable exchange order execution.

The section also explains the built-in CoinDesk RSS, mempool.space, and optional Yahoo Finance integrations. CoinDesk and mempool.space need no API key. Live equity research requires the Python `stocks` extra. Cards describe supported sources; they are not connectivity checks. Demo fixtures remain explicitly labeled. Custom endpoint and API key management is **Coming soon**.

## Workspace

Open `/settings?tab=workspace` for the actual server configuration, browser session access token, documentation, API reference, and ProtoLink links. Saving a workspace token updates this tab's browser session; clearing it does not remove the API's server-side token requirement. Exchange credentials belong in Exchanges.

Manual exchange order permission is controlled separately by `SIBYL_ALLOW_LIVE_TRADING`. Paper strategy accounts always remain virtual. See [Configuration](../getting-started/configuration.md) and [Security](./security.md).
