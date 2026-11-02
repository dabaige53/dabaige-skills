# Rule Cleanup

`value-cleaner rule` removes rule text that changes no action: agent instructions such as `AGENTS.md` and `CLAUDE.md`, skill files, policies, and style guides. Scan signals are in brackets.

## Decision rule

A rule earns its place when it changes which action is taken under a stated condition and no other rule already sets that action.

> Under what condition does this change which action, and where else is it already stated?

## Keep

- A condition and action that change output, such as "when only one item reports a count, do not fill the others with zero". It reads like a caveat but changes what gets written.
- Output requirements the user chose, such as a reply language or a sign-off.
- The reason behind a rule when the reason changes how it is applied.
- Authorization boundaries, safety limits, and required checks.
- The canonical copy of a rule that other files point to.

## Candidates

### Duplicate rules [duplicate]

The same requirement in several files or sections, often in slightly different wording, or a local rule restating a global one without narrowing it. Keep the rule in the file that owns its scope and delete the copies.

### Admonitions without scope [vague-caution]

"Be careful", "ensure quality", "consider edge cases", "when necessary", or "signals are not proof", repeated across sections with no condition, so following them changes no action. Delete them, or rewrite as a condition and an action when a real one exists. Keep a necessary caution once, where it changes a decision.

### Sections forced into every output [every-output]

A template requires every reply or report to carry limitations, residual risk, caveats, or a closing disclaimer whether or not there is anything to say, so outputs fill it with routine text. A cleanup report template that required `## Residual risk` every time is one case. Tie the section to a concrete blocker, failure, or open item, or remove it.

### Exceptions piled up around one mistake [exception-chain]

A chain of "except", "unless", and "also do not" clauses, each added after an incident and narrowing the previous one. Restate the underlying rule once so it covers the cases, and drop the clauses it already covers.

### Cleanup residue [broken-link, missing-path]

A rule that maintains, preserves, or links to content already deleted. After an originality statement was removed from a style guide, its maintenance section still said "keep the source and originality note for each example". Delete such rules together with the content they served.

## Examples

### Unrequested proof

A writing skill adapted from an article about lists and feeds ended with:

> The extension to Chinese and single documents is practical guidance; it does not claim the original research proves it applies to every language and genre.

No reader needed that proof. The paragraph was deleted.

### Repeated checks

> Distinguish planned, in-progress, and completed work; use each word only when the material supports it. A task title does not prove the task is complete.

The second sentence re-checks a case the first already covers. Delete it.

## Removing

Before calling a rule duplicated or unused, find every file that loads or references it: nested instruction files, skill references, templates, and generated copies.
