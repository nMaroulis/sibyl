---
title: Installation roadmap
hide_title: true
description: Proposed distribution options for Sibyl, with current availability and packaging prerequisites.
---

import { DocHero } from '@site/src/components/DocBlocks';

<DocHero title="An easier way in." eyebrow="Developers · Distribution proposal" icon="code" facts={['Proposed for 2.1', 'No packages published yet']}>

The next installation work should turn Sibyl into one install and one launch. Source checkout and local Docker Compose builds already work; the options below are proposals for the release, not available installers.

</DocHero>

## Recommended release scope

| Order | Method                                               | Who it helps                                                                   | Work required                                                                                                                                                                                   |
| ----- | ---------------------------------------------------- | ------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1     | Complete Python package, installable with uv or pipx | Users who want a small local installation without Node.js or a source checkout | Bundle the built React interface, resolve package resources correctly, add a stable workspace location and test an installed wheel outside the repository.                                      |
| 2     | Versioned GHCR container images                      | Docker users and people running Sibyl on a home server                         | Publish tested `linux/amd64` and `linux/arm64` images with release tags, checksums/digests and a Compose file that pulls the image.                                                             |
| 3     | Homebrew formula in a project tap                    | macOS users who want familiar installation and updates                         | Package the complete app with isolated Python dependencies, checksummed resources and an installed-app smoke test. Start with a project tap; official Homebrew inclusion is a separate process. |
| Later | Signed desktop installers                            | People who prefer an application icon and no terminal                          | Package the Python runtime, browser shell and UI; own signing, notarization, updates and process lifecycle on each platform.                                                                    |

The Python package is the common foundation for uv, pipx and Homebrew. [uv tools](https://docs.astral.sh/uv/guides/tools/) and [pipx](https://pipx.pypa.io/stable/) install command-line applications in isolated environments. A Homebrew formula can use its [Python virtual-environment helper](https://docs.brew.sh/Language-Specific-Formulae#installing-a-python-application), rather than modifying the user's Python environment. Docker documents a [multi-platform release workflow](https://docs.docker.com/build/ci/github-actions/multi-platform/).

## Package the whole application first

The current Hatch wheel includes `src/sibyl` only. FastAPI finds the dashboard at `frontend/dist` relative to the checkout. Installing that wheel in isolation therefore does not install the complete UI.

- [ ] Build the interface once in release CI and include it as Python package data.
- [ ] Resolve static resources from the installed package, with an explicit development override.
- [ ] Use a stable per-user workspace/configuration location with an explicit directory override; preserve user state across upgrades and uninstalls.
- [ ] Add a clear launcher with version, configuration and browser-opening options.
- [ ] Decide which optional model SDK extras each distribution includes; keep model weights separate.
- [ ] Test fresh installation, health, UI assets, deep links, restart and upgrade outside the source checkout on supported platforms.
- [ ] Verify the distribution name, release artifacts and dependency licensing before publication.

## Then publish the delivery channels

- [ ] Build and exercise both container architectures, preserve non-root permissions and persistent volumes, and publish immutable release tags.
- [ ] Add image provenance and an upgrade/backup procedure to the ready-to-run Compose example.
- [ ] Create the Homebrew tap, pin dependency sources and checksums, and test the installed application. Offer background service setup as an explicit choice.
- [ ] Document install, launch, update, backup and uninstall for each shipped method.

Keep the existing local-first behavior: installation does not activate accounts, start trading, download model weights or enable messaging. See the [current installation guide](../getting-started/installation.md) for commands that work today and the [backend checklist](backend-roadmap.md) for domain work.
