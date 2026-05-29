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

Do not change visibility to public until `docs/COMPLIANCE.md` is complete and the maintainer has manually reviewed the GitHub file list.

## Private Binary Assets

If a private binary package is needed, build it locally and upload it as a private release asset only after `scripts/audit-package.sh` passes.

Use `runtime-bundled` for the single ordinary-user package after the private runtime boundary is reviewed. The installer detects whether `/Applications/Codex.app` exists and points missing users to the official Codex page; do not publish separate "has Codex" and "no Codex" user-facing packages.

`runtime-external` is a maintainer-only package for machines that already have a compatible runtime.

Recommended private preview command:

```bash
scripts/publish-private-release.sh --include-runtime-bundled
```

The publish script refuses to upload assets unless the GitHub repository is private. It audits source, audits every zip package, verifies `.sha256`, then creates or updates a prerelease and uploads the selected assets.

Before sharing a direct-use asset, run:

```bash
scripts/smoke-offline-package.sh dist/private/DeepCodeX-private-runtime-bundled-*.zip
```

The smoke test unzips the package, simulates a machine with no Codex/DeepCodeX app, checks that the installer blocks on missing Codex with clear guidance, checks the bundled runtime, configures a temporary extracted app with a fake base URL/API key, and verifies the key is not printed.

## Optional GitHub Actions

The local audit script is intentionally committed as `scripts/audit-release.sh`. A GitHub Actions workflow can be added later, but pushing workflow files requires a GitHub token with the `workflow` scope. Keep CI out of the initial private push unless that scope is available.
