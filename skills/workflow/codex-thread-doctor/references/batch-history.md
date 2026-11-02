# Batch history audit and repair

## Audit

Use this sequence rather than restarting discovery for each task:

1. Freeze scope: exact supplied IDs, otherwise unarchived user tasks. Reuse the existing API snapshot when available.
2. Run `audit_history.py` once for metadata and storage candidates. Explicit `--thread-id` narrows the scope; it does not add to all tasks. Archived tasks and subagents remain excluded unless their include flags were requested.
3. Fully paginate candidates and user-observed failures. Do not fully read every healthy task merely because it exists. If the user requests exhaustive history verification, paginate the entire requested scope and state its cost; an inventory alone is not exhaustive verification.
4. Resolve empty items with the full-items API before copying databases or researching repairs. Resolve missing-source errors by exact ID in the session trees and known recovery directories, including `$HOME/.codex-recovery`; search broader locations only if these fail. Report an inaccessible location separately from a missing file.
5. Classify once, repair the proven set, and verify once. Preserve snapshots and a pending plan across app restarts rather than repeating the audit.

Use `scripts/audit_history.py --help` for a read-only inventory and classified candidates. Defaults exclude archived tasks and subagents. Use repeatable `--thread-id` for exact targets, and `--api-snapshot` for fully paginated task API evidence. Store reports outside Codex's live state directory.

The recent-task tool is bounded (currently list limit 50 and read limit 10). Follow history cursors to exhaustion; use main-DB scope discovery to reach older tasks. Do not describe a recent-page sample as an estate-wide history check. Record inventory coverage separately from API coverage and raw-record inspection.

An API snapshot must identify each task and contain `turns` with `id`, `status`, and `items` count; preserve `page.hasMore` and any error. Partial or failed reads cannot establish absent turns. Use raw `task_started` IDs and associated text-bearing messages to find entire missing turns. Inspect completed-item events when a format does not use response messages. Count failed/interrupted empty turns separately.

For empty `read_thread` items, verify the current app-server contract: `thread/turns/list` can intentionally omit items (`itemsView: notLoaded`) or return a summary. Confirm with `itemsView: full` or `thread/items/list`, preferably from a fresh server using an isolated snapshot. If persisted full items are readable, classify the discrepancy as loaded-state/summary hydration; do not rewrite durable history merely to fix an empty summary.

Projection offset mismatch is a candidate signal, not a defect by itself. `history_base` can reference earlier segments, and inherited turns need not be stored under the current task ID. Resolve lineage before concluding data loss. Detect duplicate/gapped ordinals and malformed JSON without discarding records. A missing source path requires an exact-copy search, not synthetic history.

## Authorized batch repair

1. Record exact IDs, archive state, original red signals and expected missing turn/item IDs. Group by proven cause: stale hydration, duplicated ordinal, projection defect, or missing lineage source.
2. Check the installed runtime's official repair surface. `migrate-rollouts` converts legacy history; `already_paginated` is not repair. Do not downgrade all histories or use `thread/inject_items` to manufacture replacement conversations.
3. Prefer an official operation when it expresses the intended repair. For file-level recovery, reproduce the failure and validate the smallest edit on an isolated copy. Ensure copied metadata cannot direct the test process back to live rollouts; disable background migrations in the test configuration. Do not start a model turn or execute project hooks as part of a history read.
   Reuse a validated repair mechanism for matching defects in this batch, while checking every target's payload preservation and expected history. Copy only the state and source segments needed by the selected targets; do not copy the whole Codex home, credentials, or unrelated rollouts. Use the existing `apply_history_plan.py` for a compatible prepared plan rather than writing another executor. A mechanism mismatch requires targeted investigation, not a new general-purpose repair system.
4. An ordinal edit must preserve every record's payload and order. Detect dependent lineage cutoffs before changing ordinals or byte offsets. Compare all payloads before/after and require full history retrieval, including missing IDs. Do not remove stalled projection rows unless an actual rebuild has succeeded on the isolated copy.
5. Before live file edits, use the offline gate in [state-and-repair.md](state-and-repair.md): app fully quit, fresh backup, exact targets, rollback. Previously granted repair authorization persists; ask only for any still-missing authorization or operational condition. Do not leave an unvalidated background writer waiting for app exit.
6. Process the validated target set in bounded batches. Record attempted, repaired, failed, skipped-archived and pending counts. Stop on a systemic failure. A missing source on one target need not block independently validated repairs on others.
7. Verify expected turn IDs and full items through the current app API, metadata/archive state, payload preservation, SQLite integrity, and unrelated-state preservation. A successful command is not completion. After restart, compare the user's original visible symptom. Retain backups and report unresolved targets explicitly.

“One request” means continuous execution under one authorization, with an auditable target set and verification.
