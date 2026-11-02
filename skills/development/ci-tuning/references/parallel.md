# parallel：优化执行编排

PR 的等待时间等于最慢那条依赖链（关键路径）上各 Job 的排队、setup、执行时间之和。本模块缩短这条链：独立任务并行，长任务分片，依赖只留必要的，过期运行及时取消，按改动运行时保证不漏检查。

## 1. 测量

- `run_stats.py runs --event pull_request --limit 50 --json .ci-tuning/<日期>-before/runs.json`：
  - `commits`：同一提交全部检查完成的 wall-clock P50/P95，这是主要指标。
  - `critical_chains`：按 Job 的创建和完成时间推断的关键链，以及每条链出现的次数。
  - 每个 Job 的 `queue`、`setup`、`work`、`teardown` 的 P50/P95。
- `workflow_audit.py`：静态的 Job 层级、每次 PR 展开的 Job 数、Matrix 规模。

先看最常出现在链末尾的 Job，再看它前面的依赖。

## 2. 拆分是否划算

把一个 Job 拆成两个并行 Job：原耗时 `O + W1 + W2`，新耗时 `O + max(W1, W2)`，收益是 `min(W1, W2)`。`O` 是固定开销（排队、setup、收尾），代价是多占一个并发名额、多做一遍 setup。

- 只有原 Job 在关键路径上才有收益。
- 收益不到半分钟，或并发已经饱和（`queue_p95` 明显上升）时不拆；反过来，多个秒级小 Job 应合并（见 `organize.md`）。
- 先用 `accelerate` 降低 `O`，分片和拆分的收益才会充分体现。

## 3. 并发名额

- Free 计划整个账号同时只能跑 20 个 Job（macOS 5 个），所有仓库和 PR 共用，详见 `github-free-ci.md`。
- 估算：每次 PR 展开的 Job 数 × 常见的同时活跃 PR 数，应明显低于 20。超出时先取消过期运行、合并小 Job，再考虑减少分片。
- 改动后对比 `queue_p95`。排队变长说明并行度超出了名额。

## 4. 多 Job 并行与 Matrix

- 无数据依赖的任务组全部放在第一层（无 `needs`）。
- Matrix 用于真实维度（操作系统、运行时版本）和测试分片。
- 测试 Matrix 设 `fail-fast: false`，一次运行报告全部失败，开发者或 Agent 可以一轮修完。项目有意使用 `fail-fast: true` 时保留。
- `max-parallel` 只用于保护共享的外部资源。
- 动态 Matrix：先由一个计划 Job 输出 JSON（受影响的项目、分片列表），下游用 `fromJSON(needs.plan.outputs.matrix)`。单个 run 最多 256 个 Matrix Job。

## 5. 测试分片

| 工具 | 分片方式 | 是否按耗时均衡 | 报告 |
| --- | --- | --- | --- |
| Jest | `--shard=i/n` | 否，按文件分 | 每片输出 JUnit |
| Vitest | `--shard=i/n` | 否，按文件分 | `--reporter=blob`，最后用 `vitest --merge-reports` 合并 |
| Playwright | `--shard=i/n` | 按测试数平均 | blob 报告，`npx playwright merge-reports` 合并 |
| pytest | pytest-split：`--splits n --group i`，读取提交在仓库中的 `.test_durations` | 是 | 每片 `--junitxml` |
| pytest（进程内） | pytest-xdist `-n` | — | — |
| cargo-nextest | `--partition count:i/n` 或 `hash:i/n`；可先 `cargo nextest archive` 构建一次再分发 | 否 | nextest JUnit 配置 |
| Go | 无内置；`go list ./...` 拆包后分给各片 | 用 `shard_plan.py` 计划 | `gotestsum --junitfile` |

```yaml
test:
  strategy:
    fail-fast: false
    matrix:
      shard: [1, 2, 3, 4]
  steps:
    - uses: actions/checkout@v7
    - uses: ./.github/actions/setup
    - run: pnpm run ci:test -- --shard=${{ matrix.shard }}/${{ strategy.job-total }}
```

### 选分片数

