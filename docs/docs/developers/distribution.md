---
title: Distribution and releases
hide_title: true
description: Build, test and publish Sibyl's complete Python package using the existing repository.
---

import { DocHero, DocCards } from '@site/src/components/DocBlocks';
import { PackageInstall } from '@site/src/components/ReleaseInfo';

<DocHero title="One package. One release." eyebrow="Developers · Distribution" icon="code" facts={['Dashboard included', 'One version command', 'Existing GitHub repository']}>

The release path is a complete Python wheel and source archive, attached to a GitHub Release in this repository. Source usage works independently. Homebrew and registry images are optional later additions.

</DocHero>

<DocCards
  items={[
    {
      title: 'Build a package',
      text: 'Bundle the existing React build with Python.',
      icon: 'code',
      to: '#build-and-install',
    },
    {
      title: 'Set the version',
      text: 'Synchronize metadata and locks in one command.',
      icon: 'spark',
      to: '#change-the-version-once',
    },
    {
      title: 'Publish a release',
      text: 'Test first, then attach packages on GitHub.',
      icon: 'shield',
      to: '#publish-in-the-existing-repository',
    },
  ]}
/>

## Current scope

| Method                                              | Status                                                                                             |
| --------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Source checkout                                     | Available; build React once and launch with `uv run sibyl --open-browser`.                         |
| Complete local wheel                                | Available; includes dashboard assets and supports an independent `sibyl` command.                  |
| GitHub wheel download                               | Publication tooling is prepared; public commands require published assets.                         |
| Docker from source                                  | The existing Dockerfile/Compose build remains available; container runtime acceptance is separate. |
| Homebrew, prebuilt images, PyPI, desktop installers | Deferred; no extra repository or registry is needed to publish the wheel.                          |

## Build and install

From a checkout with Python, uv and Node.js installed:

```bash
uv sync --frozen --group dev
npm ci
npm run build
uv build
python scripts/distribution/release.py inspect-wheel
```

Install this checkout's package:

<PackageInstall local />

`hatch_build.py` includes React assets in `sibyl/web` in wheels and `src/sibyl/web` in source archives. A wheel can be rebuilt from the source archive without Node.js. Normal packaging fails clearly when compiled assets are absent; editable source installations do not require a frontend build.

`api/dashboard.py` resolves explicit dashboard overrides, bundled assets, then source builds. The API owns its routes before the SPA mount. Page deep links receive the entry HTML; missing API endpoints and static assets retain 404 responses. See [installation](../getting-started/installation.md#launcher-and-workspace) for launch options and workspace selection.

## Change the version once

`pyproject.toml` declares the project version. Use this command when preparing a subsequent release:

```bash
python scripts/distribution/release.py set-version 2.1.1
```

That is an example next version, not a runtime constraint. The command updates Python runtime metadata, all three npm manifests, the npm workspace lock entries and the root package entry in `uv.lock`. It does not resolve or upgrade dependencies. All target formats are checked before files are written. Repeating the same version is safe.

To preview the changes:

```bash
python scripts/distribution/release.py set-version 2.1.1 --dry-run
```

Docs headings and install examples read synchronized metadata at build time. Historical changelog entries and prior acceptance records stay fixed. Add the actual release notes manually; the version command does not invent them. The version in a built filename identifies that particular artifact and is intentionally fixed.

Validate synchronization with:

```bash
python scripts/distribution/release.py version
```

## Publish in the existing repository

1. Commit and push the intended changes to the existing Sibyl repository.
2. In **Actions**, run **Package CI and release** manually. This creates an Actions artifact called `release-candidate`; it publishes no release downloads.
3. Confirm **Test and build release packages** and each **Install and launch on …** job pass. They exercise the wheel on Linux, Windows, Apple Silicon and Intel Macs.
4. Create and publish a GitHub Release from that tested commit, using `v` followed by the declared version. The release event reruns the checks and attaches the resulting packages after they pass.

No additional repository, PyPI account or registry setup is needed. GitHub's built-in token is used only by the upload job. Existing release assets are not overwritten automatically.

The release contains:

- A complete Python wheel and source archive.
- Exported runtime requirements pinned to the verified lock, including optional hosted-model SDKs for installed-package acceptance.
- A `SHA256SUMS` manifest for the downloadable artifacts.

Users can install the wheel URL or downloaded file with uv or pipx. A plain wheel installs core dependencies; users choose SDK extras when needed. The workflow does not publish a package under the `sibyl` name on PyPI.

## What CI verifies

The workflow runs backend tests/lint, builds React, packages and inspects the wheel, then installs it on each target OS. The smoke script starts the installed package outside the checkout with an isolated empty workspace and offline source preferences. It checks command version, readiness, dashboard assets, deep links, API 404 boundaries, database/vault creation and no activated accounts. It never opens a developer's actual workspace.

Manual runs and relevant pull requests produce reviewable artifacts. A published GitHub Release triggers the upload after those same checks. Homebrew, Docker runtime tests and container registries do not gate Python-package publication.

## Optional future delivery methods

Homebrew can be added later as a small recipe pointing at published packages. That recipe can live in this repository; a separate conventional tap is an optional organizational choice. No Homebrew install command is currently advertised.

Prebuilt container images, PyPI publishing, optional background-service setup and signed desktop installers also remain future work. Local Docker builds continue through the existing `docker-compose.yaml`. Track these separately in the [pending checklist](backend-roadmap.md), rather than making them prerequisites for the first packaged release.

Installed-package smoke checks also import/search an isolated research document, inspect worker health, and create/authenticate/restore an encrypted test archive. Recovered accounts remain inactive. These checks run outside the checkout with no user credentials.
