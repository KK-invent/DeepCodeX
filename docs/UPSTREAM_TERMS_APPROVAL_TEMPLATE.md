# Upstream Terms Approval Template

Copy this file to `docs/UPSTREAM_TERMS_APPROVAL.md` only after the maintainer or legal reviewer has approved the public release posture.

Do not fill this as a placeholder. The public release audit treats exact approval markers as a release gate.

```text
approval-status: approved
reviewer:
review-date:
terms-reviewed:
  - OpenAI Terms of Use, effective 2026-01-01
  - OpenAI Service Terms, updated 2026-01-09
  - OpenAI Services Agreement / applicable account agreement
  - OpenAI Codex product page
public-source-release: approved
public-binary-release: private-only
notes:
  - Public source release is approved because the repository does not contain upstream Codex binaries, app.asar, official assets, auth state, logs, sessions, caches, or API keys.
  - Public binary release assets are not approved unless this field is changed to approved after separate distribution review.
```

Allowed `public-binary-release` values:

- `private-only`: public source is approved, but binary assets must stay private or be removed before public visibility.
- `approved`: public binary assets are explicitly approved.

If `public-binary-release` is `private-only`, do not make a GitHub repository public while private preview zip assets remain attached to its releases.
