# accelerate test：测试执行

只调整测试怎么跑（进程并发、运行配置、报告输出）。测试分片见 `parallel.md`。

## 1. 并发度匹配核数

Linux 公开仓库的 Runner 是 4 vCPU（Job 中运行 `nproc` 确认）。Owen 的 4 vCPU Job 原来同时跑 8 个任务，减半后速度不变，还消除了一个 flaky test。

| 工具 | 设置 |
| --- | --- |
| Jest | `--maxWorkers=4` 或百分比 |
| Vitest | `--maxWorkers` / 配置中的 `maxWorkers` |
| pytest-xdist | `-n 4` 或 `-n auto` |
| Go | `go test -p 4`；包内并行由 `-parallel` 控制 |
| cargo-nextest | `--test-threads` |
| Playwright | `workers`，同时考虑内存 |

在 CI 中试 2～3 个取值，各跑几次，取总耗时最短且稳定的那个。超过核数通常只会更慢，还会放大时序相关的 flaky。发现 flaky test 时报告出来，交给用户决定修复方式。

## 2. 加载开销

Owen 的每个分片 100 秒里大部分花在加载模块上：Vitest 默认给每个测试文件一个全新环境，每个文件都要重新导入整个 NestJS 应用。设 `isolate: false` 后，每个分片从 100 秒降到 35 秒。

这类改动（关闭隔离、更换 pool、复用进程）会让测试之间共享状态，必须先补齐状态重置，属于测试基础设施改动：

1. 先给出证据：分片耗时中模块加载占多少（测试框架的耗时报告，或对比单个文件的空跑耗时）。
2. 征得用户同意后，再改配置并加每个文件结束后的状态重置 Hook，同时写明测试必须自行清理的内容。
3. 验证：完整套件连续运行至少 3 次，并用随机顺序运行（如 `vitest --sequence.shuffle`）；所有分片结果与改动前一致，没有新失败。
4. 合入后的一周内用 `run_stats.py` 观察首跑失败率和 flaky 运行。明显上升时先对同一提交重跑确认，确属新增 flaky 就回退。

## 3. 报告输出

在 CI 中输出 JUnit XML（jest-junit、Vitest `junit` reporter、`pytest --junitxml`、`gotestsum --junitfile`、nextest JUnit 配置），并作为 artifact 上传。`shard_plan.py` 和 `compare.py tests` 都依赖它。增加 reporter 不改变测试行为。

## 4. 完成条件

测试 Job 的执行时间下降，`compare.py tests` 显示测试集合与结果一致，flaky 运行没有增加。
