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

## Official Source Snapshot

Observed on 2026-05-30:

- OpenAI Terms of Use were published and effective on 2026-01-01. They state that the services include associated software applications and websites.
- The Terms of Use prohibit modifying, copying, leasing, selling, or distributing OpenAI services, and prohibit attempting or assisting reverse engineering, decompiling, or discovering source code or underlying components except where prohibited by law.
- The Terms of Use say downloaded software may update automatically and may include open source software governed by its own licenses.
- The Terms of Use reserve OpenAI IP rights in the services and require use of OpenAI name and logo only according to OpenAI brand guidelines.
- OpenAI Service Terms were updated on 2026-01-09 and govern service-specific use alongside the applicable agreement.
- OpenAI Services Agreement defines services for business/developer use as including associated software, tools, developer services, documentation, and websites, and defines reverse engineering broadly.
- OpenAI's Codex product page identifies Codex as an OpenAI coding agent and says the app is available on macOS and Windows.

These notes are evidence for review, not legal approval.

## Public Release Posture

Default posture before approval:

- Public source repository: not approved.
- Public binary release assets: not approved.
- Private preview binary assets: allowed only while the GitHub repository and release remain private.

If the repository is changed to public before binary distribution is approved, remove private preview binary assets first. A public GitHub repository makes attached release assets public too.

## Decision Checklist

- [ ] Identify which OpenAI/Codex terms apply to the maintainer account and the intended users.
- [ ] Confirm whether local patching, local derivative bundle creation, and any private binary sharing are allowed.
- [ ] Confirm whether naming, screenshots, README language, and release assets avoid implying OpenAI/Codex endorsement.
- [ ] Confirm that DeepCodeX does not distribute upstream Codex binaries or protected assets in git or public release assets.
- [ ] Decide whether binary releases remain private-only even if the source repository becomes public.
- [ ] Record the reviewer, date, terms version, and conclusion in `docs/UPSTREAM_TERMS_APPROVAL.md` before treating the upstream blocker as resolved.

## Current Conclusion

The repository source boundary is clean enough for continued private review, but the upstream patching and distribution model has not been approved for a public release. Keep the repository private until this file has a recorded approval.
