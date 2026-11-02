---
name: how
description: "Use for \"how does X work\", code walkthroughs before changing something, and placement / ownership / layering questions (\"where should this live\", \"which package owns this\", \"is this the right layer\"). Explains subsystem architecture, runtime flow, onboarding mental models. Use why for motivation."
disable-model-invocation: false
---

# How

Explore the codebase to answer "how does X work?" questions. Produce architectural explanations at the level of a senior engineer onboarding onto a subsystem, enough to build a working mental model, not so much that it reads like annotated source code.

Use current Codex tools for a read-only code investigation. Follow applicable local delegation instructions: investigate directly by default, and delegate only when independent parallel exploration clearly justifies its cost. Use only available agent types; inherit the current model unless an authorized override applies. There is no dependency on Cursor model rules or other pstack Skills.

## 1. Assess complexity

If the scope is ambiguous, state your interpretation and explore. The user can redirect.

- **Simple** (a single module, a small utility, a narrow question such as "how does function X work"): explore and explain directly. Use [explainer-prompt.md](references/explainer-prompt.md) as a checklist without the explorer-findings section. Go to step 4.
- **Complex** (a subsystem spanning multiple files or services, a cross-cutting feature, a full architectural overview): go to step 2.

When in doubt, take the simple path.

## 2. Explore (complex only)

Decompose the question into distinct, non-overlapping angles. Investigate directly unless delegation is justified by the rules above. When delegating, use the smallest useful number of explorers within session limits, each with [explorer-prompt.md](references/explorer-prompt.md), its assigned scope and explicit read-only responsibility. Otherwise use the same checklist for focused passes.

## 3. Synthesize (complex only)

Synthesize the findings directly using [explainer-prompt.md](references/explainer-prompt.md). If independent synthesis is separately justified, give the reviewer all findings and the original question; do not create an extra agent only to rephrase the answer.

## 4. Present

Answer the original question in language suited to the current reader. Cite inspected files and explain necessary terms. Reconcile contradictory findings by checking the code; keep unresolved gaps visible. A diagram is useful only when it clarifies the actual flow.

## Output format

The explanation uses the sections defined in `references/explainer-prompt.md`, dropping any that do not apply: Overview, Key Concepts, How It Works, Where Things Live, Gotchas.
