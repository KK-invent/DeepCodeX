# Support

## Public Support Scope

Use GitHub Issues for source repository problems:

- Install or setup documentation is unclear.
- A source script fails with a reproducible error.
- `scripts/audit-release.sh` reports a false positive or misses a risky file.
- The installer or doctor output is confusing after secrets are redacted.

Do not use public issues for:

- API keys, OAuth tokens, cookies, bearer tokens, private gateway URLs, or account-specific identifiers.
- Private binary packages or app bundles.
- Screenshots that reveal keys, workspace paths, internal hosts, or user data.
- Questions about OpenAI, Codex, DeepSeek, or third-party account access.

## What To Include

- macOS version.
- Whether `/Applications/Codex.app` exists.
- Whether `/Applications/Deepcodex.app` exists.
- Whether this came from source checkout or a private preview package.
- Redacted output from `scripts/preflight-mac.sh` or `deepcodex-doctor.py`.
- The exact command that failed.

## Security Reports

For suspected security issues, follow `SECURITY.md` and do not open a public issue with secret material.
