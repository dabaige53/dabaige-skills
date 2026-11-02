# GitHub 免费 CI 的平台事实

以下内容于 2026-10-31 按 GitHub 官方文档核实。数字会变，结论依赖某个数字时，先打开对应来源复核。

## 1. 标准托管 Runner（公开仓库）

公开仓库使用标准 GitHub-hosted runner 免费且不限分钟数。

| 系统 | CPU | 内存 | SSD | 架构 | 标签 |
| --- | --- | --- | --- | --- | --- |
| Linux（容器） | 1 | 5 GB | 14 GB | x64 | `ubuntu-slim` |
| Linux | 4 | 16 GB | 14 GB | x64 | `ubuntu-latest`、`ubuntu-24.04`、`ubuntu-22.04`、`ubuntu-26.04` |
| Linux | 4 | 16 GB | 14 GB | arm64 | `ubuntu-24.04-arm`、`ubuntu-22.04-arm`、`ubuntu-26.04-arm` |
| Windows | 4 | 16 GB | 14 GB | x64 | `windows-latest`、`windows-2025`、`windows-2025-vs2026`、`windows-2022` |
| Windows | 4 | 16 GB | 14 GB | arm64 | `windows-11-arm`、`windows-11-vs2026-arm` |
| macOS | 4 | 14 GB | 14 GB | Intel | `macos-15-intel`、`macos-26-intel` |
| macOS | 3（M1） | 7 GB | 14 GB | arm64 | `macos-latest`、`macos-14`、`macos-15`、`macos-26`、`xcode-27` |

- 私有仓库的同名标签规格更小，并按分钟计费。本 Skill 面向公开仓库，私有仓库需重新确认规格。
- `ubuntu-slim` 运行在非特权容器中：Job 超时上限 15 分钟，不支持 Docker-in-Docker、挂载文件系统等特权操作，预装工具很少。适合汇总 Job、变更检测、标签等轻量任务，不适合构建和测试。
- Linux 公开仓库只有 4 vCPU。Owen 文中“换 8 vCPU 机器”这条在免费方案中不可用，只能靠多 Job 并行和减少每个 Job 的固定开销。

## 2. 并发与执行上限

| 项 | 上限 |
| --- | --- |
| 同时运行的 Job（Free / Pro / Team / Enterprise） | 20 / 40 / 60 / 500 |
| 同时运行的 macOS Job（Free / Pro / Team / Enterprise） | 5 / 5 / 5 / 50 |
| 单个 workflow run 的 Matrix | 256 个 Job |
| 单个 Job 执行时间（GitHub 托管） | 6 小时 |
| workflow run 总时长 | 35 天 |
| concurrency group 排队（`queue: max`） | 100 个 |

- 并发上限按账号或组织计算，所有仓库、所有 PR 共用。Free 计划下一次 PR 展开 30 个 Job，至少 10 个要排队；几个 PR 同时推送时排队更多。
- 排队时间计入等待时间。用 `run_stats.py` 的 `queue_p95` 判断是否撞到上限。

## 3. 缓存

| 项 | 规则 |
| --- | --- |
| 容量 | 每仓库默认 10 GB；超出部分需绑定付款方式并计费，本 Skill 不使用 |
| 淘汰 | 7 天未访问的条目删除；超出容量时按最后访问时间从旧到新淘汰，可能出现缓存抖动 |
| 速率 | 每仓库每分钟上传 200 次、下载 1500 次，超出后失败直到重置 |
| 读取范围 | 当前分支和默认分支的缓存；PR 运行还能读 base 分支的缓存 |
| PR 写入范围 | PR 运行创建的缓存属于 `refs/pull/<n>/merge`，只有同一 PR 的重跑能恢复，其他 PR 和默认分支都用不到 |
| 默认分支写入 | 只有 `push`、`workflow_dispatch`、`repository_dispatch`、`delete`、`registry_package`、`page_build`、`schedule` 能写默认分支范围；`pull_request_target`、`issue_comment`、`workflow_run` 等默认只读 |
| `cache-mode` | workflow 或 Job 级键，取值 `read`、`write`、`write-only`、`none`，可把 PR Job 明确设为只读 |

推论：没有在默认分支上运行、写入同一份缓存的 workflow，每个新 PR 都从冷缓存开始。Owen 的团队就是这样，一年都没发现。

## 4. 必需检查与跳过

| 情况 | 结果 |
| --- | --- |
| workflow 因 `paths`、`branches` 过滤或提交信息被跳过 | 关联检查一直处于 Pending，阻止合并 |
| Job 因 `if` 条件被跳过 | 检查报告 Success |
| Job 因依赖的 Job 失败而被跳过 | 依赖它的检查被跳过，可能不阻止合并；聚合检查要配合 `always()` 与 `needs` |

- 成功状态包括 `success`、`skipped`、`neutral`。
- 只有过去 7 天内成功运行过的检查才能被选为必需检查。
- 结论：必需检查所在的 workflow 不要用 `paths` 过滤；按改动跳过放在 Job 级条件里，再用一个聚合 Job 作为唯一必需检查。

## 5. 并发控制

- `concurrency.group` 相同的 run 或 Job 互斥；`cancel-in-progress` 可写表达式，例如只在 `pull_request` 时取消旧运行。
- 默认每个 group 只保留一个 pending；`queue: max` 允许最多 100 个排队，不能与 `cancel-in-progress: true` 同时使用。

## 6. 官方 Action 当前主版本（2026-10-31）

| Action | 主版本 |
| --- | --- |
| `actions/checkout` | v7 |
| `actions/cache` | v6 |
| `actions/setup-node`、`actions/setup-python`、`actions/setup-go` | v7 |
| `actions/upload-artifact` / `actions/download-artifact` | v7 / v8 |
| `astral-sh/setup-uv` | v10 |
| `pnpm/action-setup` | v6 |
| `oven-sh/setup-bun` | v2 |

沿用项目现有的固定方式（SHA 加注释，或主版本标签）。写入前查最新版本：

```sh
gh api repos/actions/checkout/releases/latest --jq .tag_name
```

升级 Action 主版本不属于提速，除非它带来可测的收益或旧版本已经停用。

## 7. 不使用的付费选项

larger runner（自定义标签、`macos-*-large` 等）、第三方 Runner（Blacksmith、Depot、Namespace、BuildJet、WarpBuild、Ubicloud、RunsOn 等）、托管 CI（如 Vercel CI）、付费远程缓存、超过 10 GB 的缓存容量。项目已经在用的，保持原样并在报告中标注；本 Skill 不新增。

## 来源

- [GitHub-hosted runners reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [Actions limits](https://docs.github.com/en/actions/reference/limits)
- [Dependency caching reference](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
- [Troubleshooting required status checks](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks)
- [Workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)（`concurrency`、`cache-mode`、`services`）
