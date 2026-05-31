# Security

## Don't commit secrets

The `.gitignore` already blocks the obvious ones (`secrets.env`, `auth.json`, `*.sqlite`, etc.), but double-check before pushing. Run `scripts/audit-release.sh` — if it flags something as a possible secret, treat it as real until proven otherwise.

## Found a vulnerability?

Report it directly to the repository owner. Please don't open a public issue with secret material.
