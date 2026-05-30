# Upstream Terms Review

This file tracks the release decision that cannot be solved by source cleanup alone: whether the DeepCodeX local patching model is acceptable under the applicable upstream app and service terms.

Status: not approved for public release.

## Scope To Review

- DeepCodeX asks each user to install the official Codex desktop app themselves.
- The source repository does not redistribute Codex desktop, `app.asar`, upstream assets, API keys, auth state, logs, sessions, caches, SQLite databases, or third-party binary payloads.
- The patcher reads a user's local Codex installation and rebuilds a local DeepCodex app on that user's Mac.
- Private binary packages are a separate path and require stricter review before sharing.

## Official Sources To Check

Last checked: 2026-05-30.

- OpenAI Terms of Use: `https://openai.com/policies/terms-of-use/`
- OpenAI Service Terms: `https://openai.com/policies/service-terms/`
- OpenAI Services Agreement / Business Terms: `https://openai.com/policies/business-terms/`
- OpenAI Codex product page: `https://openai.com/codex/`

Use the currently applicable agreement for the account, distribution channel, and Codex desktop build involved. These pages can change, so refresh this review before changing GitHub visibility.

## Decision Checklist

- [ ] Identify which OpenAI/Codex terms apply to the maintainer account and the intended users.
- [ ] Confirm whether local patching, local derivative bundle creation, and any private binary sharing are allowed.
- [ ] Confirm whether naming, screenshots, README language, and release assets avoid implying OpenAI/Codex endorsement.
- [ ] Confirm that DeepCodeX does not distribute upstream Codex binaries or protected assets in git or public release assets.
- [ ] Decide whether binary releases remain private-only even if the source repository becomes public.
- [ ] Record the reviewer, date, terms version, and conclusion before setting `DEEPCODEX_PUBLIC_UPSTREAM_TERMS_APPROVED=1`.

## Current Conclusion

The repository source boundary is clean enough for continued private review, but the upstream patching and distribution model has not been approved for a public release. Keep the repository private until this file has a recorded approval.