1. 从基线运行的 JUnit 报告取每个文件的耗时（报告是 artifact 时用 `gh run download` 下载）。
2. `shard_plan.py --junit <报告> --overhead <每片固定开销秒数> --max-shards 12`，对比 1～12 片的预测耗时（固定开销 + 最长分片）。固定开销取该 Job 的 `queue + setup + teardown` 中位数。
3. 选收益开始变小的位置，不选理论最小值。最长的单个测试文件是下限，分片再多也无法低于它；拆这个文件属于改测试，交给用户决定。
4. Linux 免费 Runner 只有 4 vCPU，先让进程内并发匹配核数（`accelerate/test.md`），再增加分片。

### 不均衡时

内置分片按文件均分，文件耗时差异大时各片相差很多（最长片 / 平均片 > 1.3）。按耗时均衡的做法：

- pytest 用 pytest-split，durations 文件定期刷新；不在文件里的新测试会按平均耗时分配。
- Jest、Vitest 可配置自定义 sequencer 的 `shard` 方法读取耗时文件。这属于测试配置，不改测试内容。
- 其他工具可提交 `shard_plan.py` 生成的分片清单，CI Hook 按清单运行，并在运行前核对：所有测试文件都必须出现在某个清单里，否则失败或放进固定分片，绝不能静默漏跑。

### 分片的约束

- 每片使用自己的 service container（数据库等），不共享外部状态。
- 所有分片合起来必须正好是完整测试集：用 `compare.py tests` 对比改动前后的 JUnit 报告，确认没有遗漏和重复。
- 需要合并覆盖率或报告时，各片上传 artifact，在最后一个 Job 合并；项目没有覆盖率门禁时不加合并 Job，避免拉长关键路径。

## 6. DAG 与产物

- 下游需要构建产物（如 e2e）时：比较“构建一次，上传后由下游下载”和“下游各自构建”的耗时，选择更快的方案。
- 小数据用 Job `outputs`，文件用 artifact。已压缩的数据上传时设 `compression-level: 0`。
- lint、typecheck、单元测试不应依赖 build，除非确实读取构建产物。

## 7. 并发控制

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.sha }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
```

- PR 有新推送时取消旧运行，释放并发名额。
- 默认分支每个提交单独成组，不互相取消：这些运行负责写缓存，也是性能基线。
- 部署类需要依次执行的 workflow 用 `queue: max`，不能与取消同时使用。

## 8. 按改动运行

工具：`nx affected`、`turbo run <task> --affected`、`pnpm --filter "...[origin/main]"`、Bazel 或 Pants 的变更查询，或自建的“路径 → 项目”映射配合 `dorny/paths-filter`。

只有同时满足以下条件才能启用：

1. **在 Job 级决定。** 用 `changes` Job 输出标记，下游 Job 用 `if` 判断。必需检查所在的 workflow 不用 `paths` 过滤，否则未命中的 PR 会一直 Pending。
2. **有全量兜底。** 默认分支 `push`、merge queue（`merge_group`）、每晚定时任务跑全量。参考 ruff：`if: needs.changes.outputs.code == 'true' || github.ref == 'refs/heads/main'`。
3. **全局文件触发全量。** lockfile、CI 配置、根配置（tsconfig、lint 配置）、共享包、工具链版本变化时全量运行。
4. **未知即全量。** 改动的文件不属于任何已知项目时，运行全部检查。
5. **测试跳过逻辑本身。** 准备一个映射会漏掉的改动（或在测试分支修改一个全局文件），确认结果是全量运行或失败，而不是“零测试、全绿”。Owen 就遇到过六个分片全部跳过却报绿。运行时加保护：有源码改动但选中的测试为空时，失败或改为全量。不要用 `--passWithNoTests` 让空选择通过。
6. **汇总检查区分预期跳过。** Job 被 `if` 跳过时报告 Success，所以汇总 Job 只允许由 `changes` 输出决定的跳过（`alls-green` 的 `allowed-skips`）。

计算差异需要 base 提交：PR 用 `github.event.pull_request.base.sha` 或 merge-base。需要历史时用 blobless 拉取（`accelerate/checkout.md`）。

## 9. 完成条件

- 新的 Job 关系图、预测的关键路径和实际测得的关键路径。
- `compare.py coverage` 无丢失；引入分片时 `compare.py tests` 确认测试集合完整。
- 引入按改动运行时，跳过逻辑自检的结果。
- 按 `validate.md` 采集改动后的运行数据，用 `compare.py timing` 对比。
