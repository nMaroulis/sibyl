# Installation

Use Python 3.12 or newer, uv, and Node.js 22.12 or newer. Development uses three independent processes: the Python API, React dashboard, and optional documentation server.

## Install dependencies

From the repository root:

```bash
uv sync --group dev
npm ci
cp .env.example .env
```

`uv.lock` and `package-lock.json` describe the verified dependency resolution. The Python runtime does not download ML models or start additional inference servers.

## Start the API

```bash
uv run sibyl
```

The API listens at `http://127.0.0.1:8000`. `/health` reports process readiness. `/docs` exposes the interactive OpenAPI reference. Services and the paper-strategy worker initialize during application startup, not during module imports.

## Start the dashboard

In a separate terminal:

```bash
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` requests to the Python process. The workspace starts with illustrative market fixtures and a persistent paper wallet. You do not need exchange credentials or a model.

## Start documentation

```bash
npm run docs:dev
```

Open `http://localhost:3000/sibyl/`. Documentation links in the dashboard use this local address. For a hosted documentation site, change those links in the React source to your own documentation URL.

## Optional dependencies

```bash
uv sync --extra openai
uv sync --extra anthropic --extra gemini --extra deepseek --extra huggingface
uv sync --extra llama-cpp
uv sync --extra stocks
```

Extras can be combined in one `uv sync` invocation. Ollama and OpenAI-compatible HTTP servers do not require a hosted-provider SDK. You must run the selected model server separately. The `llama-cpp` extra is only for embedded GGUF inference and may require a platform build toolchain. Model downloads are not bundled.

## Common startup problems

- **The dashboard shows a provider or network error:** confirm the API is running, then retry. Live mode requires network access to the configured exchange.
- **Workspace access is denied:** enter the configured `SIBYL_API_TOKEN` in Settings. Clearing a stored token does not remove the server's token requirement.
- **Port is occupied:** set `SIBYL_PORT` for the API and update `frontend/vite.config.ts` to the same port. Vite prints its selected dashboard address; include that origin in `SIBYL_CORS_ORIGINS` when changing ports.
- **Encryption key missing:** recover both `sibyl.db` and `vault.key` from the same backup. A newly generated key cannot decrypt existing credentials.
- **Equities fail in live mode:** install the `stocks` extra and check provider availability.
