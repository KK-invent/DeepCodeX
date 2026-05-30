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
git status --short
git ls-files
```

## Private Repository Command

```bash
gh repo create DeepCodeX --private --source=. --remote=origin --push
```

If the name already exists, create a private repository with a dated suffix and keep the local remote explicit.

## Public Release Gate

Do not change visibility to public until `docs/COMPLIANCE.md` and `docs/PUBLIC_RELEASE_CHECKLIST.md` are complete and the maintainer has manually reviewed the GitHub file list.

Run:

```bash
scripts/audit-public-release.sh --repo KK-invent/DeepCodeX --release-tag private-preview-YYYYMMDD-HHMMSS
```

This audit intentionally fails while the project still has unresolved public-release blockers, such as the private-preview license notice, DeepSeek-style brand assets without public approval, unreviewed upstream patching terms, or missing GitHub Actions CI.

## Private Binary Assets

If a private binary package is needed, build it locally and upload it as a private release asset only after `scripts/audit-package.sh` passes.

Use `DeepCodeX-mac.zip` for the single ordinary-user package after the private runtime boundary is reviewed. The installer detects whether `/Applications/Codex.app` exists and points missing users to the official Codex page; do not publish separate "has Codex" and "no Codex" user-facing packages.

`DeepCodeX-mac-no-runtime.zip` is a maintainer-only package for machines that already have a compatible runtime.

Recommended private preview command:

```bash
scripts/publish-private-release.sh --include-runtime-bundled
```

The publish script refuses to upload assets unless the GitHub repository is private. It audits source, audits every zip package, verifies `.sha256`, then creates or updates a prerelease and uploads the selected assets.

The publish script also verifies the final release asset surface after upload. The ordinary-user release must expose exactly:

```text
DeepCodeX-mac.zip
DeepCodeX-mac.zip.sha256
```

To verify an existing release manually:

```bash
scripts/verify-release-assets.sh --tag private-preview-YYYYMMDD-HHMMSS
```

Before sharing a direct-use asset, run:

```bash
scripts/smoke-offline-package.sh dist/private/DeepCodeX-mac.zip
```

The smoke test unzips the package, simulates a machine with no Codex/DeepCodeX app, checks that the installer blocks on missing Codex with clear guidance, checks the bundled runtime, configures a temporary extracted app with a fake base URL/API key, and verifies the key is not printed.

## Optional GitHub Actions

The local audit script is intentionally committed as `scripts/audit-release.sh`. A GitHub Actions workflow should be enabled before public release, but pushing workflow files requires a GitHub token with the `workflow` scope.

Until that scope is available, keep the template at `docs/GITHUB_ACTIONS_AUDIT_TEMPLATE.yml`. When ready, copy it to `.github/workflows/audit.yml`, commit it, and confirm GitHub Actions runs on `main`.
