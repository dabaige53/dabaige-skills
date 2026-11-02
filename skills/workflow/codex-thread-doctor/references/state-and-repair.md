# State model and repair gates

## Evidence layers

Resolve the effective Codex home first (`$CODEX_HOME` when explicitly set, otherwise `~/.codex`). Discover current filenames and schemas before querying; names below reflect known macOS desktop layouts and may change.

| Layer | Typical location | What it can prove |
|---|---|---|
| Task API | `read_thread`, active/archived list tools | Current app-visible status and readable turns |
| Main state | `state_5.sqlite` | Task metadata, archive flag, rollout path, history mode |
| Raw history | `sessions/**/rollout-*.jsonl`, `archived_sessions/**` | Durable event stream and latest valid raw history |
| Projection | `thread_history_1.sqlite` | Materialized paginated turns/items and projection progress |
| Logs | app/Codex logs | Archive source, migrations, resume/read failures, timings |
| UI state | `.codex-global-state.json` | Sidebar membership/order, pinning, remote-hosted visibility, migrated pin state, project display state |
| Legacy/recovery | `session_index.jsonl`, old DBs, backups | Legacy list candidates and recovery evidence, not current truth by default |

Use the main DB plus exact rollout file as the storage baseline. UI state is weaker evidence. Old indexes and backups are historical evidence unless the current data is missing.

## Read-only audit

1. Copy or open SQLite databases read-only. Inspect `sqlite_master` and `PRAGMA table_info(...)` before relying on remembered columns.
2. Run `PRAGMA quick_check` or `integrity_check`; record WAL presence and active writer locks without removing them.
3. For each candidate task, record ID, title, archive flag, history mode, DB rollout path, file existence/location/size, projection progress, API visibility, and UI references.
4. Parse JSON/JSONL defensively. Count malformed and duplicate legacy-index records, but keep them outside the repair set unless they reproduce the red signal.
5. Search logs by exact task ID and bounded time. Broad error counts are supporting context, not a cause.

## Classification and preferred repair

| Confirmed defect | Preferred action |
|---|---|
| Official state is correct; archived ID remains or resurrects in the sidebar | Reassert the exact ID through official `thread/archive`; verify normal and state-DB-only membership, then restart. Consider cache surgery only if the restarted UI remains red and the user explicitly authorizes it |
| Multiple confirmed ghosts or legacy-index risks after the same resurrection bug | With explicit estate-wide authorization, batch the classified ID union through official archive operations; record success/failure counts and verify a restarted sidebar |
| Archived task's valid rollout remains in active directory | Prefer official `unarchive → archive`, then verify DB path and file location |
| DB rollout path is stale; exact same-ID rollout exists elsewhere | Offline backup, update only the exact row/path using the discovered schema, then integrity and API checks |
| Rollout is absent everywhere | Preserve metadata; search trusted backups by exact ID/hash; report unrecoverable history if none exists |
| Paginated projection lags valid rollout | Use a current-version supported rebuild/migration if available; otherwise isolate the exact projection defect and design a reversible, per-task repair |
| Incorrect history mode from an earlier bulk repair | Restore per-task mode from trusted baseline/current contract; verify turn retrieval, not just the flag |
| True orphan rollout or projection-only row | Preserve or quarantine only after recovery analysis; deletion is not diagnosis |

## Offline gate

Before SQLite or global-state mutation:

1. Confirm the user requested repair and list exact task IDs/fields/files.
2. Quit the Codex/ChatGPT app with Cmd+Q and verify real app processes are gone. Crashpad helper processes may remain and must not alone block repair.
3. Create a timestamped backup outside the live tree. Use SQLite's backup API or a transactionally safe copy including WAL/SHM as applicable; copy JSON before atomic replacement.
4. Capture pre-change counts and integrity results. Define a rollback command/path before writing.
5. Apply the smallest mutation in a transaction or atomic file replacement. Preserve permissions.
6. Re-run integrity checks before reopening the app.

Bulk deletion of Codex home, Application Support, rollouts, writer locks, session indexes, or projection tables is outside this workflow. A broad cache clear is acceptable only after identifying the exact disposable cache and proving it contains no authoritative history.

## Verification matrix

- Original red signal is green: exact error absent, expected last turn visible, archived ghost absent, or load timing materially improved.
- `read_thread` succeeds for affected tasks and one unaffected control task.
- Active and archived lists contain each affected ID exactly where intended.
- Main DB flags, rollout paths, file locations, and history modes agree.
- Restarted UI contains no archived ghost. Persisted visibility/index references are reported separately; they do not fail verification when canonical lists and the user-visible red signal are green.
- SQLite quick/integrity checks pass and no unrelated task counts changed.
- Backup and rollback remain available until the user accepts the result.
