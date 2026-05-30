## Summary

-

## Checks

- [ ] `scripts/audit-release.sh` passes.
- [ ] No `.app`, `.asar`, `.dmg`, `.pkg`, `.zip`, runtime binary, cache, log, session, SQLite database, auth file, or real config is committed.
- [ ] No API key, token, cookie, private gateway URL, or private local path is included.
- [ ] Docs are updated for install, release, compliance, or user-facing behavior changes.

## Release-Sensitive Changes

- [ ] This does not change release, packaging, compliance, brand, or audit behavior.
- [ ] If it does, the relevant checklist in `docs/PUBLIC_RELEASE_CHECKLIST.md` and `docs/REVIEW_CHECKLIST.md` was reviewed.
