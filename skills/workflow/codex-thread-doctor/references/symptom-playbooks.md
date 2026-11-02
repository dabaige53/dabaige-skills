# Symptom playbooks

Choose one primary branch. Add another only when its independent red signal is also present.

## Archived task remains visible or disappears when clicked

Red signal: the sidebar shows a task that the task API or main DB marks archived; clicking it refreshes the list or routes away.

1. Read the task and compare active and archived task lists. Preserve exact IDs supplied by the user as explicit visibility evidence; an unindexed Desktop hydration source may not appear in known global-state fields.
2. Check whether clicking generated a new archive request. If none exists and resume/read reports an already archived task, classify this as stale UI membership/order state rather than auto-archiving.
3. Compare `thread/list(archived=false)` under normal hydration with `useStateDbOnly=true`, then inspect `.codex-global-state.json`. Visibility-bearing fields include pinned IDs, sidebar project/thread order, `electron-remote-hosted-pip-task-visibility-state` entries marked `shown`, and `app-server-migrated-pinned-thread-ids-by-host`. Treat project assignments and other metadata as non-visibility data.
4. Reassert each confirmed or explicitly user-observed ghost with the official `thread/archive` operation, even when the DB flag and rollout directory already indicate archived. This emits the lifecycle event that direct SQLite or legacy-index edits bypass.
5. Verify every target is absent from normal and state-DB-only active lists and present in the archived list. When the bug reproduces only after restart, user confirmation after a full restart is the final red-signal check. Persisted legacy references can remain after a successful RPC and must be reported as residual risk, not automatically deleted.

## Task unexpectedly archived

Red signal: a previously active task has a new archive event or moves into the official archived list.

1. Find the exact log line `Archive requested` for the task ID and capture `source` and time.
2. Correlate the source with the action immediately before it. Common sources include recent-task menu actions, worktree deletion, handoff, and dynamic tool calls.
3. Distinguish an intentional source-triggered archive from a failed archive operation. Verify the final main-DB/API state instead of trusting a toast.
4. If the task should remain active, use the official unarchive operation. Change workflow behavior only when the source proves which action caused the archive.

## `list_turns is not supported yet`

Red signal: task restoration or `read_thread` fails with this exact error after a history-mode change or app update.

1. Check the task's `history_mode`, current app version, and whether the same call works for a known paginated task.
2. Inspect recent repairs or migrations. A blanket switch from paginated to legacy can make a newer client call an unsupported legacy path.
3. Restore only modes proven incorrect from a trusted pre-change snapshot or current-version contract. Do not infer that legacy is safer merely because the rollout file is complete.
4. Verify both task listing and actual turn retrieval after correction.

## History loads slowly or ends early

Red signals: time the same task operation twice; identify the last visible item/turn; compare it with the latest valid event in the rollout.

1. Determine scope. One large task suggests rollout/projection work; all tasks suggests app version, provider/network, storage contention, or global migration.
2. Compare rollout size, valid line/event count, latest ordinal, projection ordinal/offset, and projected item/turn counts.
3. Search near the projection stop for an unfinished `inProgress` turn, malformed line, duplicate ordinal, or schema/version boundary. Later valid rollout events prove that the raw history continued; they do not prove the projection consumed it.
4. Run any official migration in dry-run/read-only mode first. `already_paginated` only identifies mode; it does not prove the projection is current.
5. Keep provider/network diagnosis separate: compare a new small task with the affected task and inspect request timing. Provider configuration changes require their own evidence and authorization.

## Task missing from active and archived lists

1. Query the exact task ID in the main DB and both task APIs.
2. Resolve the recorded rollout path and search active/archived session trees for an exact ID match.
3. Classify one of: wrong directory with valid file; stale DB path with exact file elsewhere; DB metadata with missing rollout; rollout without DB record; projection-only residue; UI/list filtering.
4. Preserve true orphans and projection-only rows during diagnosis. They may be the only remaining recovery evidence.

## Estate-wide audit

Use counts only to find candidate sets: active/archived, history modes, missing rollout paths, projection gaps, unfinished turns, duplicate ordinals, UI references to archived IDs, index parse failures/duplicates, and DB quick/integrity checks. For archived ghosts, `scripts/audit_archived_ghosts.py` separates confirmed visibility conflicts, legacy-index risks, and archived user-level delegation tasks that may survive only in an unexposed Desktop hydration layer. Add user-observed rows with `--thread-id`; other task types may also be absent from every exposed persisted field. For user-authorized estate-wide recovery, send the resulting explicit ID union through official archive operations in bounded batches and record failures. Every proposed mutation must still reduce to explicit task IDs and one classified defect; aggregate counts alone never authorize a rewrite.
