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

## Optional GitHub Actions

The local audit script is intentionally committed as `scripts/audit-release.sh`. A GitHub Actions workflow can be added later, but pushing workflow files requires a GitHub token with the `workflow` scope. Keep CI out of the initial private push unless that scope is available.
