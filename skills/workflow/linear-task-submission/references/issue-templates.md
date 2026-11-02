# Linear Issue Templates

Read the shared template and the selected type's requirements. Apply the writing contract in `SKILL.md`. Replace bracketed guidance with confirmed facts. Remove unused optional YAML keys. Mark required unknowns as `待确认` and keep the issue in Triage until its readiness requirements are met.

## Shared body

Use the same four sections for every issue type. Keep stable instructions and necessary warnings visible. Fold supporting history and evidence into `背景`.

````markdown
## 速览

- 做什么：[需要完成的工作]。
- 不做什么：[范围之外的工作]。
- 完成条件：[可检查的最终结果]。

允许：
- [允许的操作或修改范围]。

禁止：
- [禁止的操作或修改范围]。

## 验收标准

- [ ] [检查动作]；预期结果为 [准确结果]。
- [ ] [另一项检查动作]；预期结果为 [准确结果]。

## Agent 上下文

```yaml
inputs:
  - source: "[可访问的仓库、issue、文档或附件标识]"
    purpose: "[用途]"
outputs:
  - destination: "[仓库相对路径或交付平台]"
    format: "[格式]"
environment:
  prerequisites:
    - "[已确认的工具、版本或运行条件]"
  working_directory: "[相对仓库根目录的路径]"
  setup_commands:
    - "[已确认的准备命令]"
steps:
  - warning: "[执行此步骤前必须知道的风险；无风险时删除此键]"
    action: "[一条指令]"
verification:
  - command: "[已确认的验证命令；无需命令时删除此键]"
    expected: "[可观察的准确结果]"
dependencies:
  - "[依赖的 issue ID 或资源标识]"
open_questions:
  - "[影响执行的待确认项]"
```

## 背景

<details>
<summary>背景与证据</summary>

[任务来源、已确认事实和选定类型所需的证据。]

- [来源名称]([可访问的链接])

</details>
````

## Agent context rules

- Include task-relevant inputs, output destinations, execution conditions, actions, and verification. Keep small tasks short. An action can describe manual work when no command is needed.
- Add an `actor` to a step when its owner differs from the issue assignee or needs clarification. Do not invent an owner.
- Use YAML mappings and lists. Quote string values that contain commands, paths, dates, or special characters. Preserve command bytes inside strings.
- Identify repositories by accessible URL or project identity. Use repository-relative paths for files. Describe how the agent locates the repository root.
- State required capabilities and confirmed versions. Let the agent resolve its local checkout and installed tools. Include an absolute host path only when the task targets that exact host.
- Include secret names or approved access methods when required. Keep secret values out of the issue.
- Treat unavailable inputs, unknown commands, and unresolved environment requirements as explicit gaps. State the gap in `open_questions`; do not invent a command or version.
- Put a step-specific warning in `warning` before `action`. Put a warning for manual checks before the applicable acceptance line.
- Keep execution progress and authorization changes in comments. Use `open_questions` only for unresolved task definition or prerequisites.

## Type-specific requirements

Place completion checks in `验收标准`, execution requirements in `Agent 上下文`, and supporting evidence in folded `背景`.

| Type | Properties | Required content |
|---|---|---|
| Bug | `Type/Bug`, team; priority, `Area/*` and `Severity/*` when known and available | Record affected users and environment. Record reproduction steps or other evidence. State actual and expected results. Check the original failure path after the fix. Add adjacent-path checks only when the change creates a regression risk. |
| Feature | `Type/Feature`, team; `Area/*`, project and milestone when known and available | State the user problem and intended behavior. Define scope and observable acceptance. Link specifications and designs. Identify dependencies and required resources. |
| Task | `Type/Task`, team | Identify the input and accessible output. Give an unambiguous completion check. |
| Spike | `Type/Spike`, team | State the research question and method. Specify an exact time box with units or an exact deadline. Define the required output and stop condition. Record the resulting answer and decision in a comment. |
| Design Review | `Type/Design`, team | Link the design target. List the requested feedback and decisions. Define the review output and follow-up ownership. Record the resulting decisions in a comment. |
| Incident | `Type/Incident`, team; `Severity/*` and priority when known and available | Record initial impact, initial status, and known timeline with dates and time zones. Identify the response owner. Define recovery checks and follow-up actions with owners and exact due dates when known. Use private teams or restricted links for sensitive details. Record subsequent status, timeline, recovery, and cause findings in comments. |

Use issue properties for team, owner, status, priority, labels, project, milestone, cycle, estimate, due date, and relations. Repeat a property in the body only when the execution instruction requires it.

## Example issue

This fictional example shows a human-readable issue. Adapt it to confirmed facts; do not submit its invented details as real evidence.

Title: 修复重置密码后无法登录的问题

````markdown
## 速览

- 做什么：修复用户重置密码后无法登录的问题。
- 不做什么：不修改密码重置页面的设计。
- 完成条件：用户可以使用新密码登录。

允许：
- 修改与问题有关的密码重置和登录代码。

禁止：
- 修改现有密码规则。

## 验收标准

- [ ] 使用新密码登录；预期结果为登录成功。
- [ ] 使用旧密码登录；预期结果为登录失败。

## Agent 上下文

```yaml
inputs:
  - source: "账号服务仓库"
    purpose: "检查密码重置和登录流程"
outputs:
  - destination: "账号服务仓库"
    format: "代码变更和验证结果"
steps:
  - action: "复现重置密码后无法登录的问题。"
  - action: "修复已确认的原因。"
  - action: "检查新旧密码的登录结果。"
```

## 背景

<details>
<summary>背景与证据</summary>

测试人员在测试环境重置密码后，使用新密码登录。页面提示密码错误。预期结果是登录成功。

</details>
````
