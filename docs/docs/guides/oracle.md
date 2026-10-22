# Module agents

Each workspace module has its own embedded [ProtoLink](https://github.com/nMaroulis/protolink) agent. Each specialist has its own role, instructions, and native read-only tools. All agents start with the app and register with the in-process ProtoLink registry. Module Ask requests reach their specialist directly through a ProtoLink client. [Sibyl](./sibyl.md) is a separate lead agent that can discover and consult these specialists. There is no separate gRPC inference service or mandatory model download.

## Ask without leaving the page

The gradient **Ask** button opens a floating dialog over the current module. Closing it returns to the same chart, form, selection, and scroll position. **Esc** closes the dialog, and keyboard focus returns to the button that opened it. On small screens the dialog uses the available screen height.

- **Portfolio → Accountant:** allocation, concentration, and balances.
- **Markets → Analyst:** the selected market, chart timeframe, and sample window.
- **Strategies → Broker:** the currently selected strategy and validated simulation parameters. Asking does not run a backtest or start a paper strategy.
- **Trading → Broker:** the selected market and execution assumptions.
- **Forecasting → Chronos:** the selected market and forecast horizon.
- **News → Reporter:** the feed, or a specific story when opened from its card.
- **Settings → Technician:** practical setup guides, provider-specific connection instructions and saved metadata, excluding credentials.
- **Research → Wiki / Explorer / Equity Analyst:** the glossary search, Bitcoin blocks, or selected equity ticker.

Drafts and conversations remain available after closing and reopening the dialog during the current browser session. Different modules and page selections use separate sessions. **Recent conversations in this context** restores a saved session; the server retains recent turns for model inference. **New conversation** clears the current draft and starts a fresh session without deleting saved history. Browser reloads clear unsent drafts.

The **More → Agents** dock entry is a directory of specialists and their native tools. It provides another way to open an agent dialog; it is not required for asking a module agent.

## Two useful modes

### Tool mode: works immediately

`SIBYL_LLM_PROVIDER=none` sends a native tool task through `AgentClient` to the selected specialist. The response is a deterministic factual summary of actual tool output. It is labeled **Tool snapshot** and is not a language-model response.

This mode does not interpret an arbitrary question like a model. The question selects glossary matches for Wiki; other specialists return the selected module context snapshot. Page selections supply the market, horizon, strategy parameters, or equity ticker. Without page context, Analyst and Chronos default to BTC/USDT and Equity Analyst defaults to AAPL.

### Model mode: conversational reasoning

Select and save a model in **Settings → AI models** to let ProtoLink interpret the question, inspect module evidence, and call its read-only tool with supported arguments. The same agent stays available throughout the app lifetime; ProtoLink isolates each task’s model history. Evidence is read only when the agent calls a tool, rather than preloaded into its prompt. Up to six recent turns from the same session and module are supplied explicitly; model state is not shared across unrelated conversations.

Each response shows the provider and actual completed tool observations. Expand **Inspect evidence** to see returned data; multiple tool reads can be inspected together. An answer without workspace reads says so. This is evidence, not hidden model reasoning. Reporter can read the existing news archive, article excerpts, publisher health and cached Fear & Greed index. Technician can explain how to connect Binance or configure any Settings tab without reading credentials.

## Connect a provider

Open **Settings → AI models**. Choose API or Local, select the provider, pick a preset or enter a custom model ID, add its key or server URL, then **Save & use**. No restart is needed. All providers in the installed ProtoLink factory are supported, including local servers, embedded GGUF inference, and a clearly labeled Mock runtime. See the [Settings guide](./settings.md).

Install the optional SDK for hosted providers when needed:

```bash
uv sync --extra openai --extra anthropic --extra gemini --extra deepseek --extra huggingface
```

Ollama, LM Studio, vLLM, llama.cpp server, xAI, and OpenAI-compatible HTTP adapters use the core HTTP dependencies. Run local model servers separately and install/load your desired model there. Embedded llama.cpp additionally needs `uv sync --extra llama-cpp` and a GGUF file on the Python host. A localhost server URL refers to the API host; inside Docker, use a reachable host address such as `http://host.docker.internal:11434` on Docker Desktop.

Environment configuration remains available for a workspace with no saved selection:

```dotenv
SIBYL_LLM_PROVIDER=ollama
SIBYL_LLM_MODEL=your-installed-model
SIBYL_LLM_BASE_URL=http://127.0.0.1:11434
```

Restart after editing environment defaults. Saved profiles override them. Provider environment credential names are `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `XAI_API_KEY` (or `GROK_API_KEY`), `HF_API_TOKEN`, `OPENAI_COMPATIBLE_API_KEY`, `OLLAMA_API_KEY`, `LMSTUDIO_API_KEY`, and `VLLM_API_KEY`. Keys entered in Settings remain encrypted in the vault and are passed only to the chosen adapter, never copied into model messages or agent tools. Provider capabilities and model tool-following quality vary.

## Data and execution boundaries

Model-backed requests send the selected module's evidence, your message, and recent session turns to the configured provider. Accountant and Oracle evidence can include portfolio balances. Choose a local model if you want that inference to remain on your machine.

Exchange API keys and secrets are not available to agents. Native agent tools do not place orders, change credentials, start strategies, execute shell commands, or access arbitrary files. News and user text are treated as untrusted input in agent instructions, but factual answers still require your own review.

Two requests may run concurrently. ProtoLink inference has an eight-step budget with at most six tool calls; the page request waits at most 95 seconds. A provider thread already in progress may finish after the HTTP timeout. It has only read-only module tools and cannot execute trades.

Requests and responses are stored locally, including questions, answers, and completed tool observations. **New conversation** resets the active module's session context without deleting saved run history.
