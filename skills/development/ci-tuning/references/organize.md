# organize：重新组织任务

把现有 Job 整理成职责清楚的任务组：消除重复，只保留必要的依赖，把最慢 Job 里不属于它的工作拆出去。本模块只调整“哪些命令放在哪个 Job、Job 之间谁等谁”，不改命令本身。

## 1. 输入

- `workflow_audit.py` 的清单：每个 Job 的质量命令及分类、触发事件、`needs`、Matrix、重复项。
- `run_stats.py runs`：每个 Job 的 setup、执行时间，以及最常出现在关键路径末尾的 Job。
- CI Hook 的任务列表（已执行 `init` 时）。

## 2. 列任务清单

整理成一张表，作为分组依据：

| 任务 | 分类 | 命令 | 所在 workflow/Job | 触发事件 | 执行 P50/P95 | 依赖的产物 | 必需检查 |
| --- | --- | --- | --- | --- | --- | --- | --- |

分类使用 lint、format、typecheck、test（unit、integration、e2e 分开）、build，以及 security、docs、migration 等其他类。

## 3. 分组原则

1. **按环境需求和时长分组。** 需要同一套环境、同样依赖的任务放在一起；需要数据库等 service 的测试与纯单元测试分开。
2. **小任务合并。** 每个 Job 都要付固定开销：排队、Set up job、checkout、工具链、依赖恢复，用 `run_stats.py` 的 `queue` 加 `setup` 中位数估算，通常 20～60 秒。执行时间明显短于固定开销、又不在关键路径上的任务（format 检查、actionlint、拼写检查等）合并成一个 static Job。
3. **长 Job 拆开。** 混合多个分类的 Job（如先 lint 再 test 再 build）让关键路径变成各段之和；拆成并行 Job。拆分是否划算的判断见 `parallel.md` 第 2 节。
4. **把最慢 Job 的杂活挪走。** 最常最后完成的 Job 里，不属于它主要职责的步骤（迁移检查、其他应用的测试、文档生成）放到自己的 Job。Owen 的第一个测试分片还跑迁移检查和其他应用的测试，拆出去后少了 2 分钟。
5. **平台 Matrix 保持原样。** 项目声明支持的操作系统和运行时版本照常运行。把部分平台测试挪到 CD 或定时任务属于门禁调整，只作为方案交给用户决定。
6. **与平台无关的检查只在 Ubuntu 跑一次。** 格式化、多数 lint、TypeScript 类型检查、npm 和 Cargo 的依赖审计，结果不随操作系统变化。放进 macOS、Windows 的 Matrix 只是重复运行，还占用稀缺的 macOS 并发（Free 计划整个账号同时只能跑 5 个 macOS Job）。把它们移到一个 Ubuntu Job，或在 Matrix 中只让一个 Linux 组合执行这些步骤；检查名会变化，按第 6 节处理必需检查。
   会按平台条件编译或解析的检查例外：clippy、go vet、golangci-lint、staticcheck、mypy、pyright、pylint、govulncheck、pip-audit 在不同平台上可能得出不同结果，保持原样。想移时，先在 Ubuntu 上用目标平台参数运行（如 `GOOS=windows go vet ./...`、`mypy --platform win32`），结果一致再移。`workflow_audit.py` 的 `os-agnostic-off-linux` 会列出可以移的检查。

## 4. 去重

| 重复形式 | 处理 |
| --- | --- |
| 同一检查出现在两个 workflow，触发事件重叠 | 保留一份，触发事件取并集 |
| 同一提交同时触发 `push`（任意分支）和 `pull_request` | `push` 限定默认分支和发布分支，PR 由 `pull_request` 覆盖；确认 fork PR 和 `merge_group` 仍有检查 |
| 测试跑两遍（单元测试 Job 和覆盖率 Job 各跑一次） | 合并为一次运行同时产出覆盖率 |
| 多个 Job 各自构建同一产物 | 构建一次，用 artifact 分发；若重新构建比上传下载更快，就保持各自构建（先测量） |
| 每个 Job 重复写环境准备步骤 | 抽成共享 composite action（见 `init.md` 第 4 节） |

每处去重都要确认：保留的那份覆盖了原来所有触发事件、参数和严格级别。

## 5. 依赖关系

- `needs` 只用于真实的数据依赖（artifact、outputs）或有意的放行顺序（如部署等测试）。
- 为节省分钟数而设的“先 lint 再跑测试”在公开仓库没有意义，只会拉长等待时间，改为并行。例外：`queue_p95` 显示经常撞到并发上限时，先测量再决定。
- 用一个汇总 Job 作为唯一必需检查（见 `init.md` 第 5 节）。依赖失败的 Job 被跳过时不会阻止合并，所以汇总 Job 必须 `if: always()` 并检查所有 `needs` 的结果。

## 6. 检查名称与必需检查

- Job 的显示名称就是检查名，Matrix Job 的检查名带参数后缀。改名或拆分后原来的必需检查会一直 Pending。
- 迁移顺序：先加汇总 Job，并让它在一次运行中成功；由用户把必需检查切到汇总 Job；最后再重组其他 Job。
- 用 `compare.py coverage --required-from <owner>/<repo>:<分支>` 确认每个必需检查在改动后仍然会产生。

## 7. 输出

- 新旧分组对照表，以及新的 Job 关系（每层有哪些 Job）。
- workflow 修改，`compare.py coverage` 结果。
- 需要用户在仓库设置中执行的操作。
