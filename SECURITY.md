# Security Policy

## Secrets

Do not commit:

- `secrets.env`
- `auth.json`
- `ccx/.config/config.json`
- API keys, OAuth tokens, cookies, private keys, or bearer tokens
- session, log, cache, memory, or SQLite files

Use `config/secrets.env.example` only as a template.

## Local Audit

Run this before every push:

```bash
scripts/audit-release.sh
```

If the script reports a possible secret, treat it as real until manually disproven.

## Reporting

For the private preview, report findings directly to the repository owner. Do not paste secrets into issues, pull requests, screenshots, or chat logs.
