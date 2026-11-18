---
name: wu-mode
description: Wu 的工程工作方式。明确调用时，Agent 按任务选择做法，自主推进，把结果和需要判断的取舍交给用户。
disable-model-invocation: true
---

# Wu mode

## 遇到这些情况就这样做（Non-negotiables）

- 开始一项工程改动 → 一句话说清目标和最小改动。技术分歧若能通过一次小实验解决，走[原型](playbooks/prototype.md)。
- 写代码 → 先确定数据形状、谁负责写入、谁负责读取。结果要在用户实际使用的入口上判断；某个入口没有运行，就明确说明。
- 报性能数字 → 说明基线、负载、波动和实际完成的工作量。长任务 → 将影响下一步的决定记入项目已有记录。查 PR → 按[跟进 PR](playbooks/babysit.md)区分一次查询和持续跟进。
- 存在两种会导致不同交付的理解 → 用 [in-your-own-words](../in-your-own-words/SKILL.md) 说清分歧。用户要推敲任务要求 → [sharpen](../sharpen/SKILL.md)；要深入讨论取舍 → [grilling](../grilling/SKILL.md)。
- 接续已有工作 → 先找上次停在哪里。跨本机、Mac mini、云端时，以项目共用的任务记录、数据和产物为准。区分“本机已改”“已推送”“目标端已生效”。
- 发现改动可能影响其他使用方 → 用 [blast-radius](../../development/blast-radius/SKILL.md) 查关键依赖。用户要清理内容 → [value-cleaner](../../development/value-cleaner/SKILL.md)；明确清注释 → [no-comments](../../development/no-comments/SKILL.md)。
- 写技术文档 → [technical-writing](../technical-writing/SKILL.md)；写 PR 正文 → [pr](../../development/pr/SKILL.md)；写给 Agent 的规则 → [writing-for-agents](../writing-for-agents/SKILL.md)。用 [unslop](../../creative/unslop/SKILL.md) 删掉不影响理解的套话。
- 用户要理解一个功能 → [teach](../teach/SKILL.md)，由它按需使用 `how`、`why`。只要求把上一条说简单 → [bro](../bro/SKILL.md)，直接重述。

## 判断原则（Principles）

按[判断原则](references/principles.md)选择真正会改变本次做法的条目。设计看 Core、Architecture；修复和测量看 Verification；反复纠正同一问题看 Meta。需要解释取舍时，说清哪条原则改变了哪个决定。

## 按任务执行（Playbooks）

选择与交付物匹配的一项，只打开该项的步骤。已有 Skill 自带完整流程时，直接以它作为 playbook。

| 要交付什么 | 打开哪个流程 |
| --- | --- |
| 接着做上次未完的工作 | [接续任务](playbooks/session-pickup.md) |
| 做一个新功能 | [功能开发](playbooks/feature.md) |
| 排查并修复故障 | [故障修复](playbooks/bug-fix.md) |
| 把一个目标拆成一批可执行任务 | [多阶段计划](playbooks/multi-phase-plan.md) |
| 回答实现或设计问题，不改代码 | [只读调查](playbooks/investigation.md) |
| 整理代码结构且保持行为不变 | [重构](playbooks/refactoring.md) |
| 用最小实验比较方案 | [原型](playbooks/prototype.md) |
| 查一次性能问题；或围绕指标持续改进 | [单次性能问题](playbooks/perf-issue.md) / [多轮优化](playbooks/hillclimb.md) |
| 观察正在运行的程序；或分析已有采样 | [运行时调查](playbooks/runtime-forensics.md) / [采样分析](playbooks/trace-forensics.md) |
| 判断 UI 迁移是否保持视觉一致 | [视觉对照](playbooks/visual-parity.md) |
| 用同一任务比较多个方案的产出 | [盲评](playbooks/eval.md) |
| 编写或修改普通 Skill | [编写 Skill](playbooks/authoring-a-skill.md) |
| 准备 PR；或查看已有 PR 的状态 | [准备 PR](playbooks/opening-a-pr.md) / [跟进 PR](playbooks/babysit.md) |
| 连续执行直到达到明确目标；或应用户要求暂停 | [连续执行](playbooks/autonomous-run.md) / [安全暂停](playbooks/pause-safely.md) |
| 整理目录与文档 | [project-maintenance](../project-maintenance/SKILL.md) |
| 配置新项目或迁移旧项目到多端 | [cloud-setup](../../development/cloud-setup/SKILL.md)：逐个子项目交代在哪里运行、哪些必须本地配、共用什么、还有什么没解决 |
| 清理旧产物和缓存；或清理 worktree | 目录用 [workspace-cleanup](../../development/workspace-cleanup/SKILL.md)，涉及 worktree 时先走 [worktree 清理](playbooks/worktree-cleanup.md) |
| 根据反复出现的工作习惯更新本 mode | [automate-me](../automate-me/SKILL.md)：区分长期偏好和本次例外 |

没有完全匹配的流程时，按实际目标选相邻步骤，明确停止条件。
