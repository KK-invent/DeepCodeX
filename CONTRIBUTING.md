# Contributing

Thanks for helping improve DeepCodeX. This repository is a source-only maintenance toolkit, not a binary distribution of Codex or DeepCodex.

## Before Opening An Issue

- Search existing issues first.
- Read `README.md`, `docs/INSTALL.zh-CN.md`, and `docs/TROUBLESHOOTING.zh-CN.md`.
- Run the relevant local check:

```bash
scripts/audit-release.sh
scripts/preflight-mac.sh
```

For an installed DeepCodeX app, also run:

```bash
"$DEEPCODEX_HOME/bin/deepcodex-doctor.py"
```

Redact local paths, API keys, tokens, cookies, account identifiers, request IDs, and any private gateway URLs before sharing output.

## Pull Request Rules

Every pull request should keep the public source boundary intact:

- Do not commit `.app`, `.asar`, `.dmg`, `.pkg`, `.zip`, runtime binaries, caches, logs, sessions, SQLite databases, auth files, or real config.
- Do not commit OpenAI, Codex, DeepSeek, or third-party trademarked image assets unless the public visibility decision is recorded in `docs/COMPLIANCE.md`.
- Do not print secrets in scripts, tests, logs, or error messages.
- Keep changes small and focused.
- Update docs when changing install, packaging, release, or compliance behavior.
- Run `scripts/audit-release.sh` before pushing.

## Development Setup

```bash
scripts/install-local.sh
scripts/preflight-mac.sh
cp config/secrets.env.example "$DEEPCODEX_HOME/secrets.env"
"$DEEPCODEX_HOME/bin/deepcodex-configure-deepseek.py"
```

Only use real API keys in local ignored files. Do not paste keys into issues, pull requests, screenshots, or chat logs.

## Release-Sensitive Changes

Changes to any of these files require extra review:

- `scripts/audit-release.sh`
- `scripts/audit-public-release.sh`
- `scripts/package-private-release.sh`
- `scripts/publish-private-release.sh`
- `scripts/prepare-public-source-release.sh`
- `docs/COMPLIANCE.md`
- `docs/PUBLIC_RELEASE_CHECKLIST.md`
- `docs/UPSTREAM_TERMS_REVIEW.md`
- `docs/UPSTREAM_TERMS_APPROVAL_TEMPLATE.md`
- `assets/brand/*`

Before changing repository visibility or release assets, run the public gates described in `docs/PUBLISHING.md`.
