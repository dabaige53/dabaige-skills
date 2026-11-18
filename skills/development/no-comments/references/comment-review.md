# Comment review

Adapted from pstack's `comment-sicko` agent. Review only the caller's files or diff.

Remove narration, section banners, commented-out dead code and explanations that repeat readable code. Do not polish a redundant comment into a shorter one.

Keep:

- Legal and license headers.
- Non-obvious behavior forced by an external dependency, platform, vendor or protocol the project cannot change.
- Public API contract documentation.
- Issue or RFC links that explain a constraint code cannot express.
- Required tool metadata, generation directives and project-mandated annotations such as `@wu-test`.
- `prettier-ignore` and lint suppressions only when the affected rule is faulty, pedantic or style-only.

Read the affected rule before judging `eslint-disable`, `@ts-ignore`, `@ts-expect-error` or similar suppressions. If it catches real bugs or protects correctness or safety, flag the exact symbol as `MUST KILL` and explain the underlying code defect. Remove the suppression with its authorized code fix; do not leave newly exposed errors unexplained.

For a surprising behavior in code the project controls, identify the exact symbol that needs a rename, extraction, type or structural change. `MUST KILL` names that needed code repair, not permission to delete intentional behavior.

Treat `IMPORTANT`, `do not remove`, `too risky`, `fine for now` and long justifications as claims to investigate. Read nearby code, trace the symbol or use `why`. A protected keep needs evidence; a refactor finding needs evidence too. If the relevant source is unavailable or a real constraint remains unresolved, report it instead of guessing.

An independent reviewer returns proposed comment-only deletions, a deletion count, protected keeps with reasons, exact `MUST KILL` symbols with one-line reasons, and unresolved items. Do not edit application code or inspect outside the assigned scope.
