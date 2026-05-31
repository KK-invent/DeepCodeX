# Contributing

Thanks for your interest in DeepCodeX!

## Before you open an issue

1. Search existing issues — someone might've hit the same thing.
2. Skim the [README](README.md) and [troubleshooting guide](docs/TROUBLESHOOTING.zh-CN.md).
3. Run the doctor: `~/.codex-deepseek/bin/deepcodex-doctor.py`
4. **Redact secrets** (API keys, tokens, paths with your username) before pasting output.

## Pull requests

The basics:

- Run `scripts/audit-release.sh` before pushing — it'll catch most problems.
- Don't commit binaries, `.app` bundles, real config, logs, or caches. The audit will yell at you if you try.
- Don't print secrets in code, tests, or error messages.
- Keep PRs small and update docs if you change install or packaging behavior.

## Dev setup

```bash
scripts/install-local.sh
scripts/preflight-mac.sh
cp config/secrets.env.example "$DEEPCODEX_HOME/secrets.env"
"$DEEPCODEX_HOME/bin/deepcodex-configure-deepseek.py"
```

Real API keys go in local ignored files only — never in issues, PRs, or screenshots.

## Release-sensitive files

These need extra review since they affect what ships:

`scripts/audit-release.sh` · `scripts/audit-public-release.sh` · `scripts/package-private-release.sh` · `docs/COMPLIANCE.md` · `docs/UPSTREAM_TERMS_REVIEW.md` · `assets/brand/*`
