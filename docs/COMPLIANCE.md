# Compliance Notes

This repository should stay private until these boundaries are reviewed.

## What This Repository Does Not Ship

- No built `Deepcodex.app`.
- No copied `/Applications/Codex.app`.
- No `app.asar`, extracted upstream bundle, or generated app package.
- No OpenAI, Codex, DeepSeek, or third-party trademarked image assets.
- No `ccx` binary.
- No real local configuration, keys, auth state, sessions, logs, caches, memories, or SQLite databases.

## Upstream Dependency Boundary

The scripts expect users to install the official Codex desktop app themselves. The patcher reads that local installation and builds a local private derivative on the user's own machine.

Private binary packages are a separate distribution path. They must stay out of git and must be reviewed before sharing, especially if they include an app bundle or local `ccx` runtime.

Before public release, review whether this patching model is acceptable under the upstream app's terms and any applicable distribution rules. If the answer is unclear, keep the repository private.

## Trademark Boundary

DeepCodeX, Codex, OpenAI, DeepSeek, and related marks may belong to their respective owners. This repository should not imply endorsement, affiliation, or official support.

The first private preview intentionally excludes branded icon assets. If a public icon is added later, use an original asset that does not copy protected marks.

## License Boundary

The current `LICENSE.md` is a private preview notice. Before public release, choose an explicit license for the original scripts and documentation, or keep the project source-available without open-source reuse rights.

Do not choose a public license until the upstream binary and trademark boundaries are reviewed.

## Public Release Checklist

- `scripts/audit-release.sh` passes.
- `git ls-files` contains only expected source, docs, templates, and audit scripts.
- No `.app`, `.asar`, `.dmg`, `.pkg`, `.sqlite`, `.db`, `.log`, `.env`, `auth.json`, or session files are tracked.
- README clearly distinguishes source-build users from private-package users who do not have Codex installed.
- README clearly says real DeepSeek API keys are user-provided and never committed.
- License decision is intentional.
- GitHub repository is private until the maintainer completes review.
