---
title: Installation
hide_title: true
---

import { DocHero, DocCards } from '@site/src/components/DocBlocks';

<DocHero title="Installation" eyebrow="Getting started" icon="code" facts={["Source checkout", "Docker Compose", "Local workspace"]}>

Run Sibyl on your own machine, with a source checkout or Docker Compose. The dashboard, Python API and your encrypted workspace stay under your control.

</DocHero>

<DocCards
  items={[
    {
      title: 'Develop locally',
      text: 'Run the API and dashboard separately, with live reload.',
      icon: 'code',
      to: '#install-dependencies',
    },
    {
      title: 'One application',
      text: 'Build React once and serve it from the Python process.',
      icon: 'server',
      to: '#one-process-source-build',
    },
    {
      title: 'Use Docker',
      text: 'Build the complete app in a container with persistent storage.',
      icon: 'shield',
      to: '#docker-compose',
    },
  ]}
/>

## Install dependencies

For local development, install **Python 3.12 or newer**, **uv**, and **Node.js 22.12 or newer**. Start with a checkout:

```bash
git clone https://github.com/nMaroulis/sibyl.git
cd sibyl
```

From the repository root:

```bash
uv sync --frozen --group dev
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

Open `http://127.0.0.1:5173`. Vite proxies `/api` requests to the Python process. New workspaces have no active accounts. Connect one or several exchanges in Settings, or choose **Preview with Demo** from Account, Trade or Strategies. Public market prices default to Binance; select Demo prices in Market data for offline charts. News and other research sources have independent settings. A model is optional for these workspaces and required for the Sibyl coordinator chat.

## One-process source build

For normal use without frontend live reload, build the dashboard after installing dependencies:

```bash
npm run build
uv run sibyl
```

Open `http://127.0.0.1:8000`. FastAPI serves both the built interface and the API. Keep the repository checkout: the current Python wheel does not include the dashboard assets.

## Docker Compose

With Docker and its Compose plugin installed, the repository can build the complete application without installing Python or Node.js on your host:

```bash
git clone https://github.com/nMaroulis/sibyl.git
cd sibyl
cp .env.example .env
```

Set a private `SIBYL_API_TOKEN` in `.env`, then run:

```bash
docker compose up --build
```

Open `http://127.0.0.1:8000` and enter the workspace token in Settings. Compose publishes the port on loopback, stores the workspace in the `sibyl-data` volume and runs the application as a non-root user. Preserve the database and vault key together when backing up that volume. See [deployment](../developers/deployment.md#one-origin-container) for optional packages and model-server networking.

:::note[Additional installers]
Homebrew, an all-in-one Python package and prebuilt container images are [proposed distribution work](../developers/distribution.md). They are not published installation options yet.
:::

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
