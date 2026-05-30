# DeepCodeX v0.1.0 Public Source Release Notes

DeepCodeX v0.1.0 is the first planned public source release.

## What Is Included

- Source-only maintenance scripts for rebuilding a local DeepCodex app from a user-installed Codex desktop app.
- DeepSeek-compatible configuration helper that avoids printing API keys.
- Local doctor, preflight, backup, log pruning, and image-strip helper scripts.
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
- `scripts/audit-public-release.sh --repo KK-invent/DeepCodeX` passes.
- `scripts/verify-github-public-metadata.sh --repo KK-invent/DeepCodeX` passes.
- GitHub Actions audit CI is enabled.
- `docs/UPSTREAM_TERMS_APPROVAL.md` records public source approval.
- Private preview binary assets are removed unless public binary distribution is explicitly approved.
- `scripts/publish-public-source-release.sh --repo KK-invent/DeepCodeX --dry-run` passes before creating the public source release.

## Install Notes

The source repository is not a direct app download. Users need the official Codex desktop app installed at `/Applications/Codex.app` before DeepCodeX can rebuild a local DeepCodex app.

Private preview binary packages, if shared separately, remain private unless public binary distribution is approved.
