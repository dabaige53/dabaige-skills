---
disable-model-invocation: true
name: ci-tuning
description: 基于项目现有 GitHub Actions CI 做工程化提速：建立 CI.md 与统一 CI Hook，重组 Lint、Typecheck、Test、Build 任务，编排并发、Matrix、分片与关键路径，加速缓存、Checkout、依赖安装、环境和 Lint，并用运行数据验证覆盖与耗时。通过 `$ci-tuning init|organize|parallel|accelerate|validate` 调用；只用 GitHub 标准免费 Runner，不削弱质量门禁。
argument-hint: "<init|organize|parallel|accelerate|validate> [范围]"
---

# CI Tuning


## 命令

第一个参数选模块，其余参数限定范围（任务组、workflow 或加速项）。只读取所选模块的文件；其他 reference 在被引用时再读。

| 命令 | 目标 | 读取 |
| --- | --- | --- |
| `init` | 建立 CI 工程规范：CI.md、统一 CI Hook、任务入口和基础约定 | `references/init.md` |
| `organize` | 重新分组 Lint、Typecheck、Test、Build，消除重复，理顺依赖 | `references/organize.md` |
| `parallel` | 多 Job 并发、Matrix、测试分片、DAG、关键路径、并发控制、按改动运行 | `references/parallel.md` |
| `accelerate [范围]` | 提升单个 Job 的执行速度 | `references/accelerate/<范围>.md` |
| `validate` | 核对任务覆盖、质量门禁、实际执行结果和前后耗时 | `references/validate.md` |

`accelerate` 的范围：

| 范围 | 内容 | 文件 |
| --- | --- | --- |
| `lint`（含 `format`、`typecheck`） | 高性能 Lint、Formatter、Typechecker，工具缓存，替换前的规则等价验证 | `accelerate/lint.md` |
| `cache` | 依赖与构建缓存、默认分支播种、key 设计、容量 | `accelerate/cache.md` |
| `checkout` | 浅克隆、blobless、sparse、LFS、submodule | `accelerate/checkout.md` |
| `deps` | 依赖安装方式与安装范围 | `accelerate/deps.md` |
| `env` | 工具链、预编译工具安装、service container、Docker、Runner 选择 | `accelerate/env.md` |
| `build` | 连续构建检查、增量构建缓存、产物复用 | `accelerate/build.md` |
| `test` | 测试进程并发与核数、加载开销（不改测试内容） | `accelerate/test.md` |

未给范围时先测量，按各项占关键路径的时间从大到小选一至两项。

未给模块时从请求推断。请求笼统（如“优化 CI”）时，先完成基线测量，按关键路径收益给出模块顺序，从收益最大的模块开始；完成一个模块并验证后再进入下一个。

## 执行规则

1. **从现状出发。** 先读 `.github/workflows/`、本地 action、CI 调用的脚本与任务入口、依赖清单、必需检查（branch protection 或 ruleset）和最近的运行记录，再决定改什么。不套通用模板。
2. **先测基线。** 修改前运行 `workflow_audit.py` 和 `run_stats.py runs`，原始输出存到项目的 `.ci-tuning/<日期>-before/`，把 `.ci-tuning/` 写入 `.git/info/exclude`，不提交。拿不到运行记录时说明原因，之后只能依靠静态对比和改动后的实际运行验证。
3. **优化目标是等待时间。** 主要指标是同一提交全部检查完成的 wall-clock P50/P95 和关键路径，不是 Job 数量或计算分钟。
4. **只用免费 Runner。** 只使用 GitHub 标准托管 Runner；不引入 larger runner、第三方 Runner 或付费远程缓存。已存在的保持原样，在报告中标出。平台限制和已核实的事实见 `references/github-free-ci.md`。
5. **质量门禁不降。** 不删除或跳过必需检查；不加 `continue-on-error`、`|| true`、`--passWithNoTests`；不降低阈值或严格级别；不靠重试变绿。按改动跳过检查必须有全量兜底和跳过逻辑自检（见 `parallel.md`）。
6. **测试只改编排。** 可以调整分组、分片、并发度和运行配置；不修改、合并或删除测试用例。需要改测试基础设施的项（如关闭隔离、补状态清理），先给出证据并征得用户同意。
7. **替换工具先证明等价。** 替换 Lint、Formatter、Typechecker 或构建工具前，按对应 reference 对比规则和输出。新工具未覆盖的部分保留原工具，或把取舍交给用户决定。
8. **不默认安装本地 Git Hook。** CI Hook 指项目统一的检查入口；pre-push 等本地 Hook 只在用户明确要求时安装。
10. **保护现有改动与仓库设置。** 检查工作区，只改本模块范围内的文件。必需检查名称、ruleset 等仓库设置的变更，给出具体操作，由用户执行或确认。推送分支、创建 PR、触发或重跑 workflow 前先征得同意。
11. **以实际运行为准。** 每组改动后运行 `compare.py coverage`（有 actionlint 时一并运行），再用真实运行验证。不能只凭 YAML 看起来合理就宣布完成。

## 脚本

脚本在本 Skill 的 `scripts/` 目录，只读取、不修改项目文件。需要 Python 3.9+；`workflow_audit.py` 依赖 PyYAML，缺失时用 `uv run --no-project --with pyyaml python …` 运行；访问 GitHub 的脚本需要已登录的 `gh`。

| 脚本 | 用途 |
| --- | --- |
| `workflow_audit.py [ROOT] --json OUT` | 解析 workflow 和本地 action：触发事件、Job DAG、Matrix 规模、检查名称、质量命令分类；列出重复任务、缺少并发控制、PR 独占缓存、门禁削弱、从源码编译工具、平台无关检查占用 macOS/Windows 等问题 |
| `run_stats.py runs --json OUT [--logs N]` | 把每个 Job 拆成排队、setup、执行、收尾；统计提交级 wall-clock P50/P95、推断关键路径、首跑失败率、flaky 运行与重跑；`--logs` 从日志统计缓存命中 |
| `run_stats.py caches` | 按 ref 和 key 族统计缓存：默认分支是否有种子、PR 缓存占比、容量与 key 抖动 |
| `shard_plan.py` | 用 JUnit 或 durations 耗时做均衡分片，预测不同分片数下的最长分片 |
| `compare.py coverage｜timing｜tests` | 对比改动前后：检查覆盖与门禁、耗时分布、测试集合完整性 |

参数以各脚本的 `--help` 为准。

## 报告

说明改了哪些文件（附行号）、基线与结果（P50/P95、关键路径、样本量与时间范围）、门禁保留的证据（`compare.py coverage` 结论）、未验证的项目，以及需要用户处理的仓库设置。项目有 CI.md 时同步更新对应章节。
