# Settings

Settings is the single home for exchange connections and workspace configuration. Open it from the floating dock. Its top tabs share the dock's rounded style, sliding selection, and subtle content reveal. On smaller screens, the rail scrolls horizontally.

The selected tab is part of the URL, so you can bookmark a section and use browser Back/Forward. Arrow keys move between tabs; Home and End select the first and last. Animations respect reduced-motion preferences. Switching Settings tabs preserves unsaved drafts in memory. Leaving or reloading the page clears those drafts.

## Exchanges

Open `/settings?tab=exchanges` to search and add accounts from the 20-provider exchange catalog, verify read access, or disconnect a saved account. Multiple accounts per provider are supported. Credentials are encrypted in the local Python workspace, never included in agent context. See [Exchange connections](./exchanges.md) for permissions and credential formats.

## AI models

Open `/settings?tab=models` to select **API** or **Local**, then choose a provider by its icon. The workspace default is used by agents without a custom assignment. Sibyl and each specialist can select a different provider/model under **Agent models**. **Tool mode** works without an LLM.

| API                                                                              | Local                                                                       |
| -------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| OpenAI, Anthropic, Google Gemini, DeepSeek, xAI, Hugging Face, OpenAI compatible | Ollama, LM Studio, vLLM, llama.cpp server, llama.cpp embedded, Mock runtime |

Choose a model from the provider's presets or select **Custom model…** and enter an exact model ID. Presets are suggestions, not a fetched list of models available to your account. Local server presets must match a model already installed or loaded. The embedded llama.cpp adapter requires an existing `.gguf` file on the Python server; enter its file path. The Mock runtime is for testing and returns a labeled simulated answer.

For an API provider, enter its API key. Local servers and custom endpoints can also save a key if authentication is required. Enter the server URL where shown. **Save as workspace default** encrypts the provider profile and selects it for agents following the default. **Save profile only** saves the key/model/endpoint for later assignment without changing that default. Both apply to subsequent requests without restarting the API. Saving does not send a test request or verify provider access. Install any optional dependency shown by the editor before asking the agents to use that adapter.

Keys stay with their provider when you switch. Leaving the key field blank preserves its saved value; entering a new key replaces it. Saved keys are never returned by the API or placed in browser storage, prompts, or agent run records. The editor shows only whether a key is saved or supplied by the server environment. **Remove saved key** deletes the stored key; an independently configured environment key remains available. If the workspace default requires a key and none remains, that default returns to tool mode. Explicit overrides stay selected and show **Needs setup**; they never silently switch providers.

**Use tool mode** sets the workspace default to tool mode while preserving provider profiles and agent overrides. Requests already queued or running keep their original team/provider/model/key/endpoint snapshot. Saved workspace selections take precedence over the environment after a restart. See [Module agents](./oracle.md) for setup and data boundaries. Downloading, quantizing, and deploying local models from the app is **Coming soon**.

### Choose models per agent

1. Save each provider's profile above, using **Save profile only** when you want to keep the existing workspace default. Keys and endpoints are shared by all agents assigned to that provider.
2. Expand **Agent models → Customize agents**, then Configure Sibyl or a specialist. Choose a provider and one of its presets, or enter a custom model ID/GGUF path. Local models must already be available on the server. Save the assignment.
3. **Default** means the agent follows future workspace-default changes. **Custom** fixes that agent's provider/model. Choose **Follow workspace default** in the dialog to remove an override.

For example, Sibyl can use one configured API model while Reporter uses an installed local model. Direct module dialogs and Sibyl's consultations use the same specialist configuration. Each new request freezes the whole team's choices; edits during a conversation affect subsequent requests, not an answer already running. Reply and consultation history retain their original model attribution.

**Configuration ready** means required local configuration is present, not that the provider/server has been tested or the model is available. **Needs setup** points to a missing key, dependency or embedded file. Preset availability is not verified. A tool-only specialist still exposes its read-only tools, but cannot complete reasoning consultations. Sibyl itself needs a model to chat; its override also determines Telegram's model readiness.

Messages and evidence can be sent to the selected providers when Sibyl consults specialists. No agent gains new permissions. See [runtime and security contracts](../developers/agent-models.md).

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

Open `/settings?tab=workspace` for [background-worker activity](worker-health.md), [encrypted backup/recovery](workspace-backups.md), the actual server configuration, browser session access token, documentation, API reference, and ProtoLink links. Saving a workspace token updates this tab's browser session; clearing it does not remove the API's server-side token requirement. Exchange credentials belong in Exchanges.

Exchange order permission is controlled by `SIBYL_ALLOW_LIVE_TRADING`. Automated exchange strategies additionally require `SIBYL_ALLOW_STRATEGY_EXECUTION` and an explicit account/budget approval; see [exchange strategy execution](strategy-execution.md). Paper strategy accounts always remain virtual. Workspace displays both permission states. See [Configuration](../getting-started/configuration.md) and [Security](./security.md).

## Source health

