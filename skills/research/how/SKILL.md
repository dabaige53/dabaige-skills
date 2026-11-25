---
name: how
description: "Use for \"how does X work\", code walkthroughs before changing something, and placement / ownership / layering questions (\"where should this live\", \"which package owns this\", \"is this the right layer\"). Explains subsystem architecture, runtime flow, onboarding mental models. Use why for motivation."
disable-model-invocation: true
---

# How

Explore the codebase to answer "how does X work?" questions. Produce architectural explanations at the level of a senior engineer onboarding onto a subsystem, enough to build a working mental model, not so much that it reads like annotated source code.

Use current Codex tools for a read-only code investigation. Follow applicable local delegation instructions: investigate directly by default, and delegate only when independent parallel exploration clearly justifies its cost. Use only available agent types; inherit the current model unless an authorized override applies. There is no dependency on Cursor model rules or other pstack Skills.

## Explore and explain

Trace the user's question from its entry point through the code that owns the behavior. Gather evidence and write the explanation in the same read-only pass. If the scope is ambiguous, state your interpretation and proceed.

Use the [exploration checklist](references/explorer-prompt.md) for an independent part of a complex investigation. Use the [explanation guide](references/explainer-prompt.md) when a subsystem walkthrough would help the reader.

## Present

Answer the original question, citing the files you inspected. Follow the execution flow, explain ownership, and identify gaps that affect the answer. For a narrow question, give the finding directly.
