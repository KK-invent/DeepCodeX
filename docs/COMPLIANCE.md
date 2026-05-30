# Compliance Notes

This repository should stay private until the remaining upstream terms and CI boundaries are reviewed.

## What This Repository Does Not Ship

- No built `Deepcodex.app`.
- No copied `/Applications/Codex.app`.
- No `app.asar`, extracted upstream bundle, or generated app package.
- No OpenAI, Codex, DeepSeek, or third-party trademarked image assets.
- Public-facing DeepCodeX image assets are original project artwork; see `assets/brand/SOURCES.md`.
- No `ccx` binary.
- No real local configuration, keys, auth state, sessions, logs, caches, memories, or SQLite databases.

## Upstream Dependency Boundary

The scripts expect users to install the official Codex desktop app themselves. The patcher reads that local installation and builds a local private derivative on the user's own machine.

Private binary packages are a separate distribution path. They must stay out of git and must be reviewed before sharing, especially if they include an app bundle or local `ccx` runtime. They must not become public release assets unless public binary distribution is explicitly approved in `docs/UPSTREAM_TERMS_APPROVAL.md`.

Before public release, review whether this patching model is acceptable under the upstream app's terms and any applicable distribution rules. If the answer is unclear, keep the repository private.

## Trademark Boundary

DeepCodeX, Codex, OpenAI, DeepSeek, and related marks may belong to their respective owners. This repository should not imply endorsement, affiliation, or official support.

The public-facing repository should use original DeepCodeX artwork and should not imply visual endorsement by DeepSeek. Keep the source note in `assets/brand/SOURCES.md`. If official or derived third-party marks are reintroduced, public visibility requires explicit approval.

## License Boundary

The original DeepCodeX source code, documentation, scripts, and original public-facing artwork are licensed under the MIT License in `LICENSE.md`.

The MIT License does not grant rights to:

- The upstream Codex desktop app or any upstream app bundle content.
- OpenAI, Codex, DeepSeek, or third-party trademarks.
- DeepSeek or OpenAI service accounts, API keys, hosted services, or service names.
- Third-party binaries, runtimes, or assets that are not tracked in this repository.

Do not present the project as public-ready until the upstream patching model has been reviewed against the applicable upstream terms. Track that review in `docs/UPSTREAM_TERMS_REVIEW.md`.

## Public Release Checklist

- `scripts/audit-release.sh` passes.
- `scripts/audit-public-release.sh --repo KK-invent/DeepCodeX` passes, except for an intentional private-repository check before the final visibility switch.
- `git ls-files` contains only expected source, docs, templates, and audit scripts.
- No `.app`, `.asar`, `.dmg`, `.pkg`, `.sqlite`, `.db`, `.log`, `.env`, `auth.json`, or session files are tracked.
- README clearly says the private package checks for official Codex and guides missing users to install it.
- README clearly says real DeepSeek API keys are user-provided and never committed.
- README clearly states this is unofficial and not affiliated with upstream vendors.
- Public-facing visual assets are original, or any third-party visual assets have explicit approval for the intended visibility.
- GitHub detects the MIT License after the license commit is pushed.
- GitHub Actions audit CI is enabled before public visibility.
- Private preview binary release assets are removed before public visibility unless public binary distribution is explicitly approved.
- GitHub repository is private until the maintainer completes review.
