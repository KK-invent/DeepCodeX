<p align="center">
  <img src="assets/brand/deepcodex-icon.svg" alt="DeepCodeX original route icon" width="156">
</p>

<p align="center">
  <img src="assets/brand/deepcodex-logo.svg" alt="DeepCodeX" width="560">
</p>

# DeepCodeX

中文文档：[README.zh-CN.md](README.zh-CN.md)

DeepCodeX is a safety-focused wrapper and maintenance toolkit for rebuilding a local DeepCodex app from an already installed Codex desktop app, then routing it through DeepSeek-compatible local services.

This source repository is prepared as a sanitized maintainer toolkit. It intentionally does not contain a built `.app`, `app.asar`, upstream Codex assets, API keys, auth files, logs, caches, sessions, SQLite databases, or third-party binary payloads.

The visual identity uses original DeepCodeX artwork. See [assets/brand/SOURCES.md](assets/brand/SOURCES.md) and [docs/COMPLIANCE.md](docs/COMPLIANCE.md) for source and trademark boundaries.

DeepCodeX is an unofficial project. It is not affiliated with, endorsed by, or supported by OpenAI, Codex, DeepSeek, or their respective owners.

## Public Source And Private Binary Preview

The source repository is the public-ready surface. Binary preview packages are a separate private distribution path until upstream terms review explicitly approves public binary release assets.

If you received a private GitHub Release, use the ordinary-user package:

```text
DeepCodeX-mac.zip
DeepCodeX-mac.zip.sha256
```

Verify it before opening:

```bash
shasum -a 256 -c DeepCodeX-mac.zip.sha256
```

Then unzip `DeepCodeX-mac.zip` and run `Install-DeepCodeX.command`. The installer checks whether `/Applications/Codex.app` exists. If Codex is missing, install the official Codex desktop app first, then rerun the installer.

Do not use the source checkout as a direct app download. The repository is a maintainer toolkit and intentionally does not include the built app or upstream Codex binaries.

## Scope

![DeepCodeX routing architecture](assets/brand/routing-architecture.svg)

![DeepCodeX install detection flow](assets/brand/install-detection-flow.svg)

![DeepCodeX safety scorecard](assets/brand/safety-scorecard.svg)

Included:

- `bin/deepcodex-sync-upstream.py` rebuilds a staged DeepCodex bundle from the local `/Applications/Codex.app`, applies DeepSeek-only patches, signs it locally, and verifies it before replacement.
- `bin/deepcodex-doctor.py` checks the local DeepCodex bundle, routing, model picker, launchd services, signing-sensitive settings, and runtime guards.
- `bin/deepcodex-configure-deepseek.py` provides the single CLI entry for setting the upstream DeepSeek base URL and API key without printing secrets.
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
- Official Codex desktop app installed at `/Applications/Codex.app`, or set `CODEX_APP`. The private installer checks this first and points missing users to the [official Codex page](https://openai.com/codex/).
- A local DeepCodeX home directory, defaulting to `~/.codex-deepseek`, or set `DEEPCODEX_HOME`.
- A local `ccx` compatible service if you use the DeepSeek route expected by the current scripts.
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
cp config/secrets.env.example "$DEEPCODEX_HOME/secrets.env"
"$DEEPCODEX_HOME/bin/deepcodex-configure-deepseek.py"
"$DEEPCODEX_HOME/bin/deepcodex-sync-upstream.py" --stage
```

Only run `--apply` after `--stage` succeeds and you have reviewed the output:

```bash
"$DEEPCODEX_HOME/bin/deepcodex-sync-upstream.py" --apply
"$DEEPCODEX_HOME/bin/deepcodex-doctor.py"
codesign --verify --deep --strict "$DEEPCODEX_APP"
```

## Safety Gates

Before pushing or making the repository public, run:

```bash
scripts/audit-release.sh
scripts/audit-public-release.sh --repo KK-invent/DeepCodeX
git status --short
```

The audit checks Python syntax, the image-strip self-test, high-confidence secret patterns, and banned runtime/binary filenames.

## Compliance Boundary

This project is a patcher and local maintenance toolkit. It does not redistribute Codex desktop, OpenAI assets, DeepSeek assets, or third-party binaries. The source code and original documentation/artwork are licensed under the MIT License; that license does not grant rights to upstream apps, trademarks, service accounts, API keys, or third-party assets. See [docs/COMPLIANCE.md](docs/COMPLIANCE.md) before changing the repository visibility from private to public.

Release history is tracked in [CHANGELOG.md](CHANGELOG.md).

## Contributing And Support

Before opening an issue or pull request, read [CONTRIBUTING.md](CONTRIBUTING.md), [SUPPORT.md](SUPPORT.md), and [SECURITY.md](SECURITY.md). Do not paste API keys, tokens, cookies, private gateway URLs, app bundles, logs with secrets, or screenshots containing credentials into public GitHub threads.

## Current Release Status

The source license is now chosen. Do not make the repository public until:

- The audit script passes.
- The public-release audit blockers are resolved.
- The committed file list is manually reviewed.
- The legal/compliance notes are accepted.
- GitHub detects the committed MIT License.
- Private binary release assets are removed, or public binary distribution is explicitly approved in `docs/UPSTREAM_TERMS_APPROVAL.md`.
- A fresh local `--stage` and `doctor` verification pass on the target Codex version.
