---
name: automate-me
description: "Use for \"automate me\", \"create/update/refresh my -mode skill\", \"turn/capture my preferences or working style into a skill\", or wanting agents to follow how the user works. Drafts or revises a personal -mode skill via skill-creator + unslop, optionally pulling fresh evidence from recent conversations."
disable-model-invocation: true
---

# Automate me

A guided flow for turning the user's working conventions into a skill agents will follow. The output is one `-mode` skill tailored to them (e.g. `jay-mode`, `priya-mode`).

Use the history-mining pass below, the installed **skill-creator** for authoring, and **unslop** for prose discipline. Read their available instructions rather than copying them into the mode.

## Flow

### 0. Check for an existing skill

Find matching `*-mode/SKILL.md` files in the current project's declared skill source and relevant personal skill roots. Follow installed links back to their maintained source; don't edit a generated copy or plugin cache. Mode skills can live in category directories. If one exists and the user has not said whether to update or replace it, ask only that unresolved choice:

- Update the existing skill (default for repeat runs)
- Start fresh (rare, ask why before doing it)

Update mode changes the rest of the flow:
- Step 1 mines only history since the skill was last edited (`git log -1 --format=%cI <path>`).
- Step 2 asks what's changed or missing, not what to capture from zero.
- Step 4 edits the existing file in place. Preserve sections the user hasn't contradicted. Revise ones with new evidence. Add new sections only for genuinely new rules.

### 1. Mine their history

Use the current client's conversation tools, scoped to the active project. In Codex, discover `list_threads` and `read_thread`. Use a documented project-scoped transcript source only if those tools are unavailable. Never search unrelated projects without authorization. If history cannot be read, say so and use the conversation and explicit conventions already provided; do not invent evidence.

Survey recent conversations within that scope, usually the last 2–4 weeks unless the user sets a range. Read small sets directly. Delegate independent slices only when useful under local delegation rules; use configured roles and model routing. Give each reader the project, time range and source access. Each returns a short structured list of patterns with conversation IDs and evidence pointers. Default signals worth hunting:

- Response preferences (length, tone, format, "dumb it down" corrections)
- Delegation habits (subagents, models, specialized workflows, parallelism)
- Verification posture (what "done" means, unit tests vs live repro, reviewers)
- Code and prose discipline (style, principles cited, lint/format tools)
- Process conventions (worktrees, commits, PRs, review/merge tooling)
- Meta preferences (fixing skills mid-task, proposing new ones)

Cross-check inferred habits across independent conversations before elevating them. Repeated patterns are stronger than a single example. Explicit current user instructions are requirements and need no repetition; distinguish those from inferred preferences and task-only exceptions.

### 2. Ask the user directly

Use preferences already stated. Ask only when a missing decision would materially change the skill. Use the current client's question tool if available and appropriate; otherwise ask a short chat question. Keep options within the tool's supported format. No mandatory questionnaire or repeated confirmation of settled choices.

### 3. Cluster findings

Group the combined signals into sections. Common ones (use only what applies):

- **Response style**: length, tone, format.
- **Autonomy**: how much to do without asking, MCP tool use.
- **Understand first**: which skills to reach for when scoping or investigating a change.
- **Subagents**: default, parallelism, model-to-task, specialized workflows.
- **Prose / code discipline**: principles, lint tools, style guides.
- **Review and verify**: repro posture, verification skills, live-testing tools.
- **Process**: git worktrees, commits, PRs, review/merge tooling.
- **Skills**: skill-authoring habits, fix-the-skill-first, proposing new skills.

If the user provides a reference mode such as **poteto-mode**, read it for granularity. It is optional inspiration, not a runtime dependency. Don't copy its workflow, agent names or models into the user's mode.

### 4. Draft the skill

Use the installed **skill-creator** to author the skill. Placement:

- Path: preserve an existing mode skill's source and category. For a new mode, follow the project's skill-maintenance rules. In this Skills repository, use `skills/workflow/<handle>-mode/SKILL.md` and register its source. Distribute through Magpie when installation is authorized; don't create global links yourself.
- Handle: the user's first name or chosen identifier.
- Frontmatter `description`: trigger on their name + `/<handle>-mode` + "work in their style", not on generic keywords like "write code" or "review PR".
- Frontmatter formatting: follow `skill-creator`'s YAML rules. Keep `description` as one YAML scalar. Quote it or use `description: >-` with indented continuation lines when punctuation or wrapping requires it.
- Preserve the user's invocation choice separately for each client. For a requested manual mode in Codex, set `agents/openai.yaml` to `policy.allow_implicit_invocation: false`; use `disable-model-invocation` only for clients that support it. Don't silently enable a mode on every turn.
- If the user asks to review included skills before writing, report that list first and leave mode creation pending.

### 5. Iterate on prose

Apply the **unslop** skill and `skill-creator`'s writing guidelines to every line.

Show the draft to the user and take feedback. Expect multiple iterations. Cut ruthlessly. A mode skill is not a manual.

### 6. Land it

Save the skill in the authorized source location and follow its registration rules. Worktrees, commits, pushes, PRs and installation each follow the current request and project rules; authoring a skill alone does not authorize them.

## Guardrails

- **Don't overfit to one conversation.** Require repeated evidence for inferred habits. Follow explicit current instructions and record only their stated scope; a task-only exception is not a permanent rule.
- **Don't be clever.** Restating other skills' contents, inventing metaphors, or writing "poetic" prose for an agent reader is cost without benefit. Keep it operational.
- **Reference, don't inline.** Other skills the user relies on should appear as path references, not pasted excerpts. Same for any principle docs they maintain elsewhere.
- **Keep sections minimal.** Only add a section if the user has a specific, non-default rule there. "Communicate clearly" is not a section. "Short paragraphs. Tables when comparing options. Bullets only when items are genuinely parallel." is.
- **Name conventions generic.** Use "the user" or "the human" in imperatives, not the author's first name.
- **Don't force symmetry.** If a user has no process rules worth writing down, skip the Process section entirely.

## Evaluation

A `-mode` skill is subjective output. A benchmark loop isn't useful here. Review the wording with the user: does it reflect their choices and omit anything important? Honor requests to write without tests or validation.

Run a description-optimization loop only if the skill's trigger accuracy turns out to be a problem in practice.

## When not to use

- User wants a task-specific skill (not working conventions): `skill-creator` alone, no mining required.
- User wants to capture one narrow workflow (e.g. "how I write commit messages"). That's a regular skill, not a mode skill.
