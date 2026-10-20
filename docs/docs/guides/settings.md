# Settings

Settings is the single home for exchange connections and workspace configuration. Open it from the floating dock. Its five top tabs share the dock's rounded style, sliding selection, and subtle content reveal. On smaller screens, the rail scrolls horizontally.

The selected tab is part of the URL, so you can bookmark a section and use browser Back/Forward. Arrow keys move between tabs; Home and End select the first and last. Animations respect reduced-motion preferences. Switching Settings tabs preserves unsaved drafts in memory. Leaving or reloading the page clears those drafts.

## Exchanges

Open `/settings?tab=exchanges` to search and add accounts from the 20-provider exchange catalog, verify read access, or disconnect a saved account. Multiple accounts per provider are supported. Credentials are encrypted in the local Python workspace, never included in agent context. See [Exchange connections](./exchanges.md) for permissions and credential formats.

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

## News

Open `/settings?tab=news` to save the sources behind News, Reporter, and text sentiment. Click a source card to select it. Combine public publishers, or choose **Demo briefings** on its own. News can use real reporting while exchange accounts use demo data.

Select CoinDesk, Cointelegraph, Decrypt, The Block, CryptoSlate, and optionally NewsAPI. The five publisher feeds need no key. CryptoSlate also offers a **Website collector** that checks robots.txt and extracts public homepage article cards. Switching collectors keeps article identities and the retained archive. Disabled providers stop collection and their stories leave the active feed; stored data remains available if re-enabled.

**NewsAPI** has an encrypted, write-only key and a configurable crypto search query. A blank key preserves the saved credential. Removing it also requires disabling that provider. Access, delays, quotas and production use depend on your NewsAPI plan. The API supplies snippets and source links, not complete article bodies. Saved choices apply to new news reads immediately; background collection checks enabled sources while the API runs in public news mode. Saving a configuration does not test a paid API key.

The Demo card has an **Exclusive** badge and a distinct selection color. Choosing it clears every public-source selection; choosing a public card exits Demo and selects that source. Selected cards have a check mark and a highlighted border, with local publisher logos. Source-specific options appear below when relevant. **Save news sources** applies the selection. Demo is a separate backend provider with sample briefings, full demo reading dialogs, and illustrative Fear & Greed values. Saved API credentials remain available for later use but their collectors are disabled in Demo. Public news uses the attributed Alternative.me index. See [Research](research.md) and the [News backend](../developers/news.md).

## Market data

Open `/settings?tab=market` and click a source card, then **Save market source**. The selection applies immediately to new reads. Each complete read keeps one source, even if settings change while it runs. Account mode and trading permissions are independent.

Binance is the initial market feed, even when account mode is Demo. Saved source choices override it. The offline **Demo prices** card appears last; select it on its own for offline fixtures, choose one of 20 public exchange feeds without an API key, or select an existing account under **Connected exchanges**. Account cards retain the saved production/test environment. Public exchange cards do not need an account or saved trading credentials.

**Market APIs** offers CryptoCompare (provider key), CoinGecko Demo API (free-plan key), and CoinGecko Pro API (separate paid-plan key). Enter the provider key and save. Leaving it blank preserves the saved credential; switching providers retains their separate keys. Keys are encrypted on the backend and never returned to the browser. Select another default before removing an active provider's required key. Saving does not test connectivity, plan access or quota.

CoinGecko supplies quotes only in this adapter. CryptoCompare and exchange feeds provide supported candle intervals; exchange feeds also provide order-book snapshots. CoinGecko's Demo plan is live data, distinct from Sibyl's offline Demo card. The Markets page offers a temporary source switcher and links back here for setup.

Saved choices take precedence over environment defaults. This tab also describes fixed research integrations for CoinPaprika, Wikipedia, mempool.space and optional yfinance. The old `/settings?tab=apis` bookmark opens Market data. See the [backend source contract](../developers/market-data.md).

## Workspace

Open `/settings?tab=workspace` for the actual server configuration, browser session access token, documentation, API reference, and ProtoLink links. Saving a workspace token updates this tab's browser session; clearing it does not remove the API's server-side token requirement. Exchange credentials belong in Exchanges.

Manual exchange order permission is controlled separately by `SIBYL_ALLOW_LIVE_TRADING`. Paper strategy accounts always remain virtual. See [Configuration](../getting-started/configuration.md) and [Security](./security.md).
