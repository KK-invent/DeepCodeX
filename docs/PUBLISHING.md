# Private GitHub Publishing Plan

Target flow:

1. Build and audit the local release candidate.
2. Commit only the sanitized release files.
3. Create a GitHub repository as private.
4. Push the initial commit.
5. Review file list and rendered README on GitHub.
6. Keep private until the compliance checklist is accepted.
7. Only then decide whether to change repository visibility to public.

## Pre-Push Commands

```bash
scripts/audit-release.sh
scripts/verify-public-release-git-state.sh
git status --short
git ls-files
```

## Private Repository Command

```bash
gh repo create DeepCodeX --private --source=. --remote=origin --push
```

If the name already exists, create a private repository with a dated suffix and keep the local remote explicit.

## Public Source Release Gate

Do not change visibility to public until `docs/COMPLIANCE.md` and `docs/PUBLIC_RELEASE_CHECKLIST.md` are complete and the maintainer has manually reviewed the GitHub file list.

The planned public source version is stored in `VERSION`. Public source release notes live in `docs/PUBLIC_SOURCE_RELEASE_NOTES.md`.

Run:

```bash
scripts/audit-public-release.sh --repo KK-invent/DeepCodeX --release-tag private-preview-YYYYMMDD-HHMMSS
scripts/verify-github-public-metadata.sh --repo KK-invent/DeepCodeX
```

This audit intentionally fails while the project still has unresolved public-release blockers, such as missing GitHub MIT license detection, DeepSeek-style brand assets without public approval, unreviewed upstream patching terms, or missing GitHub Actions CI.

If `--release-tag` points at a private preview release that still has `DeepCodeX-mac.zip` or checksum assets, the audit also fails unless `docs/UPSTREAM_TERMS_APPROVAL.md` explicitly says `public-binary-release: approved`.

Before switching repository visibility, complete `docs/UPSTREAM_TERMS_APPROVAL.md` from `docs/UPSTREAM_TERMS_APPROVAL_TEMPLATE.md`.

The approval file must pass:

```bash
scripts/verify-upstream-terms-approval.sh
```

If binary distribution is not approved, run the final public gate without a private preview binary release attached to the public repository:

```bash
scripts/audit-public-release.sh --repo KK-invent/DeepCodeX --require-public
```

If binary distribution is explicitly approved, the approval file must contain:

```text
public-binary-release: approved
```

To prepare the source-only public path without changing visibility, run:

```bash
scripts/verify-public-release-git-state.sh
scripts/prepare-public-source-release.sh \
  --repo KK-invent/DeepCodeX \
  --private-release-tag private-preview-YYYYMMDD-HHMMSS \
  --dry-run

scripts/publish-public-source-release.sh \
  --repo KK-invent/DeepCodeX \
  --private-release-tag private-preview-YYYYMMDD-HHMMSS \
  --dry-run \
  --skip-public-check
```

`--skip-public-check` is for dry-run planning only. The publish script refuses to create a real public source release while the repository is still private.

Do not omit `--private-release-tag` while a private preview release exists. If there has never been a private binary release, pass `--no-private-release-assets`; the script will scan GitHub releases and fail if any binary or checksum assets exist instead of silently skipping asset inspection.

The supplied private preview tag must already exist on GitHub. The preparation script treats a missing tag as a blocker instead of interpreting it as an empty release.

If the approval file says `public-binary-release: private-only`, remove private preview binary assets before switching visibility:

```bash
scripts/prepare-public-source-release.sh \
  --repo KK-invent/DeepCodeX \
  --private-release-tag private-preview-YYYYMMDD-HHMMSS \
  --delete-binary-assets \
  --hide-private-release
```

`--hide-private-release` marks the old private preview Release as a draft after its binary/checksum assets are removed. The preparation script does not make the repository public. After it passes, review the GitHub UI and then change visibility manually.

After the repository is public, create the source-only GitHub Release:

```bash
scripts/publish-public-source-release.sh \
  --repo KK-invent/DeepCodeX \
  --private-release-tag private-preview-YYYYMMDD-HHMMSS
scripts/verify-public-source-release.sh --repo KK-invent/DeepCodeX --tag v$(cat VERSION)
```

The public source release script refuses to upload binary assets. For real publishing, it also reruns the public-release audit and source-release preparation gate before creating or updating the `vX.Y.Z` GitHub Release using `docs/PUBLIC_SOURCE_RELEASE_NOTES.md`.

## Private Binary Assets

If a private binary package is needed, build it locally and upload it as a private release asset only after `scripts/audit-package.sh` passes.

Use `DeepCodeX-mac.zip` for the single ordinary-user package after the private runtime boundary is reviewed. The installer detects whether `/Applications/Codex.app` exists and points missing users to the official Codex page; do not publish separate "has Codex" and "no Codex" user-facing packages.

`DeepCodeX-mac-no-runtime.zip` is a maintainer-only package for machines that already have a compatible runtime.

Recommended private preview command:

```bash
scripts/publish-private-release.sh --include-runtime-bundled
```

If updating an existing `private-preview-*` release whose git tag points at an older commit, pass `--retarget-tag` after confirming that preview tag should move:

```bash
scripts/publish-private-release.sh --include-runtime-bundled --retarget-tag
```

The publish script refuses to upload assets unless the GitHub repository is private. It audits source, audits every zip package, verifies `.sha256`, makes the release tag match the release commit, then creates or updates a prerelease and uploads the selected assets.

The publish script also verifies the final release asset surface after upload. The ordinary-user release must expose exactly:

```text
DeepCodeX-mac.zip
DeepCodeX-mac.zip.sha256
```

To verify an existing release manually:

```bash
scripts/verify-release-assets.sh --tag private-preview-YYYYMMDD-HHMMSS --expected-target $(git rev-parse HEAD)
```

The verifier checks the release target commit and the matching remote git tag, retries transient GitHub API and checksum-asset download failures, and then fails the gate if the remote asset surface is not exactly the expected package set.

Before sharing a direct-use asset, run:

```bash
scripts/smoke-offline-package.sh dist/private/DeepCodeX-mac.zip
```

The smoke test unzips the package, simulates a machine with no Codex/DeepCodeX app, checks that the installer blocks on missing Codex with clear guidance, checks the bundled runtime, configures a temporary extracted app with a fake base URL/API key, and verifies the key is not printed.

Private preview binary assets must remain private. If the repository is changed to public, GitHub release assets attached to that repository become public too. Remove private preview zip assets first unless `docs/UPSTREAM_TERMS_APPROVAL.md` explicitly approves public binary release distribution.

## GitHub Actions Audit

The local audit script is intentionally committed as `scripts/audit-release.sh`. The GitHub Actions workflow is committed at `.github/workflows/audit.yml` and runs the same audit on pushes and pull requests targeting `main`.

If the workflow must be recreated from the template, refresh the GitHub token with `workflow` scope, then run:

```bash
gh auth refresh -h github.com -s workflow
scripts/enable-github-actions-audit.sh
```

Confirm the workflow is active and the latest run passed:

```bash
gh workflow list --repo KK-invent/DeepCodeX
gh run list --repo KK-invent/DeepCodeX --workflow Audit --limit 5
scripts/verify-github-actions-audit.sh --repo KK-invent/DeepCodeX --commit $(git rev-parse HEAD)
```
