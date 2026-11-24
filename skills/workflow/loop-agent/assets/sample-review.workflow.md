# sample-review 工作流

- 工作流 ID：`sample-review`
- 执行定义：[workflow.example.json](workflow.example.json)
- 触发：手动；离线样本，未接入实际调度器。

## 执行路线

`collect` → `analyze` → `verify`

| 步骤 ID | 主体 | 输入 → 输出 | 紧前 | 紧后 | 完成条件 |
|---|---|---|---|---|---|
| collect | 脚本 | 无 → 样本 JSON | 无 | analyze | JSON 可解析，sample=true |
| analyze | AI | 样本 JSON → status、findings、evidence | collect | verify | 空记录返回 no_data，非空结论引用证据 |
| verify | 脚本 | 分析 JSON → 结构校验结果 | analyze | 无 | status 合法，findings、evidence 为列表 |

脚本命令见执行定义；AI 入口见 [analysis-prompt.example.md](analysis-prompt.example.md)。

## 分支与异常

- 空样本：analyze 返回 no_data，仍进入 verify。
- 失败：由实际执行器落实超时、有限重试和失败出口，并验证这些控制能力。记录失败步骤及恢复条件；必需步骤全部通过后标记完成。

## 完成判定

样本标识和本轮输入范围清楚；结论与证据一致；结构校验通过。真实业务验收另行验证。

本文描述计划路线；实际执行者、耗时和步骤状态从运行事件获取。
