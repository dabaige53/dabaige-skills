# 通用描述与辅助程序

现有平台配置作为唯一来源；需要通用检查时导出兼容视图。JSON 示例在 [workflow.example.json](../assets/workflow.example.json)，字段类型由 lint 校验。JSON 可直接使用；YAML 需要目标环境已有 PyYAML。禁止重复键（含合并后重复键），避免静默覆盖。

## 调用

在当前 Skill 目录使用 `python3 scripts/workflow_tools.py <子命令> --help` 查询参数；调用时传入实际配置路径。

| 子命令 | 用途与结果边界 |
|---|---|
| lint | 校验描述、文件引用和依赖图；运行能力交给 validate 验证 |
| preflight | 当前环境中的命令、变量存在性和文件快照；目标鉴权与调度能力另取证据 |
| collect | 从配置或参数指定的日志作有界读取；复核脱敏片段后分享 |
| report | 汇总指定 run 的计划关系、实际事件及已观测用量 |
| audit | 有界多轮审计：重复失败签名、已观测用量/时间/尝试次数超限、静默、版本混用 |

业务执行使用项目执行器。辅助命令默认 stdout；`--output` 保存到已存在的父目录，并保护输入配置、日志、事件、状态及引用文件免遭覆盖。退出码 0/1/2 分别表示辅助操作成功、检查或证据错误、输入或调用错误。

collect 在业务 Lint 失败时仍可取证；report/audit 在工作流与步骤 ID 可识别时继续汇总。三者附 configuration_issues；report 的无效依赖图 planned_route 为 null。

`audit --config <文件> --events <文件> --max-runs 20 --stale-seconds <秒>`：按最近观测事件选择运行（最多 100 轮）；静默阈值可省略，`--as-of` 可固定观测时间。当前配置上限未必适用于历史版本；结果是调查线索，不证明根因、连续失败、进程卡死或预算机制生效。需比较时选择版本、输入和计量口径一致的样本。

## 路径语义

| 路径 | 解析基准 |
|---|---|
| `--config`、`--output`、`--project-root` | 当前工作目录 |
| `paths.project_root` | 配置文件目录；省略时取该目录 |
| 其他配置路径、`--log`、`--events` | project_root；命令行 root 覆盖配置值 |

`logs: []`、`state: null` 表示尚未声明对应的本地来源；平台存储通过已有工具访问。数据库或对象存储需要已有适配器导出最小文件证据。

## 描述中的业务语义

- `max_attempts` 包含第一次尝试；`side_effects` 包括写文件、发送和远端修改。
- `controls` 记录实际执行约束的组件与落实状态。`needs` 的并行层还须满足资源限制；`when` 条件交由项目执行器解释。
- `agent` 可填角色；实际 Agent/会话身份从运行记录获取。`related_workflows` 记录真实关联与接入状态。
- `kind` 支持 script/tool/ai/human。使用现有 CLI 时可省略 `script_file`；tool 用 `tool_ref` 标识目标执行器的工具或连接器操作；AI 步骤引用可复用的 `prompt_file`。静态检查不证明工具可达。复杂平台类型保持原生表达。
- 扩展字段可保留；Cron、时区、触发器与平台专用字段由对应平台校验。

## 事件与计量

UTF-8 JSONL，每行一个事件。必填带时区的 timestamp、workflow_id、run_id、step_id、正整数 attempt 和 status。状态支持 pending/running/succeeded/failed/blocked/skipped/cancelled/timed_out。

```json
{"timestamp":"2026-11-24T09:00:00+08:00","workflow_id":"sample-review","run_id":"example-run-01","step_id":"collect","status":"succeeded","attempt":1,"event_id":"collect-1-done","agent_id":null,"duration_seconds":0.3,"tokens":null,"tool_calls":1}
```

event_id 用于去重，内容冲突标记证据不完整。可选 agent_id、reason、workflow_revision 为字符串或 null；reason_code 为稳定的大写机器分类码（如 AUTH_REQUIRED、INPUT_NOT_READY），不含凭据、随机 ID 或易变描述，用于跨轮归类；来源缺失、截断、格式错误及工作流不匹配均保留完整性提示。

duration_seconds、tokens、tool_calls 使用**本步骤本次 attempt 的累计终值**，未知为 null。来源使用工作流累计值或增量片段时先适配。每个 attempt 取最后快照，只汇总终态已知值并报告覆盖范围；重试产生的消耗计入成本。

事件顺序为输入文件顺序及行顺序。跨来源精确时序需要先整理时间与重复记录。步骤状态由事件汇总；业务 completion 由 validate 核查产物与回执，辅助报告中的 completion_verified 保持 false。
