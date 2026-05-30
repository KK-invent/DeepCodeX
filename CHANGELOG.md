# Changelog

All notable changes for the DeepCodeX preview and release preparation are tracked here.

## v0.1.0

- Prepared the first planned public source release identity with `VERSION` and public source release notes.
- Added source-only public release publish and verification scripts that refuse uploaded binary assets.
- Hardened source audit to fail on tracked runtime, package, cache, or private-state payload filenames while allowing ignored local release caches.
- Refreshed the upstream-terms review packet with current Codex/OpenAI source links and explicit GitHub Actions scope guidance.
- Broadened release payload guards for common archive/checksum formats and recursive brand raster assets.
- Updated the reviewer runtime checklist so Python syntax checks do not leave banned `__pycache__` files in the source tree.
- Restricted public source release public-check bypass to dry-run planning while the repository is still private.
- Required explicit private release asset inspection, or an explicit no-private-assets assertion, before public source release preparation can pass.
- Made the no-private-assets path scan GitHub releases for binary/checksum assets instead of relying on maintainer assertion alone.
- Validated supplied private preview release tags before inspecting assets so typos cannot pass as empty releases.
- Simplified the project logo into a standalone uppercase `X` with a Codex-style purple-to-blue gradient.
- Public release remains gated on upstream terms approval and GitHub Actions audit CI.

## private-preview-20260530-074240

- Published the private Mac preview package as `DeepCodeX-mac.zip` with a matching `.sha256` file.
- Added first-install guidance for users who already have Codex and for users who need to install Codex first.
- Added Chinese-localized README diagrams so the Chinese entry point does not show English diagram copy.
- Replaced DeepSeek official/derived icon assets with an original gradient `X` mark for public-facing artwork.
- Replaced the private-preview license notice with the MIT License for original DeepCodeX source, documentation, scripts, and original artwork.
- Added upstream-terms review tracking and a helper for enabling GitHub Actions audit CI once the token has `workflow` scope.
- Split public source release readiness from private binary preview distribution, with an approval template and audit guard for public binary assets.
- Added a public source release preparation script that can dry-run or remove private preview binary assets before GitHub visibility changes.
- Added contributing, support, issue template, and pull request template files for public repository operations.
- Added GitHub public metadata verification for issue-template labels, topics, homepage, description, and license detection.
- Added release asset verification to keep GitHub Release downloads concise and predictable.
- Added a public-release readiness audit and checklist for license, brand, upstream-terms, CI, and GitHub metadata blockers.
- Hardened the source audit against generated Python caches and local desktop metadata.
- Documented the private-preview compliance boundary for Codex and DeepSeek assets.
