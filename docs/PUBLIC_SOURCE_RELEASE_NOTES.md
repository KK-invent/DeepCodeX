# DeepCodeX v0.1.1 Public Source Release Notes

DeepCodeX v0.1.1 is the first public source release meant to be usable by a stranger from source without a private `ccx` runtime.

## What Is Included

- Source-only maintenance scripts for rebuilding a local DeepCodex app from a user-installed Codex desktop app.
- A pure Python DeepSeek bridge that translates Codex Responses-style requests to a DeepSeek-compatible Chat Completions upstream.
- DeepSeek-compatible configuration helper that avoids printing API keys.
- Local doctor, preflight, backup, log pruning, launchd, and image-strip helper scripts.
- English and Chinese installation, troubleshooting, privacy, compliance, release, and review documentation.
- Original DeepCodeX brand artwork and diagrams.
- Public repository operations files: contributing guide, support guide, security policy, issue templates, and pull request template.
- Release readiness gates for source audit, public metadata, upstream approval, CI, and private binary asset posture.

## What Is Not Included

- OpenAI Codex desktop app binaries or resources.
- DeepCodex `.app` builds.
- `app.asar` or extracted upstream frontend bundles.
- Real API keys, auth files, logs, sessions, caches, memories, SQLite databases, or local runtime state.
- Public binary release assets unless explicitly approved in `docs/UPSTREAM_TERMS_APPROVAL.md`.

## Public Release Preconditions

Before publishing this release publicly:

- `scripts/audit-release.sh` passes.
- `scripts/audit-public-release.sh --repo KK-invent/DeepCodeX --release-tag private-preview-YYYYMMDD-HHMMSS` passes.
- `scripts/verify-github-public-metadata.sh --repo KK-invent/DeepCodeX` passes.
- GitHub Actions audit CI is enabled.
- `docs/UPSTREAM_TERMS_APPROVAL.md` records public source approval.
- `scripts/verify-upstream-terms-approval.sh` passes against the approval record.
- Private preview binary assets are removed unless public binary distribution is explicitly approved.
- `scripts/prepare-public-source-release.sh --repo KK-invent/DeepCodeX --private-release-tag private-preview-YYYYMMDD-HHMMSS --dry-run` passes for private preflight planning.
- `scripts/publish-public-source-release.sh --repo KK-invent/DeepCodeX --private-release-tag private-preview-YYYYMMDD-HHMMSS --dry-run --skip-public-check` passes for private preflight planning.
- `scripts/publish-public-source-release.sh --repo KK-invent/DeepCodeX --private-release-tag private-preview-YYYYMMDD-HHMMSS --dry-run` passes after the repository is public and before creating the public source release.

## Install Notes

The source repository is not a direct app download. Users need the official Codex desktop app installed at `/Applications/Codex.app` before DeepCodeX can rebuild a local DeepCodex app.

Users also need their own DeepSeek-compatible base URL and API key. The normal public-source path is:

```bash
scripts/install-local.sh
~/.codex-deepseek/bin/deepcodex-configure-deepseek.py --restart-services
~/.codex-deepseek/bin/deepcodex-sync-upstream.py --stage
~/.codex-deepseek/bin/deepcodex-sync-upstream.py --apply
~/.codex-deepseek/bin/deepcodex-doctor.py
```

Private preview binary packages, if shared separately, remain private unless public binary distribution is approved.
