# Changelog

## Unreleased

- Added a root `Install-DeepCodeX.command` source installer so GitHub source ZIP users can double-click through the public, no-binary install path.
- Added `START-HERE.zh-CN.txt` and updated Chinese install/troubleshooting docs for the source ZIP beginner flow.
- Extended release audit coverage with a missing-Codex smoke test for the root source installer.
- Extended Codex conversation import to sync the desktop thread database, archived sessions, shell snapshots, and session index so DeepCodeX can actually list and resume imported Codex projects.
- Extended Codex conversation import to merge Codex left-sidebar project/conversation state into DeepCodeX while preserving DeepCodeX-native chats.

## v0.1.2

Fixed a false failure in the post-apply launch check (Electron renderer path changed in newer Codex).

## v0.1.1 — Open source bridge

The big one: **DeepCodeX no longer needs the private `ccx` binary.** A pure Python bridge (`deepcodex-deepseek-bridge.py`) now handles the Responses ↔ Chat Completions translation. Anyone can clone, install, and run — just bring your own DeepSeek API key.

Also in this release:
- Self-contained install flow from source: `install-local.sh` → configure → stage → apply → doctor.
- Launchd handling cleans up stale ccx/image-strip processes before starting bridge services.
- Upstream patching updated for Codex `26.527.31326` (bootstrap, menu, model-query shape changes).
- Smoke test switched to non-streaming so staging doesn't hang on SSE.

## v0.1.0 — First public source release

Prepared the repo for public visibility:
- Source-only release scripts (no binaries allowed in public releases).
- Release audit catches leaked secrets, banned filenames, broken doc links, and stale caches.
- GitHub Actions CI on pushes and PRs to `main`.
- New logo: standalone gradient X mark (original artwork, no upstream trademarks).
- MIT License for source, docs, and original artwork.
- Upstream terms review tracking and approval gates.
- Contributing, support, and security docs for public repo operations.

## Private preview (2026-05-30)

- First private Mac preview package (`DeepCodeX-mac.zip` + SHA-256 checksum).
- Chinese-localized README diagrams.
- Install detection for all four Codex/DeepCodeX states.
- Compliance boundary documented for Codex and DeepSeek assets.
