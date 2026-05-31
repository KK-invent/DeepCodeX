<p align="center">
  <img src="assets/brand/deepcodex-hero.svg" alt="DeepCodeX light blue hero" width="860">
</p>

# DeepCodeX

中文文档：[README.zh-CN.md](README.zh-CN.md)

DeepCodeX is a safety-focused wrapper and maintenance toolkit for rebuilding a local DeepCodex app from an already installed Codex desktop app, then routing it through DeepSeek-compatible local services.

This source repository is prepared as a sanitized maintainer toolkit. It intentionally does not contain a built `.app`, `app.asar`, upstream Codex assets, API keys, auth files, logs, caches, sessions, SQLite databases, or third-party binary payloads.

The visual identity uses original DeepCodeX artwork. See [assets/brand/SOURCES.md](assets/brand/SOURCES.md) and [docs/COMPLIANCE.md](docs/COMPLIANCE.md) for source and trademark boundaries.

DeepCodeX is an unofficial project. It is not affiliated with, endorsed by, or supported by OpenAI, Codex, DeepSeek, or their respective owners.

## Quick Start

### No Codex yet? Do this first

DeepCodeX does not ship Codex itself. Install the official Codex desktop app from [OpenAI Codex](https://openai.com/codex/) first and make sure it exists at `/Applications/Codex.app`, then come back and run the steps below. If Codex lives somewhere else, set `CODEX_APP=/path/to/Codex.app` before running the installer.

Official Codex download page: https://openai.com/codex/

DeepCodeX no longer depends on the private `ccx` runtime. The local translation layer is `bin/deepcodex-deepseek-bridge.py`, a pure Python service that listens on `127.0.0.1:3000`.

You still need to provide your own DeepSeek-compatible endpoint and API key. The maintainer does not provide either value.

```bash
# 1. Install the official Codex desktop app at /Applications/Codex.app.

# 2. Clone this public source repository.
git clone https://github.com/KK-invent/DeepCodeX.git
cd DeepCodeX

# 3. Install local scripts, config skeletons, and launchd bridge services.
scripts/install-local.sh

# 4. Enter your DeepSeek-compatible base URL and API key.
~/.codex-deepseek/bin/deepcodex-configure-deepseek.py --restart-services

# 5. Rebuild DeepCodeX from your local Codex.app.
~/.codex-deepseek/bin/deepcodex-sync-upstream.py --stage
~/.codex-deepseek/bin/deepcodex-sync-upstream.py --apply

# 6. Verify the local install.
~/.codex-deepseek/bin/deepcodex-doctor.py
```

Use `https://api.deepseek.com` as the base URL if your Mac can reach the official DeepSeek API. If you use a company or third-party OpenAI-compatible gateway, enter that gateway URL instead. Do not enter `127.0.0.1:3100`; that is DeepCodeX's internal shim address.

After the app exists, the same settings can be changed from the DeepCodeX app menu: **Configure DeepSeek...**.

## Scope

![DeepCodeX routing architecture](assets/brand/routing-architecture.svg)

![DeepCodeX install detection flow](assets/brand/install-detection-flow.svg)

![DeepCodeX safety scorecard](assets/brand/safety-scorecard.svg)

Included:

- `bin/deepcodex-sync-upstream.py` rebuilds a staged DeepCodex bundle from the local `/Applications/Codex.app`, applies DeepSeek-only patches, signs it locally, and verifies it before replacement.
- `bin/deepcodex-doctor.py` checks the local DeepCodex bundle, routing, model picker, launchd services, signing-sensitive settings, and runtime guards.
- `bin/deepcodex-configure-deepseek.py` provides the single CLI entry for setting the upstream DeepSeek base URL and API key without printing secrets.
- `bin/deepcodex-deepseek-bridge.py` replaces the former private `ccx` runtime with a pure Python Responses API to DeepSeek Chat Completions translator.
- `bin/deepcodex-image-strip-proxy.py` removes or converts image blocks before forwarding text-only requests to DeepSeek.
- `bin/deepcodex-log-prune.py` and `bin/deepcodex-backup.sh` keep local logs and backups bounded.

Not included:

- OpenAI Codex desktop app binaries or resources.
- DeepCodex `.app` builds.
- `app.asar` or extracted upstream frontend bundles.
- Real `secrets.env`, `auth.json`, `ccx/.config/config.json`, sessions, logs, memories, caches, or SQLite state.
- The local `ccx` binary.
- OpenAI Codex trademarked image assets.

## Requirements

- macOS.
- Official Codex desktop app installed at `/Applications/Codex.app`, or set `CODEX_APP`.
- A local DeepCodeX home directory, defaulting to `~/.codex-deepseek`, or set `DEEPCODEX_HOME`.
- A DeepSeek-compatible base URL and API key supplied by you.
- Python 3.10+ recommended.

Important environment variables:

```bash
export DEEPCODEX_HOME="$HOME/.codex-deepseek"
export CODEX_APP="/Applications/Codex.app"
export DEEPCODEX_APP="/Applications/Deepcodex.app"
export DEEPCODEX_LAUNCHD_DOMAIN="com.deepcodex"
```

## Local Setup

For Chinese first-time installation guidance, see [docs/INSTALL.zh-CN.md](docs/INSTALL.zh-CN.md).

```bash
scripts/install-local.sh
scripts/preflight-mac.sh
"$DEEPCODEX_HOME/bin/deepcodex-configure-deepseek.py" --restart-services
"$DEEPCODEX_HOME/bin/deepcodex-sync-upstream.py" --stage
```

Only run `--apply` after `--stage` succeeds and you have reviewed the output:

```bash
"$DEEPCODEX_HOME/bin/deepcodex-sync-upstream.py" --apply
"$DEEPCODEX_HOME/bin/deepcodex-doctor.py"
codesign --verify --deep --strict "$DEEPCODEX_APP"
```

## Safety Gates

Before pushing release changes, run:

```bash
scripts/audit-release.sh
git status --short
```

The audit checks Python syntax, shell syntax, documentation links, image-strip and bridge self-tests, high-confidence secret patterns, banned runtime/binary filenames outside local release caches, and tracked source payload filenames.

## Compliance Boundary

This project is a patcher and local maintenance toolkit. It does not redistribute Codex desktop, OpenAI assets, DeepSeek assets, service accounts, API keys, or third-party binaries. The source code and original documentation/artwork are licensed under the MIT License; that license does not grant rights to upstream apps, trademarks, service accounts, API keys, or third-party assets. See [docs/COMPLIANCE.md](docs/COMPLIANCE.md) before changing distribution behavior.

Release history is tracked in [CHANGELOG.md](CHANGELOG.md).

Planned public source release notes are in [docs/PUBLIC_SOURCE_RELEASE_NOTES.md](docs/PUBLIC_SOURCE_RELEASE_NOTES.md). The current source release version is tracked in [VERSION](VERSION).

## Contributing And Support

Before opening an issue or pull request, read [CONTRIBUTING.md](CONTRIBUTING.md), [SUPPORT.md](SUPPORT.md), and [SECURITY.md](SECURITY.md). Do not paste API keys, tokens, cookies, private gateway URLs, app bundles, logs with secrets, or screenshots containing credentials into public GitHub threads.

## Current Release Status

The repository is public source. Public GitHub releases are source-only unless `docs/UPSTREAM_TERMS_APPROVAL.md` explicitly approves public binary release assets. For user-ready bridge changes, verify at least:

- `scripts/audit-release.sh`
- `~/.codex-deepseek/bin/deepcodex-sync-upstream.py --stage`
- `~/.codex-deepseek/bin/deepcodex-sync-upstream.py --apply`
- `~/.codex-deepseek/bin/deepcodex-doctor.py`
- One real text request and one real tool-call request in DeepCodeX.app.
