---
name: codex-thread-doctor
description: "Audit and repair Codex task history and sidebar anomalies, individually or in batches: missing history, restore failures, stale archived rows, and missing tasks. Use for thread state problems, not general model latency or unrelated app configuration."
---

# Codex Thread Doctor

Diagnose the smallest failing state transition before proposing repair. Treat the rendered sidebar as a cache, not the source of truth.

## Fast execution

- Keep incident repair separate from skill development. During an incident, reuse the bundled scripts; do not build a general recovery framework, refactor tools, or expand tests unless a demonstrated defect blocks this repair. When asked to optimize this skill, edit it without reopening an unrelated incident.
- Read only the reference for the reported symptom. For missing history, use the batch-history branch; do not inspect archive caches, legacy sidebar indexes, or archived tasks unless evidence requires them.
- Reuse this run's version, schema, target list and verification results. Refresh only evidence invalidated by new writes, a runtime change, or a failed check. Check current official behavior once per relevant runtime/mechanism, not once per task.
- Start with inexpensive scope inventory, then inspect candidate histories. Run bounded independent reads together and retain only IDs, counts, cursors and errors needed for comparison. Do not dump full conversations or database schemas into the model context.
- Stop diagnosis for a target when its cause and validated repair are sufficient. Continue to repair under existing authorization; further research needs a concrete unresolved question. A successful verification is a stopping condition, not a prompt for broader testing.
- If offline execution is required, prepare and validate one exact-target batch, then give one concise exit/run instruction. Do not spend additional time redesigning recovery after the batch is ready. Preserve the backup, payload and scope checks required for that batch.

## Scope and execution mode

- A report of a problem authorizes diagnosis. An explicit request to fix it authorizes continuing from audit through scoped repair and verification; do not stop at an audit report or ask again for the same authorized action.
- For multiple tasks or a request to check everything, use [batch history audit and repair](references/batch-history.md). Audit all tasks in the requested scope, not just the most recent sidebar page. Default history repair to unarchived user tasks; include archived tasks or subagents only when requested.
- Freeze the proven target IDs before writing. Recheck archive state immediately before each repair and exclude newly archived targets. A batch is not permission to reset every projection or rewrite every rollout.
- Complete preparation and isolated verification before an offline handoff. If app shutdown or access to a protected recovery location requires the user, ask once for that concrete missing condition and preserve the pending batch for continuation.

## Workflow

1. Define one **red signal** that reproduces the report: an exact task ID, error, missing turn, unexpected archive event, stale sidebar row, or measured load delay. Record the Codex app/CLI version and whether the symptom affects one task or all tasks. The step is complete when the failure is observable and bounded.
2. Inspect task APIs before local storage. For task references, call `read_thread`; compare `list_threads` and `list_archived_threads` when visibility or archive state is involved. A user-supplied exact ID or task reference that is visibly stale remains a first-class candidate even when automatic sidebar-field discovery cannot reproduce it. Do not infer task contents from its title or sidebar row.
3. Choose the matching branch in [references/symptom-playbooks.md](references/symptom-playbooks.md). If local state is involved, read [references/state-and-repair.md](references/state-and-repair.md) before querying or changing it.
4. Reconcile evidence in this order: current task API and main state DB; referenced rollout file; paginated history projection; logs; UI membership/order caches; legacy indexes and backups. Explain any conflict rather than averaging it away.
5. Report the diagnosis and classified candidates before mutation. Prefer an official task operation when it can express the intended state change. For archived sidebar ghosts, reassert archive state through `thread/archive` even when SQLite already says `archived=1`; the RPC also drives the canonical lifecycle event used by clients. Local file repair requires the user to have asked for a fix, a full app quit, a fresh backup, an exact target set, and a rollback path.
6. Re-run the original red signal and the relevant integrity checks. For archive repairs, compare both normal `thread/list` hydration and `useStateDbOnly=true`: every target must be absent from `archived=false` and present in `archived=true`. Ask for a full restart check when resurrection was the red signal. Completion requires canonical state and the restarted sidebar to agree; legacy references may remain as risk evidence without making the repair a failure.

## Operating boundaries

- Start read-only. Diagnosis does not authorize repair.
- Keep current-version behavior authoritative. Verify version-sensitive migration or history-mode behavior with official OpenAI documentation or the current `openai/codex` issue/PR before acting.
- Scope repairs to proven candidates. Preserve unrelated tasks, rollout files, projection rows, writer locks, metadata, and project assignments.
- Estate-wide archive repair means batch-processing the classified conflict set, never replaying archive across every archived task. Use `scripts/audit_archived_ghosts.py` to produce candidates from current list hydration, the main DB, known sidebar membership/order fields, and user-supplied exact IDs via `--thread-id`.
- Archive-state mutation must use official Codex task operations. Treat SQLite, global-state, rollout, and legacy-index edits as offline recovery only after official operations demonstrably fail and the user explicitly authorizes file-level repair.
- When the user explicitly requests estate-wide cleanup after multiple confirmed ghosts, reassert archive for the classified union in bounded batches through the official operation. Record processed, succeeded, and failed counts; stop on systemic failures rather than falling back to file edits. Do not include every archived task merely because it exists.
- Report discovery coverage explicitly. Automatic discovery covers normal/state-DB hydration, sidebar membership/order, remote-hosted visibility, migrated pins, the legacy session index, and archived user-level delegation tasks. Desktop can retain other rows in an unexposed in-memory hydration source; those require an exact user-observed ID and must not be hidden behind a claim of completeness.
- Treat a missing rollout as data loss until an exact matching copy is found. Preserve the DB metadata and report the recovery boundary; never manufacture an empty or synthetic history.
- Keep secrets out of commands and reports. Thread diagnosis ordinarily does not require changing model-provider configuration.

## Deliverable

Lead with repaired / pending / excluded counts, the cause, and any required user action. Include only material verification and backup/rollback details. Write a separate report only when requested or needed for offline continuation; avoid a full forensic report for every incident. If no mutation was requested, stop after the evidence-backed diagnosis and repair plan.
