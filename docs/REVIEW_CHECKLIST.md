# Review Checklist

## Security

- [ ] `scripts/audit-release.sh` passes locally.
- [ ] `scripts/audit-public-release.sh --repo KK-invent/DeepCodeX` passes before public visibility.
- [ ] `git ls-files` contains no secrets, local state, logs, sessions, caches, app bundles, or upstream binaries.
- [ ] `config/secrets.env.example` contains placeholders only.
- [ ] CLI and GUI configuration paths do not print API keys.

## Reusability

- [ ] `DEEPCODEX_HOME`, `CODEX_APP`, and `DEEPCODEX_APP` are configurable.
- [ ] Scripts do not depend on a specific macOS username.
- [ ] README explains prerequisites and the expected local `ccx` service boundary.
- [ ] Missing optional icon assets do not block a staged build.

## Compliance

- [ ] No upstream app binary or `app.asar` is tracked.
- [ ] Any tracked third-party visual asset has a source note and visibility decision; replace before public release if rights are unclear.
- [ ] README states this is not affiliated with upstream vendors.
- [ ] `CONTRIBUTING.md`, `SUPPORT.md`, and GitHub issue/PR templates are present for public repository operations.
- [ ] GitHub detects the committed MIT License before public visibility.
- [ ] Upstream patching terms are reviewed and recorded in `docs/UPSTREAM_TERMS_REVIEW.md`.
- [ ] `docs/UPSTREAM_TERMS_APPROVAL.md` exists only after real approval and records whether public binary release assets are approved or private-only.
- [ ] Private preview binary release assets are removed before public visibility unless public binary distribution is approved.
- [ ] `scripts/prepare-public-source-release.sh --repo KK-invent/DeepCodeX --private-release-tag private-preview-YYYYMMDD-HHMMSS --dry-run` passes.
- [ ] GitHub Actions audit CI is enabled before public visibility.

## Runtime Validation

- [ ] `python3 -m py_compile bin/*.py` passes.
- [ ] `bin/deepcodex-image-strip-proxy.py --selftest` passes.
- [ ] On a configured machine, `bin/deepcodex-sync-upstream.py --stage` passes.
- [ ] On a configured machine, `bin/deepcodex-doctor.py` reports no failures.
- [ ] `codesign --verify --deep --strict "$DEEPCODEX_APP"` passes after apply.
