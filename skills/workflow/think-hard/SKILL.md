---
name: think-hard
description: Use $think-hard for independent reasoning and alternative solutions.
---

# Think Hard

Do not optimize the path before questioning the path. Preserve truth, constraints, and evidence—not accidental structure.

## Workflow

1. Freeze the problem before changing the solution.
   - Extract the objective, hard constraints, success criteria, known facts, and unresolved uncertainties.
   - Treat every existing draft, plan, architecture, and explanation as a hypothesis rather than an authority.

2. Delegate the rethink when delegation is allowed by the current request.
   - If the user forbids subagents, continue the analysis locally and disclose that there was no independent review. This Skill does not override that constraint.
   - Read the applicable delegation guidance. Spawn one independent subagent with `agent_type: "think_hard"` and `fork_turns: "none"`; provide the evidence explicitly so it can challenge the current framing without inheriting the full conversation. Require it to finish without further delegation.
   - Instruct it to perform read-only analysis and research; do not ask it to implement or edit files.
   - Give it the objective, constraints, success criteria, and relevant evidence. Label the current solution as only one candidate.
   - Require it to reconstruct the problem, challenge inherited assumptions, explore up to three orthogonal alternatives, search for decision-changing evidence when needed, and recommend a direction.
   - Wait for the subagent result before committing to a path. Do not simulate delegation.

3. If the custom role is unavailable, report the limitation and continue locally without claiming independent review. Use another role or model only when the current user instructions or applicable guidance authorize that substitution.

4. Synthesize rather than copy.
   - Compare the subagent's analysis with the current path.
   - Preserve validated facts, constraints, useful evidence, and working components.
   - Discard inherited structure, assumptions, and patches that survive only because they already exist.
   - Reject novelty that is merely different. Prefer a new path only when it has a plausible advantage.
   - If the current path remains best, state why it has earned the right to continue.

## Output contract

Adapt the presentation to the user's task, but make the decision legible through these elements:

- Problem reframe
- Assumptions challenged
- Strongest alternatives, no more than three
- Material evidence
- Recommendation and tradeoffs
- What to preserve and what to abandon

Return conclusions and evidence, not the subagent's hidden reasoning or raw search log.
