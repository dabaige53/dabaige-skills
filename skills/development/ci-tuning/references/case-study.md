# 案例与开源实践

## 1. Owen：How I made our CI 20x faster

来源：Owen Gretzinger（Boardy），[How I made our CI 20x faster (steal this)](https://twitter.com/owengretzinger/status/2116291924219060319)，2026-10。PR 等待 CI 的时间从最长 40 分钟降到 2 分钟。背景是代码主要由 Agent 编写，Agent 反复“推送、等 CI、修红灯、再推送”，CI 成了整个循环里最慢的一段。

下表逐条列出原文做法，以及在 GitHub 免费 Runner 上能否使用。

| # | 原文做法 | 原文效果 | 免费 Runner 上的用法 | 模块 |
| --- | --- | --- | --- | --- |
| 1 | 所有 Job 迁出 GitHub 默认 Runner（Blacksmith），小 Job 也迁 | 等机器从最长 11 分钟降到 8 秒；整体 40→10 分钟 | 付费方案，不采用。保留其结论：排队时间算在关键路径里，“5 秒的 Job 等 10 分钟机器就是 10 分钟的 Job”。测量 `queue_p95`，取消过期运行，控制每次 PR 展开的 Job 数，合并秒级小 Job | `parallel`、`organize` |
| 2 | ESLint 换成 Oxlint，规则尽量全开 | Lint 2 分钟→5 秒 | 可用。先验证规则等价，未覆盖的规则保留 ESLint。“规则全开”会提高门禁，单独征求用户同意 | `accelerate lint` |
| 3 | 更快的 Typechecker 一出就换（tsc → TypeScript 7 → `bun check`） | 冷启动 70 秒→13 秒→5 秒内 | 可用。每次替换都要对比诊断结果，并在本仓库上跑基准 | `accelerate lint` |
| 4 | 一个 8 分钟测试目标拆成 6 个分片，用 8 vCPU 机器，每片独立数据库 | — | 免费 Linux Runner 固定 4 vCPU，只能调分片数；分片数按固定开销计算；每片用自己的 service container | `parallel`、`accelerate env` |
| 5 | Vitest 设 `isolate: false`，不再为每个测试文件重新加载整个应用 | 每片 100 秒→35 秒 | 需要加状态重置 Hook，可能让测试互相污染。属于改测试基础设施，用户同意后才做，并用多轮乱序运行证明稳定 | `accelerate test` |
| 6 | 修 setup：拉最近 150 次运行，把 Job 拆成等待、setup、执行三段 | 测试 Job 168 秒→74 秒 | 全部可用，见下方三条与缓存播种问题 | `accelerate cache/checkout/deps/test` |
| 6a | 缓存只写在 PR 范围，main 上没有播种，多数 PR 冷启动 | 半数测试 Job 未命中缓存 | 在默认分支 `push` 上写缓存，PR 只读 | `accelerate cache` |
| 6b | 缓存 `node_modules` | 恢复 13 秒，替代 33 秒安装 | 可用，key 必须精确，命中时跳过安装 | `accelerate cache`、`deps` |
| 6c | 用 blobless clone（`filter: blob:none`），不用 shallow | Checkout 36 秒→12 秒；shallow 会破坏读 git 历史的工具 | 可用 | `accelerate checkout` |
| 6d | 并发度匹配核数：4 vCPU 跑 8 个任务改为 4 个 | 速度不变，消除一个 flaky test | 可用 | `accelerate test` |
| 7 | Lint、Typecheck、Build、Test 全部并行；把最慢 Job 里的迁移检查等杂活拆出去 | 少 2 分钟 | 可用 | `organize`、`parallel` |
| 8 | `nx affected` 只测改动的项目，夜间在 main 跑全量；故意让 Nx 漏掉一个改动来测试跳过逻辑 | 六个分片全部跳过却报绿，改为让这种情况失败 | 可用，必须配全量兜底和跳过逻辑自检 | `parallel` |
| 9 | pre-push Hook 对改动文件跑 format、lint、typecheck，9 秒内完成；写进 Hook 而不是 AGENTS.md，因为 Agent 会跳步骤 | — | 本 Skill 不默认安装 Git Hook。CI Hook 提供 `quick` 任务，安装本地 Hook 需用户要求 | `init` |
| — | CI 账单从每月 230 美元涨到 4300 美元 | — | 不走这条路 | — |

另外两条结论同样适用：

- **删测试没用。** Agent 审计了 2 万个测试用例，几乎没有值得删的；时间本来就不在测试本身。本 Skill 不删测试。
- **Agent 会重试而不修根因。** 缓存缺失这个问题存在了一整年，因为 Agent 失败后只是重跑。`validate` 要检查重跑率和首跑失败率。

## 2. 开源项目实践（2026-10-31 核实）

### astral-sh/ruff：`.github/workflows/ci.yaml`

- `determine_changes` Job 按领域输出改动标记（`code`、`linter`、`formatter` 等），下游 Job 用 `if: needs.determine_changes.outputs.code == 'true' || github.ref == 'refs/heads/main'`：PR 按改动运行，main 始终全量。
- 需要历史时不用 `fetch-depth: 0`，而是先浅克隆，再运行 `git fetch --no-tags --filter=blob:none --unshallow origin`，注释写明这样更快。
- `Swatinem/rust-cache` 设 `save-if: ${{ github.ref == 'refs/heads/main' }}`：只在 main 写缓存，PR 读取。
- 注意：ruff 部分 Job 使用 larger runner 和 Depot。这里只借用它的编排和缓存做法。

### vitejs/vite：`.github/workflows/ci.yml`

- `changed` Job 用按 SHA 固定的 `tj-actions/changed-files` 计算 `should_skip`，测试 Job 用 `if: needs.changed.outputs.should_skip != 'true'` 在 Job 级跳过。
- 测试 Matrix 设 `fail-fast: false`，一次运行报告全部失败。
- 汇总 Job `test-passed` 用 `if: (!cancelled() && !failure())`、`runs-on: ubuntu-slim`，作为“测试通过或按预期跳过”的单一检查；另有 `test-failed` 在失败时报告。
- `concurrency.group` 为 `${{ github.workflow }}-${{ github.event.number || github.sha }}`，并开启 `cancel-in-progress`。

### 常用的免费 Action

| Action | 用途 | 当前版本 |
| --- | --- | --- |
| `re-actors/alls-green` | 汇总 `needs` 结果，支持 `allowed-skips`、`allowed-failures`，做唯一必需检查 | v1.3.0 |
| `dorny/paths-filter` | Job 级路径变更检测 | v4.0.3 |
| `Swatinem/rust-cache` | Rust 依赖与构建缓存，`save-if` 控制写入 | v2.9.3 |
| `mozilla-actions/sccache-action` | sccache 编译缓存，可用 GitHub 缓存作后端 | v0.0.11 |
| `rhysd/actionlint` | workflow 静态检查 | v1.7.12 |

第三方 Action 按 SHA 固定，并在注释里写版本号。
