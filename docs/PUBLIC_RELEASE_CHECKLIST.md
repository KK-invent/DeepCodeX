# Public Source Release Checklist

This checklist tracks the public source release posture for DeepCodeX.

Current posture: the repository may stay public as a source-only project. Uploaded app packages, zip archives, or checksum assets still need explicit public-binary approval before they are exposed from a public release.

## Hard Blockers

- Confirm the public license posture:
  - `LICENSE.md` is MIT for original DeepCodeX source, documentation, scripts, and original artwork.
  - The license does not grant rights to upstream apps, trademarks, service accounts, API keys, or third-party assets.
  - GitHub license detection shows `mit` after the license commit is pushed.
- Confirm the public source release identity:
  - `VERSION` contains the semver version.
  - `docs/PUBLIC_SOURCE_RELEASE_NOTES.md` describes what is included, not included, and still gated.
- Decide the visual-asset posture:
  - Keep only original DeepCodeX artwork in `assets/brand`.
  - Do not track third-party official or derived marks in the public source release.
- Review the upstream Codex patching model against applicable app terms before presenting the project as public. Track evidence in `docs/UPSTREAM_TERMS_REVIEW.md`.
- Complete `docs/UPSTREAM_TERMS_APPROVAL.md` from `docs/UPSTREAM_TERMS_APPROVAL_TEMPLATE.md` before treating the upstream blocker as resolved.
- Decide the release-asset posture before changing repository visibility:
  - Public source release with no uploaded app/binary assets, or
  - Public binary release only after explicit `public-binary-release: approved` signoff.
- Confirm GitHub Actions audit CI is active from `.github/workflows/audit.yml`.
  - If it needs to be recreated from `docs/GITHUB_ACTIONS_AUDIT_TEMPLATE.yml`, use a GitHub token with `workflow` scope and run `scripts/enable-github-actions-audit.sh`.
  - Confirm the latest `Audit` workflow run passed on `main`.

## Required Commands

Run the normal source gate:

```bash
scripts/audit-release.sh
scripts/verify-public-release-git-state.sh
scripts/verify-upstream-terms-approval.sh
```

This gate allows ignored local release caches such as `dist/`, but fails if app bundles, zip packages, runtime state, logs, auth files, caches, or private config become tracked source files.

Run the public-release gate:

```bash
scripts/audit-public-release.sh --repo KK-invent/DeepCodeX --release-tag private-preview-YYYYMMDD-HHMMSS
```

When the private preview release still has zip or checksum assets, this gate fails until public binary distribution is approved or those assets are removed before public visibility.

Run the GitHub public metadata gate:

```bash
scripts/verify-github-public-metadata.sh --repo KK-invent/DeepCodeX
```

Confirm GitHub Actions audit CI:

```bash
gh workflow list --repo KK-invent/DeepCodeX
gh run list --repo KK-invent/DeepCodeX --workflow Audit --limit 5
scripts/verify-github-actions-audit.sh --repo KK-invent/DeepCodeX --commit $(git rev-parse HEAD)
```

Before the visibility switch, run the public-release gate without `--require-public`; it should pass after all decision blockers are resolved:

```bash
scripts/audit-public-release.sh --repo KK-invent/DeepCodeX --release-tag private-preview-YYYYMMDD-HHMMSS
scripts/prepare-public-source-release.sh --repo KK-invent/DeepCodeX --private-release-tag private-preview-YYYYMMDD-HHMMSS --dry-run
scripts/publish-public-source-release.sh --repo KK-invent/DeepCodeX --private-release-tag private-preview-YYYYMMDD-HHMMSS --dry-run --skip-public-check
```

Do not omit `--private-release-tag` while a private preview release exists. If there has never been a private binary release, pass `--no-private-release-assets`; the script will scan GitHub releases and fail if any binary or checksum assets exist.

The supplied private preview tag must exist on GitHub; a typo or deleted release is a public-release blocker.

After resolving the blockers and switching visibility to public, run:

```bash
scripts/audit-public-release.sh --repo KK-invent/DeepCodeX --require-public
scripts/publish-public-source-release.sh --repo KK-invent/DeepCodeX --private-release-tag private-preview-YYYYMMDD-HHMMSS --dry-run
```

If `docs/UPSTREAM_TERMS_APPROVAL.md` says `public-binary-release: private-only`, remove the private preview zip assets before changing visibility:

```bash
scripts/prepare-public-source-release.sh --repo KK-invent/DeepCodeX --private-release-tag private-preview-YYYYMMDD-HHMMSS --delete-binary-assets --hide-private-release
```

The preparation script verifies the private preview release target before deletion, then verifies that binary/checksum assets are gone afterward. `--hide-private-release` marks the old private preview Release as a draft after its binary/checksum assets are removed, so the public repository does not expose a confusing empty private-preview prerelease.

After the repository is public, create and verify the source-only release:

```bash
scripts/publish-public-source-release.sh --repo KK-invent/DeepCodeX --private-release-tag private-preview-YYYYMMDD-HHMMSS
scripts/verify-public-source-release.sh --repo KK-invent/DeepCodeX --tag v$(cat VERSION) --expected-target $(git rev-parse HEAD)
```

## GitHub Metadata

- Description is set.
- Homepage points to the README.
- Topics include `ai`, `codex`, `deepseek`, `developer-tools`, and `macos`.
- The rendered English README and Chinese README both show the non-affiliation boundary.
- The Chinese README uses only Chinese-localized diagrams.
- GitHub detects the MIT License.
- `VERSION` and `docs/PUBLIC_SOURCE_RELEASE_NOTES.md` are present.
- `CONTRIBUTING.md`, `SUPPORT.md`, issue templates, and the pull request template are present.
- Source-only release helper scripts are present: `scripts/publish-public-source-release.sh` and `scripts/verify-public-source-release.sh`.
- GitHub labels used by issue templates exist: `bug`, `documentation`, `release`.
- `scripts/verify-public-release-git-state.sh` confirms local `main` matches `origin/main`.
- `scripts/verify-github-actions-audit.sh --repo KK-invent/DeepCodeX --commit $(git rev-parse HEAD)` passes for the exact release commit.
- `scripts/verify-upstream-terms-approval.sh` confirms reviewer, review date, reviewed terms, public binary posture, and that the approval date is current with `docs/UPSTREAM_TERMS_REVIEW.md` before any public visibility change.

## Release Asset Rules

The private-preview ordinary-user release should expose exactly:

```text
DeepCodeX-mac.zip
DeepCodeX-mac.zip.sha256
```

Do not publish maintainer-only or runtime-variant packages as default public downloads.

For public repository visibility, do not expose uploaded app, package, archive, or checksum release assets unless `docs/UPSTREAM_TERMS_APPROVAL.md` explicitly approves public binary distribution. If the approval says `public-binary-release: private-only`, delete private preview binary assets or keep the repository private.
