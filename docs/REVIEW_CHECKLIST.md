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
- [ ] Any tracked DeepSeek visual asset has a source note and visibility decision; replace before public release if rights are unclear.
- [ ] README states this is not affiliated with upstream vendors.
- [ ] License posture is intentionally chosen before public visibility.
- [ ] GitHub Actions audit CI is enabled before public visibility.

## Runtime Validation

- [ ] `python3 -m py_compile bin/*.py` passes.
- [ ] `bin/deepcodex-image-strip-proxy.py --selftest` passes.
- [ ] On a configured machine, `bin/deepcodex-sync-upstream.py --stage` passes.
- [ ] On a configured machine, `bin/deepcodex-doctor.py` reports no failures.
- [ ] `codesign --verify --deep --strict "$DEEPCODEX_APP"` passes after apply.
