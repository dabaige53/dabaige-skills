---
name: no-comments
description: "Remove unnecessary comments, identify the code problems they hide, and preserve required contracts and directives. Use for an explicit comment-cleanup request on selected files or a diff."
disable-model-invocation: true
---

# No comments

Use the adapted Comment Sicko rules in [references/comment-review.md](references/comment-review.md). Keep an independent review when it adds value; no dedicated Cursor agent is required.

## Scope

Use the caller's files or diff. Otherwise use the current diff against the base branch, default `main`, including the working tree.

Comment cleanup authorizes comment edits within that scope. Fix application code only when the task also authorizes the fix. Preserve project-required metadata, including `@wu-test` annotations.

## Steps

1. Read the review rules. For a small scope, apply them directly. When an independent pass is useful, delegate a read-only review to an available local agent (Codex: `default`) under the current delegation rules. Pass the exact files or diff and the review reference. Require proposed comment deletions, protected keeps, and exact `MUST KILL` symbols; the reviewer does not edit application code. Use configured role models, not model names from another client.
2. Inspect the report and proposed diff. Reject application-code edits, scope escapes, protected deletions, unsupported `MUST KILL` reasons, and flags that treat intentional code as faulty without evidence. Audit missed lint and TypeScript suppressions. Correctness or safety suppressions stay actionable. Before accepting thin `IMPORTANT` or `do not remove` reasons, trace the symbol or use the installed `why` skill. Required tool directives and documented exceptions survive. If a report fails these rules, request one corrected pass naming the failure. If that pass also fails, leave its disputed changes unapplied and report the open work.
3. Fix trivial accepted flags within the task's authorized code scope by deleting a dead path, dropping a parameter, or using the real API. If a fix needs a structural decision, first sketch the smallest change to the surrounding code, its responsibilities and interfaces. No separate `architect` skill is required. If only comment edits are authorized, list those code fixes instead.
4. Implement the smallest authorized root-cause fix. Remove its workaround rather than adding symptom guards. If the root cause is out of scope, report it and make only an independently useful in-scope fix. Do not widen the task to repair similar code elsewhere. Follow the project's test rules and the user's execution limits.
5. Constraint comments say `do not remove`, `do not change wording`, or `talk to X before changing`. Preserve proven external constraints and required metadata. For an internal constraint, propose the cheapest in-scope type, runtime check, test or lint rule that can enforce it. Apply it when already authorized; otherwise keep the constraint until the decision is made and list the needed action. Once enforced and no exception applies, delete the redundant comment.
6. Report deletion count, protected keeps, any corrected review, structural changes, fixes and remaining constraints. Omit empty categories.
