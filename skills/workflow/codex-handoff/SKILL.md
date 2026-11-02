---
name: codex-handoff
description: 交接当前工作到新 Codex 任务。
---

# Codex Handoff

Transfer enough verified context for a new user-owned Codex task to continue the current work. Explicit invocation authorizes task creation; a prompt-only request authorizes only the summary. Preserve the existing explicit-only invocation policy.

## Prepare the handoff

Read the latest user corrections and actual work state. Summarize:

- The current objective, scope and completion criteria.
- Decisions, changes and verification already completed; distinguish drafts, running checks and unverified claims.
- Source files, commits, issues, URLs and artifacts needed to continue, using absolute file paths and existing documents instead of copying them.
- The next concrete action, blockers and relevant permissions or restrictions.

Carry unresolved work forward. Preserve the identity of the current project and note any uncommitted changes or artifacts the destination must access. Include only necessary context; omit credentials and unrelated personal data. Keep necessary authorized private source links usable.

## Create the destination

Use the currently available Codex task-management tools and their actual schemas.

1. When work belongs to a saved project, call `list_projects` and resolve that project. Default to `local`. Choose `worktree` only when the user explicitly requests it and `isGitRepository` is true. Set `startingState` only for a git state the user explicitly requested. If required uncommitted work would be unavailable, resolve that transfer before dispatch.
2. Use `projectless` when the work has no associated saved project. Use a cloud task only when explicitly requested.
3. Call `create_thread` with a descriptive title and the handoff summary as its prompt. Omit model overrides unless the user requested one. Carry the user's actual delegation restrictions and relevant project guidance; let the destination use its current delegation rules rather than adding new permission requirements.

The destination is a new task seeded with distilled context. A subagent or a full-history fork does not satisfy this handoff request.

## Complete the handoff

Use the returned creation status. If setup is pending, report it as pending and use `clientThreadId` only with the created-thread directive; tools requiring `threadId` must wait for the real ID. Once ready, report the returned `threadId` with `::created-thread{threadId="..."}`; for pending setup use `::created-thread{clientThreadId="..."}`. Replace placeholders with returned values.

In prompt-only mode, return the complete summary. If creation fails or is uncertain, check the result before retrying to avoid duplicate tasks; provide the prepared summary and the remaining blocker.
