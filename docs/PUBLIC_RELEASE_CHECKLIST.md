# Public Release Checklist

This checklist is for changing DeepCodeX from private preview to a public GitHub project.

Do not make the repository public until every blocker here has a clear owner and evidence.

## Hard Blockers

- Choose the public license posture:
  - Replace `LICENSE.md` with a real public license, or
  - Keep a source-available private notice and state that reuse rights are not granted.
- Decide the DeepSeek visual-asset posture:
  - Keep official/derived DeepSeek-style assets only with explicit approval for public visibility, or
  - Replace `deepseek-app-icon.png`, `deepseek-official-favicon.svg`, `deepcodex-hero.png`, `deepcodex-icon.svg`, and both `deepcodex-logo*.svg` files with original DeepCodeX artwork.
- Review the upstream Codex patching model against applicable app terms before presenting the project as public.
- Enable GitHub Actions audit CI by copying `docs/GITHUB_ACTIONS_AUDIT_TEMPLATE.yml` to `.github/workflows/audit.yml` with a GitHub token that has `workflow` scope.

## Required Commands

Run the normal source gate:

```bash
scripts/audit-release.sh
```

Run the public-release gate:

```bash
scripts/audit-public-release.sh --repo KK-invent/DeepCodeX --release-tag private-preview-YYYYMMDD-HHMMSS
```

After resolving the blockers and switching visibility to public, run:

```bash
scripts/audit-public-release.sh --repo KK-invent/DeepCodeX --require-public
```

Before the visibility switch, run the same command without `--require-public`; it should pass after all decision blockers are resolved.

## GitHub Metadata

- Description is set.
- Homepage points to the README.
- Topics include `ai`, `codex`, `deepseek`, `developer-tools`, and `macos`.
- The rendered English README and Chinese README both show the non-affiliation boundary.
- The Chinese README uses only Chinese-localized diagrams.

## Release Asset Rules

The ordinary-user release should expose exactly:

```text
DeepCodeX-mac.zip
DeepCodeX-mac.zip.sha256
```

Do not publish maintainer-only or runtime-variant packages as default public downloads.
