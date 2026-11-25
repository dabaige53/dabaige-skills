---
disable-model-invocation: true
name: value-cleaner
description: Use when users want to remove low-value logic, redundant checks, filler, or meaningless content from code, tests, rules, or docs.
argument-hint: "<code|test|rule|docs> [paths]"
---

# Value Cleaner

Remove content that serves no actual behavior, decision, or action. Respond in the user's language.

Judge every candidate with one question:

> What actual behavior, decision, or action does this content serve, and is that role unique?

No concrete answer: remove it. A real role already served elsewhere: keep the clearest copy. Ordinary scan signals locate candidates for this judgment; apply the explicit removal rules below directly.

## Commands

The first word after the skill name selects the object; the rest are paths or instructions. Read only that object's file.

| Command | Cleans | Criteria | Scan |
| --- | --- | --- | --- |
| `value-cleaner code` | production code | `references/code.md` | `scripts/scan.py code <paths>` |
| `value-cleaner test` | tests, fixtures, snapshots, test docs | `references/test.md` | `scripts/scan.py test <paths>` |
| `value-cleaner rule` | agent instructions, skill files, policies, style guides | `references/rule.md` | `scripts/scan.py rule <paths>` |
| `value-cleaner docs` | READMEs, guides, plans, reports | `references/docs.md` | `scripts/scan.py docs <paths>` |

Without an object, infer it from the request and paths; when the request spans several, handle one object at a time. Without paths, use the files the conversation is working on; if there are none, ask which path to clean.

For a large test suite, `scripts/classify.py <paths>` ranks test functions by cleanup value: TypeSafe answers atomic yes/no judgments about each test, and a decision table in the script combines them with scan signals into `DELETE`, `MERGE`, `REWRITE`, `INVESTIGATE`, or `KEEP`. It sends test source to api.typesafe.ai with `TYPESAFE_API_KEY`, so run `--dry-run` first, tell the user how many tests and which files will be sent, and get their approval. Treat its rows as candidates for step 3; `--json FILE` keeps each answer and exact request for rerunning.

A command cleans by default. When the user asks only for a review, report findings as `Action | Location | Evidence`, highest value and lowest risk first, without editing. When the user asks for reusable cleanup rules, write rules instead.

## Clean up

1. Check repository status and preserve unrelated changes. Before editing, state the cleanup scope: whole repository, specified paths, or this task's changes. For task changes, identify the relevant diff or commits; do not treat every dirty file as part of the task. Follow explicit scope already given; otherwise use the current task's files, and ask only when no scope can be identified. List the concrete behavior, interfaces, and content that must remain, based on the request and project rules.
2. Run the scan on the target paths. It lists candidates as `path:line  text` under each signal and never edits files. `--signal NAME` limits the output to one signal; `--root DIR` sets where references are counted, by default the repository root.
3. Read each candidate and what decides its role: callers, the boundary that validates input, rules covering the same point, the reader's task. Judge it with the object's file. Content the scan misses still counts.
4. Remove confirmed low-value content directly. Do not replace it with a new rule, a removal note, a placeholder section, or a disclaimer. Before deleting text, move any unique command, reason, or condition to its canonical location.
5. Follow the deletion granularity the user asks for. Otherwise remove the whole unit that exists only for the removed purpose (sentence, paragraph, branch, or test) instead of rewording it to do the same job.
6. Re-read the result and fix what referenced the removed content. Clean the same pattern wherever it recurs in scope.
7. Run the smallest check that covers the change with the project's own commands: affected tests, type check, or lint for code and tests; `scan.py rule` or `scan.py docs` on the edited files with `--signal broken-link --signal missing-path` for Markdown. Do not install dependencies or weaken assertions to make it pass. Once it passes, stop.

## Text patterns

These recur in rules, docs, test docs, and comments. Remove the sentence or paragraph that exists only for one of them; do not substitute a softer version.

- **Unrequested proof** [denial]: demands evidence for a claim nobody made.
- **Stacked denials** [denial]: after a statement settles a point, another clause denies an implication nobody drew.
- **Repeated checks** [duplicate]: a later sentence re-checks what an earlier one already requires.
- **Empty closing summary** [closing-summary]: a final sentence restates what the content above already showed.

## Defensive text in rules and docs

For `rule` and `docs`, treat `defensive-text` matches as low-value text and delete the entire matching line. Apply the user's selected scope and deletion unit. Keep the document files.

Run `scripts/scan.py docs <paths> --signal defensive-text --max 100000` or the corresponding `rule` command. The scanner reports the original line numbers and leaves editing to the agent. It checks all text lines, including headings, tables, frontmatter, and fenced examples.

The complete phrase and sentence patterns are maintained in [the pattern catalog](references/defensive-text.json). They cover denials, stacked negatives, disclaimers, redundant proof demands, and defensive historical or process explanations. Use this catalog as matching data. A standalone mandatory prohibition is outside these phrase patterns.

After deletion, rerun this signal on the edited paths and check their references.

## Judge within the asked scope

When the user asks about a dimension such as clarity, duplication, or correctness, judge that dimension and name what you checked. Do not widen the question, for example from "is this clearer" to "is this proven to convert better", and then reject the wider claim for lack of evidence.

## Report

Report the agreed scope and a concise diff of what was removed or changed, using file and line references. Pair each affected area with the check actually run and its result; mark checks not run. State the commit status: uncommitted, committed with SHA, and pushed only when verified. Commit or push only when authorized by the task; do not include unrelated changes. Include blockers or failures when present, without listing healthy items.
