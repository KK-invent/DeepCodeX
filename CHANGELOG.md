# Changelog

All notable changes for the DeepCodeX preview and release preparation are tracked here.

## v0.1.0

- Prepared the first planned public source release identity with `VERSION` and public source release notes.
- Added source-only public release publish and verification scripts that refuse uploaded binary assets.
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
