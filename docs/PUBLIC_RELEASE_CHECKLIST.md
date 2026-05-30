# Public Release Checklist

This checklist is for changing DeepCodeX from private preview to a public GitHub project.

Do not make the repository public until every blocker here has a clear owner and evidence.

## Hard Blockers

- Confirm the public license posture:
  - `LICENSE.md` is MIT for original DeepCodeX source, documentation, scripts, and original artwork.
  - The license does not grant rights to upstream apps, trademarks, service accounts, API keys, or third-party assets.
  - GitHub license detection shows `mit` after the license commit is pushed.
- Confirm the public source release identity:
  - `VERSION` contains the semver version.
  - `docs/PUBLIC_SOURCE_RELEASE_NOTES.md` describes what is included, not included, and still gated.
- Decide the visual-asset posture:
  - Keep only original DeepCodeX artwork in `assets/brand`, or
  - Track third-party official or derived assets only with explicit approval for public visibility.
- Review the upstream Codex patching model against applicable app terms before presenting the project as public. Track evidence in `docs/UPSTREAM_TERMS_REVIEW.md`.
- Complete `docs/UPSTREAM_TERMS_APPROVAL.md` from `docs/UPSTREAM_TERMS_APPROVAL_TEMPLATE.md` before treating the upstream blocker as resolved.
- Decide the release-asset posture before changing repository visibility:
  - Public source release with no uploaded app/binary assets, or
  - Public binary release only after explicit `public-binary-release: approved` signoff.
- Enable GitHub Actions audit CI by copying `docs/GITHUB_ACTIONS_AUDIT_TEMPLATE.yml` to `.github/workflows/audit.yml` with a GitHub token that has `workflow` scope.
  - If `gh auth status -h github.com` does not list `workflow`, run `gh auth refresh -h github.com -s workflow`, then run `scripts/enable-github-actions-audit.sh`.

## Required Commands

Run the normal source gate:

```bash
scripts/audit-release.sh
```

This gate allows ignored local release caches such as `dist/`, but fails if app bundles, zip packages, runtime state, logs, auth files, caches, or private config become tracked source files.

Run the public-release gate:

```bash
scripts/audit-public-release.sh --repo KK-invent/DeepCodeX --release-tag private-preview-YYYYMMDD-HHMMSS
```

Run the GitHub public metadata gate:

```bash
scripts/verify-github-public-metadata.sh --repo KK-invent/DeepCodeX
```

After resolving the blockers and switching visibility to public, run:

```bash
scripts/audit-public-release.sh --repo KK-invent/DeepCodeX --require-public
scripts/publish-public-source-release.sh --repo KK-invent/DeepCodeX --dry-run
```

Before the visibility switch, run the same command without `--require-public`; it should pass after all decision blockers are resolved.

For the source-only public path, also run:

```bash
scripts/prepare-public-source-release.sh --repo KK-invent/DeepCodeX --private-release-tag private-preview-YYYYMMDD-HHMMSS --dry-run
```

If `docs/UPSTREAM_TERMS_APPROVAL.md` says `public-binary-release: private-only`, remove the private preview zip assets before changing visibility:

```bash
scripts/prepare-public-source-release.sh --repo KK-invent/DeepCodeX --private-release-tag private-preview-YYYYMMDD-HHMMSS --delete-binary-assets
```

After the repository is public, create and verify the source-only release:

```bash
scripts/publish-public-source-release.sh --repo KK-invent/DeepCodeX
scripts/verify-public-source-release.sh --repo KK-invent/DeepCodeX --tag v$(cat VERSION)
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

## Release Asset Rules

The private-preview ordinary-user release should expose exactly:

```text
DeepCodeX-mac.zip
DeepCodeX-mac.zip.sha256
```

Do not publish maintainer-only or runtime-variant packages as default public downloads.

For public repository visibility, do not expose uploaded app, package, archive, or checksum release assets unless `docs/UPSTREAM_TERMS_APPROVAL.md` explicitly approves public binary distribution. If the approval says `public-binary-release: private-only`, delete private preview binary assets or keep the repository private.
