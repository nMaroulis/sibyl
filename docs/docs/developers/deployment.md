# Deployment

## Local development

Run `uv run sibyl` and `npm run dev`. Vite proxies `/api` to `127.0.0.1:8000`; FastAPI owns domain state. Docusaurus is an independent optional process.

## One-origin container

The Dockerfile builds React in a Node stage, installs the locked Python runtime, and serves `frontend/dist` from FastAPI. A browser-history fallback supports direct navigation to dashboard routes.

```bash
cp .env.example .env
# Set a private SIBYL_API_TOKEN in .env.
docker compose up --build
```

Open `http://127.0.0.1:8000`, then enter the token in Settings. Compose binds the published port to loopback and stores the workspace in the `sibyl-data` volume. Container startup refuses to bind publicly without an API token.

Exchange execution remains disabled unless you explicitly set `SIBYL_ALLOW_LIVE_TRADING=true`. Demo/live data selection is independent. Preserve the database and vault key together when moving the volume.

To use optional runtime packages in the image, pass the Docker build argument `SIBYL_EXTRAS`, for example `--extra stocks --extra openai`. Use an explicit model-server address reachable from the container; container loopback is not your host's loopback.

## Source checkout build

```bash
npm run build
uv run sibyl
```

The API serves an existing `frontend/dist` in this repository layout. The Python wheel by itself contains only the API package; host the compiled frontend separately or package it explicitly for a different distribution layout.

## Documentation

```bash
npm run docs:build
```

Host `docs/build` as a static site. The configured public URL is `https://nmaroulis.github.io/sibyl/`; adjust `url` and `baseUrl` in `docs/docusaurus.config.js` for another host. Update the dashboard documentation links for your deployment. No site is automatically published by a local build.

## Network deployment

Use TLS, an authenticated reverse proxy, a strong workspace token, restricted browser origins, and a persistent protected data directory. Avoid logging credential payloads. The API is a single-user service, not a multi-tenant account system.

Run **one API worker**. Paper-job scheduling is owned by that process, not a distributed queue. Back up state with the service stopped. An interrupted exchange submission may remain `submitting` or `unknown`; reconcile with the exchange before retrying through a new intent.
