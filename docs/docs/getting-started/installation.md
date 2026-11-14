---
title: Installation
hide_title: true
---

import { DocHero, DocCards } from '@site/src/components/DocBlocks';
import { PackageInstall } from '@site/src/components/ReleaseInfo';

<DocHero title="Installation" eyebrow="Getting started" icon="code" facts={['Source checkout', 'Complete Python package', 'Local workspace']}>

Start with a source checkout, or install a complete Python package. Both run the same dashboard and backend. No additional repository, Homebrew setup or PyPI account is needed.

</DocHero>

<DocCards
  items={[
    {
      title: 'Run from source',
      text: 'The recommended way to start and keep developing.',
      icon: 'code',
      to: '#run-from-source-recommended',
    },
    {
      title: 'Install a package',
      text: 'A standalone command with the dashboard included.',
      icon: 'server',
      to: '#install-the-python-package',
    },
    {
      title: 'Use Docker',
      text: 'Build the application locally in a container.',
      icon: 'shield',
      to: '#docker-compose',
    },
  ]}
/>

## Run from source (recommended)

Install **Python 3.12+**, [uv](https://docs.astral.sh/uv/) and **Node.js 22.12+**, then run:

```bash
git clone https://github.com/nMaroulis/sibyl.git
cd sibyl
uv sync --frozen --group dev
npm ci
npm run build
uv run sibyl --open-browser
```

Open `http://127.0.0.1:8000` if the browser does not open automatically. One Python process serves both the built dashboard and API. Later starts only need `uv run sibyl --open-browser`; rebuild React after frontend changes.

Source checkouts keep their workspace in the repository's `.sibyl` directory, even without an environment file. To customize server defaults, optionally copy `.env.example` to `.env` and edit it. Preserve an existing `.env` rather than replacing it.

A fresh workspace has no active accounts. Connect one or several exchanges in Settings, or explicitly choose **Preview with Demo**. Public market feeds and news settings are independent. A model is optional for data workspaces and required for the Sibyl coordinator chat. See [configuration](configuration.md) and [exchange connections](../guides/exchanges.md).

### Local development with live reload

For frontend development, run the API in one terminal:

```bash
uv run sibyl
```

In another terminal:

```bash
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies API requests to the Python process. `/health` reports process readiness and `/docs` exposes the interactive API reference on port 8000.

## Install the Python package

The `.whl` file is an installable Python package containing **both the backend and the built dashboard**. Running it needs no Node.js or source checkout.

### Build and install locally

From a source checkout after installing its dependencies:

```bash
npm run build
uv build
```

Then install the package for this checkout's version:

<PackageInstall local />

uv installs a separate environment and exposes the `sibyl` command. The file's version identifies the exact build being installed. Keep using the source checkout if you are actively editing the code; installed packages are snapshots until rebuilt and reinstalled.

### Download a published release

After the package is attached to a [GitHub Release](https://github.com/nMaroulis/sibyl/releases), users can install it directly:

<PackageInstall />

These download commands require the corresponding release assets to exist. The release workflow is prepared; preparing it locally does not publish an installer. Use the source or local-build instructions above before publication. With Python 3.12+ and pipx installed, `pipx install` accepts the same wheel file or URL. The project is not published to PyPI through this workflow.

For an API model requiring a provider SDK, select that package extra when installing, for example:

<PackageInstall extra="openai" />

Ollama and compatible HTTP servers need no hosted SDK. Models and model weights remain separately configured.

## Launcher and workspace

```bash
sibyl --version
sibyl --port 8123 --open-browser
sibyl --data-dir /path/to/existing/workspace
sibyl --env-file /path/to/sibyl.env
```

CLI options override environment variables, which override the selected environment file. By default, Sibyl reads `.env` in the launch directory; `--no-env-file` ignores it. `--help` lists every option.

Installed packages use per-user application data:

| Platform | Default workspace                                 |
| -------- | ------------------------------------------------- |
| macOS    | `~/Library/Application Support/Sibyl`             |
| Windows  | `%LOCALAPPDATA%\Sibyl`                            |
| Linux    | `$XDG_DATA_HOME/sibyl`, or `~/.local/share/sibyl` |

Source checkouts keep their repository `.sibyl`. Set `SIBYL_DATA_DIR` or `--data-dir` explicitly when opening that existing workspace from an installed package. Stop the previous instance first and run one API worker per workspace. Installers do not move or delete the database or vault key.

## Docker Compose

The existing Compose file builds Sibyl from this repository. Install Docker and its Compose plugin, then create a configuration file if one does not already exist:

```bash
cp .env.example .env
```

Set a private `SIBYL_API_TOKEN` in `.env`, then run:

```bash
docker compose up --build
```

Open `http://127.0.0.1:8000` and enter that token in Settings. Compose binds loopback, runs the app as a non-root user and stores state in the `sibyl-data` volume. Python and Node.js are built inside the container. See [deployment](../developers/deployment.md#one-origin-container) for model-server networking, optional packages and backups. Container runtime acceptance still needs a Docker environment; Python package checks do not establish container acceptance.

## Optional dependencies

For a **source checkout**, install the relevant extras:

```bash
uv sync --frozen --group dev --extra openai
uv sync --frozen --group dev --extra anthropic --extra gemini --extra deepseek --extra huggingface
uv sync --frozen --group dev --extra llama-cpp
uv sync --frozen --group dev --extra stocks
```

Combine the extras you need in one invocation. For an installed wheel, select extras on its installation requirement as shown above. Ollama and OpenAI-compatible HTTP servers need no hosted-provider SDK; start the selected server separately. Embedded `llama-cpp` inference may need a platform build toolchain. No model weights are bundled or downloaded at startup.

## Start documentation

```bash
npm run docs:dev
```

Open `http://localhost:3000/sibyl/`. Development dashboard links use this local preview; packaged builds link to the public documentation. End users need no Docusaurus process. For another documentation host, update `frontend/src/lib/docs.ts` before building.

## Other installation methods

Homebrew, prebuilt registry images, PyPI publication and desktop installers remain optional future work. They do not block source usage or a GitHub wheel release. No new repository is required for this release. See the [release process](../developers/distribution.md) and [pending checklist](../developers/backend-roadmap.md).

## Common startup problems

- **Port is occupied:** stop the existing instance, or use `--port` for a separate workspace. When developing with Vite, update its proxy/origins for a different API port.
- **Workspace access is denied:** enter the server's configured API token in Settings. Clearing a browser token does not remove the server requirement.
- **Existing accounts are missing after changing installation method:** select the original workspace using `--data-dir`; installed packages and source checkouts have different defaults.
- **Vault key missing:** restore the database and vault key together from the same backup. A new key cannot decrypt existing credentials.
- **A provider or model is unavailable:** check the API process, the selected provider, its required extra and network access. Saving settings alone does not verify access.

## Start at login

After installing/building Sibyl, use its native user-service CLI on macOS, Linux systemd or Windows Task Scheduler. **Settings → Workspace → Background service** shows actual OS status and copyable preview/install/start commands for the current workspace. Installation registers future logins without starting immediately; stop/start and uninstall are explicit. See [Run Sibyl in the background](../guides/background-service.md) for private environment files, logs, upgrades and platform limits.
