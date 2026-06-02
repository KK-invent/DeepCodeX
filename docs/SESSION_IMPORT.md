# Continuing Codex projects in DeepCodeX

DeepCodeX runs with an **isolated** home (`~/.codex-deepseek`) so it never
pollutes a normal Codex install. The trade-off: DeepCodeX can't see the
conversations created by the regular Codex app, which live under `~/.codex`. So
a project you started in Codex doesn't show up in DeepCodeX's resume/history
picker out of the box.

`bin/deepcodex-session-import.py` bridges the two by mirroring the regular Codex
session rollouts, archived conversations, shell snapshots, session index, and
desktop thread database into the DeepCodeX home. Optionally, it also merges the
cross-session `history.jsonl`.

It is deliberately **non-invasive**: it only writes inside the DeepCodeX home
data directory. It never touches the app bundle, `app.asar`, the DeepSeek
bridge, the image shim, the request chain, or the regular Codex home.

## What it does

- Mirrors `<source>/sessions/`, `<source>/archived_sessions/`, and
  `<source>/shell_snapshots/` into the matching target directories without
  overwriting newer DeepCodeX-side files.
- Merges `session_index.jsonl`, keeping the newest record for each thread ID.
- Merges `state_5.sqlite` thread rows so the DeepCodeX UI can actually see the
  imported conversations in its history/resume picker.
- Rewrites imported thread rows to DeepCodeX's `ccx-deepseek` model provider so
  the DeepCodeX sidebar includes them and resumed turns continue through
  DeepSeek instead of being filtered as upstream OpenAI-provider threads.
- Merges `.codex-global-state.json` sidebar state so the Codex project and
  projectless conversation lists appear in DeepCodeX's left sidebar. Codex
  entries keep their Codex order, and DeepCodeX-only chats/projects are kept
  after them.
- Marks imported Codex projectless chats as projectless in the DeepCodeX sidebar
  state (`thread-workspace-root-hints` = `~`) so they stay in the left sidebar
  "Chats" section instead of being swallowed by project/root grouping.
- Converts legacy terminal Codex (`source=cli`) rollouts into a
  desktop-compatible view before exposing them in the DeepCodeX UI. The message
  and tool history is preserved, while the `codex-tui` metadata and old
  permission profile wrapper are normalized so the desktop thread reader can
  open the conversation.
- Records imported sessions in a sidecar manifest
  (`<target>/.deepcodex-import-manifest.json`) for fast, idempotent re-runs.
- With `--include-history`, merges `history.jsonl` entries that are not already
  present (dedup by `session_id` + `ts` + `text`), backing up the target
  history first.

## One-off import

After installing (`scripts/install-local.sh`), the tool lives at
`~/.codex-deepseek/bin/deepcodex-session-import.py`:

```bash
# Preview — writes nothing
~/.codex-deepseek/bin/deepcodex-session-import.py --dry-run --include-history

# Import conversations only
~/.codex-deepseek/bin/deepcodex-session-import.py

# Import conversations AND merge cross-session history
~/.codex-deepseek/bin/deepcodex-session-import.py --include-history
```

Restart DeepCodeX (or reopen the history picker) afterwards to see the imported
conversations in the left sidebar.

### Options

| Flag | Default | Meaning |
| --- | --- | --- |
| `--source` | `$CODEX_SOURCE_HOME` or `~/.codex` | Regular Codex home to read from (read-only). |
| `--target` | `$DEEPCODEX_HOME` or `~/.codex-deepseek` | DeepCodeX home to write into. |
| `--include-history` | off | Also merge `history.jsonl` (backed up first). |
| `--dry-run` | off | Report what would happen; write nothing. |
| `--verbose` / `-v` | off | Print each session as it is considered. |

## Automatic sync

`scripts/install-local.sh` installs a launchd agent
(`com.deepcodex.session-sync`) that keeps DeepCodeX continuously in sync with
the regular Codex app. It runs the importer:

- **on change** — `WatchPaths` fires whenever Codex sessions, archives, shell
  snapshots, the session index, or the thread database change, and
- **on a fallback interval** — every 15 minutes (`StartInterval`).

Logs go to `~/.codex-deepseek/logs/session-sync.out.log` and `session-sync.err.log`.

Override the source home at install time with `CODEX_SOURCE_HOME`:

```bash
CODEX_SOURCE_HOME="$HOME/.codex" scripts/install-local.sh
```

Uninstall just the sync agent:

```bash
launchctl bootout gui/$(id -u)/com.deepcodex.session-sync
rm ~/Library/LaunchAgents/com.deepcodex.session-sync.plist
```

## Safety notes

- The source home is opened **read-only**; the regular Codex install is never
  modified.
- History merges are deduplicated and the target `history.jsonl` is backed up
  to `history.jsonl.bak.before-import-<timestamp>` before each write.
- Thread database merges are idempotent and the target `state_5.sqlite` is
  backed up to `state_5.sqlite.bak.before-import-<timestamp>` before changed
  rows are written.
- Sidebar state merges are additive: Codex sidebar entries are inserted first,
  and DeepCodeX-native conversations/projects remain in place after them.
- Legacy CLI rollout conversion writes only to the DeepCodeX target home. The
  regular Codex source home remains untouched and read-only.
- Imported sessions keep their original UUIDs, so they never collide with
  DeepCodeX-native sessions.
