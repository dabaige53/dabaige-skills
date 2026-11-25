---
name: linear-task-submission
description: Manage Linear issues and projects. Use when drafting, creating, editing, or reviewing Linear issues, including Simplified Chinese issue descriptions and agent execution context.
---

# Linear Task Submission

Keep Linear work concrete and executable. Use properties for filtering and reporting, the issue body for stable context and acceptance criteria, and comments for progress and closure proof. These are Wu's local working conventions.

## Issue writing contract

Write for a busy engineer and an AI agent that must execute the task in any environment. Apply this contract to issue drafts, new issues, and edited text in existing issues.

- Write in Simplified Chinese. Apply ASD-STE100 principles to about 80% of the prose; treat this as a writing target, not formal STE compliance or a word-count quota. Keep domain terms, identifiers, commands, and code exact. Use the remaining 20% where rigid simplification would reduce clarity.
- Use short, natural sentences and active voice. State each action clearly. Name the actor when ownership or a handoff would otherwise be unclear; use the issue assignee and context when they already identify the owner.
- Use one term for one meaning. Keep the same term throughout the issue.
- Put each warning before the step to which it applies.
- Express boundaries as `允许` and `禁止` lists. State each boundary directly instead of stacking negatives.
- Use exact numbers and units. Write dates as `YYYY-MM-DD`. Include the time zone for times. Mark unknown values as `待确认`; preserve known facts instead of inventing precision.
- Use this body order: `速览` (做什么 / 不做什么 / 完成条件) → `验收标准` (one check per line) → `Agent 上下文` (YAML) → `背景` (folded). Read [issue templates](references/issue-templates.md) before drafting or restructuring a body.
- Keep progress, execution results, closure evidence, and authorization changes in issue comments. Keep the body as the stable task definition. Put current status, assignee, and dates in issue properties where supported. An authorization summary in a comment records authorization; it does not grant authorization to another agent.
- For a narrow edit, apply these rules to the changed text and preserve other content. Reorganize the whole body only when the request covers the description or its structure. Preserve evidence and links during reorganization.

Before writing, check section order, one check per acceptance line, valid YAML, portable execution context, and folded background. Remove unused placeholders from the submitted text.

## Comments and agent replies

Write issue comments and agent replies in natural Simplified Chinese for people to read, including when an agent is the author. Avoid first-person references such as `我`. State the next action directly, such as `还需要验证新旧密码的登录结果`. Name an owner only when needed to clarify responsibility or a handoff; mark an unresolved owner as `待确认` when it matters. Do not imply that an agent will act without an assigned action or authorization. Keep updates concise while retaining necessary context. Lead with the relevant result or finding. Add the next action, blocker, decision, or evidence link only when relevant. Do not force a fixed template, label every sentence, or repeat the issue body.

Record useful experience as a concrete trigger, finding, and future action. Distinguish verified facts from unverified hypotheses. When an experience applies beyond this issue, link to an existing shared document or propose adding it there; do not change external documents without authorization.

Add `## Agent 上下文` or `## 背景` only when extra execution context or supporting evidence is needed. Keep each section concise; omit both for ordinary updates and replies. Comments record authorization but do not grant it.

Examples (adapt to the facts; do not copy invented results):

- Progress comment: `测试环境已复现：重置密码后，登录服务还在读取旧缓存。需要检查缓存为什么没有失效。`
- Agent reply to a request for status: `问题已定位到登录缓存，修复还没有验证。还需要用新旧密码各测试一次。`
- Agent reply when extra execution context is needed: `还需要验证修复。\n\n## Agent 上下文\n\n使用测试账号重置密码，再分别用新密码和旧密码登录。\n\n## 背景\n\n重置密码后，登录服务仍读取旧缓存。`

## Local defaults and sources

- Read the relevant team, person, status, label, project or recent-issue index in `~/.codex/linear/` as needed. Select the relevant cached JSON files rather than loading every index for every request.
- Default assignee: Wu Wenyuan, unless the user or current work specifies someone else. Resolve the person's ID from the relevant index or connector; do not invent it.
- Query Linear when the user requests current verification or the needed cache is missing or stale. Update the relevant index after obtaining new information. A cache is evidence of a past state, not proof of current status.
- Use the available Linear connector and its current field schemas. Preserve existing team, project and issue identities during edits.
- Linear is a shared team platform. Store formal, editable deliverables in Google Drive by default and link them from Linear; one-off screenshots or temporary diagrams may be attachments. Use the audience and permissions authorized for the task.

## Choose the work item

| Input | Destination |
|---|---|
| Concrete task, bug, feature slice, spike, design review or incident | Issue with an owner path and completion condition |
| Ambiguous idea, PRD or research corpus needing definition | Document or specification |
| Large initiative with a clear goal and time boundary | Project |
| Work spanning teams, independent deliverables or large estimates | Sub-issues with explicit dependencies |

For an existing issue or project, inspect the current object and update only the requested fields. For a project request, apply the local source and delivery conventions above; the issue templates apply only when preparing issues.

## Prepare an issue

1. Identify the type: `Type/Bug`, `Type/Feature`, `Type/Task`, `Type/Spike`, `Type/Design` or `Type/Incident`.
2. Resolve team, project and known relations. Use the default assignee unless overridden. An assignee is required before Todo or In Progress and optional in Triage.
3. Draft an executable title and description under the issue writing contract. Use the shared template and the selected type's evidence requirements. Keep all four sections concise for small tasks.
4. Set properties that are known: status, priority, assignee, project, milestone, cycle, estimate, due date, labels and relations. Use priority for handling order and `Severity/*` for impact; add `Area/*`, `Platform/*`, `Service/*` or `Source/*` when relevant and available.
5. Check readiness, perform the authorized action, then verify the result.

## Readiness and authorization

Every issue needs a title, a confirmed team, a type label and a nonempty description. Record evidence for bugs and incidents; define acceptance or completion for bugs, features, tasks, spikes and design reviews. Add known blocked, related, duplicate, parent and sub-issue links.

Incomplete work belongs in Triage with the missing information stated. Do not mark it ready or fill gaps with invented facts. If the team is unresolved, prepare the draft and ask the one question needed to route it. Other missing information requires a question only when it changes type, privacy or whether the issue should exist.

A request to draft or review produces a draft or findings. An explicit request to create, update or move the object authorizes that action once its target and fields are concrete; reuse existing authorization. Do not create duplicates while editing an existing item.

Before leaving Triage, check the evidence relevant to the type:

- Bug: reproduction or other evidence, impact and an owner path.
- Feature: background, goal, boundaries, acceptance criteria and required resources.
- Task: accessible output and an unambiguous completion definition.
- Spike: research question, method, output and a time-boxed stop condition.
- Design review: feedback target and decision points.
- Incident: impact, initial status and timeline, owner and follow-up actions. Record subsequent status and timeline updates in comments.

## Verify and close

Read back created or changed objects where the connector supports it. Report the actual ID or link, changed fields, assumptions and remaining gaps. An empty or uncertain write response calls for a status check before retrying.

Closing requires evidence, not only a status change: verify the bug fix or feature acceptance; make task output accessible; record the spike's answer and decision; capture design decisions and follow-up work; confirm incident recovery and record the timeline, cause and action owners. Record these results and relevant PRs, commits, documents or other completion evidence in comments. Apply only checks relevant to the work and already authorized scope.