**Market data → Source health** shows observed connectivity, latest quote quality, response time, safe recent errors and queued work. Expand a source for details; use Show all sources to include unchecked providers. Refresh diagnostics reads local evidence without testing keys or contacting exchanges. Demo is explicitly offline, and a selectable feed is not marked healthy until a real read succeeds. Live counters reset on API restart; saved read history and import job counts persist. Each expanded source has 24-hour/7-day hourly charts, observed read success, mean/peak response time and saved errors. Gaps mean no observed traffic, not downtime; old history never marks a current connection healthy. Markets and populated Account views show the same compact feed status. See [request policies and boundaries](../developers/provider-control.md).

## Messaging

[Telegram](./telegram.md) supports private chat and opt-in [scheduled briefing delivery](briefings.md). Setup: save your encrypted bot token and numeric user ID, check the bot, then explicitly enable polling and replies. Setup and enabling work without an AI model. A single warning above the cards links to model settings; help/status commands work immediately, and ordinary questions receive setup guidance until a model is active. Other channels below remain unavailable previews with disabled fields.

| App      | Setup                                                                                                           |
| -------- | --------------------------------------------------------------------------------------------------------------- |
| Telegram | BotFather token and your numeric user ID                                                                        |
| Discord  | Bot token, application ID and numeric private user ID; direct DM polling                                        |
| Slack    | Bot token, Socket Mode app token and private member ID                                                          |
| WhatsApp | Graph version, access token, business phone ID, app secret, webhook verification token and your personal number |
| Signal   | Loopback signal-cli origin, separately linked account and personal sender ACI                                   |
| Email    | Dedicated TLS IMAP/SMTP mailbox, fixed personal sender and a private subject pairing phrase                     |

Every implemented connection encrypts credentials locally and starts paused. Check its identity, then enable private replies. Setup works without an LLM; questions receive model guidance until one is active. Saved secrets remain hidden; Edit requires complete replacement credentials. Pause stays available during a model request. Receipts show actual acceptance/uncertainty rather than claiming the person read a reply.

WhatsApp requires a signed public HTTPS webhook. Discord polls only your checked private DM; Slack uses native Socket Mode. Signal requires the separately linked **unofficial signal-cli** daemon; Sibyl never collects a Signal PIN or links an account. Email uses verified TLS, read-only IMAP UID cursors and a fixed reply address; each subject must start with `[Sibyl:YOUR_PAIRING_PHRASE]`, because From alone is not authentication. Provider OAuth mail sign-in is not implemented.

See [complete channel setup and boundaries](../developers/private-messaging.md) and [Telegram controls](telegram.md).

## Ollama server controls

When choosing Local → Ollama, inspect actual server status, installed and loaded models, and choose an installed model. You can start an installed local Ollama server and stop only a server started by Sibyl. Installation and model downloads remain separate, with instructions in the panel. See [Ollama setup](ollama.md).

### Workspace health report

Choose **Run health check** in Workspace to run a read-only SQLite quick check and collect content-free runtime diagnostics. **Download health report** exports the last completed report; neither opening Settings nor downloading reruns the check. Versions, numeric process/storage counters, aggregate worker states and generic check outcomes are included. Credentials, account identifiers/balances, chats, articles, paths, hostnames, plugin code and raw SQLite messages are excluded. Review the JSON before sharing.

A passed quick check is not a full integrity check, a credential test or proof that account data is correct. Interrupted, busy or inaccessible checks make no integrity conclusion. The check has a two-second execution budget plus a short lock wait; it never repairs data. Reports stay in memory until restart. Technician can read an existing report but cannot start a check or download it.

### Read allowances and quota evidence

Expand a source in **Market data → Source health** for compact allowance cards. **App allowance** is Sibyl’s conservative local budget. **Observed provider ceiling** is a separately reported Binance one-minute IP declaration, with 20% reserved from read admission. The cards show used/estimated remaining units, reset/refill behavior and observation times. Reported order counters are informational and do not grant trading permission.

Reviewed Binance Spot GET requests use their documented weights; Kraken private account/history POST reads use conservative key-scoped estimates. Coinbase Exchange Sandbox has separate public/private/fills allowances. Coinbase Advanced and other unreviewed endpoints keep their existing native limiter and base spacing; their provider headroom is unknown. Actual account tiers and outside traffic are not inferred.

**Read budget wait** means a read was deferred before sending; it does not mean the exchange is offline. Imports retain their saved progress. Native orders/cancellations keep their existing single-attempt contract; this policy never queues or replays them. Extra bypass/coverage details explain what the estimate includes. All quota evidence is local to the current backend process and resets on restart; real provider usage does not. See [policy scope](../developers/provider-control.md#reviewed-quota-policies).

### Background service

Expand **Workspace → Background service** for native current-user service state, workspace matching and copyable CLI controls. It reads the OS only when opened/refreshed; it cannot execute service changes. Preview and install from your local terminal, then start explicitly. See [background service setup](background-service.md).
