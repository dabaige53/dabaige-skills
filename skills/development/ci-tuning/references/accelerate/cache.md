# accelerate cache：缓存

缓存是否生效看两点：PR 能否读到默认分支写好的缓存，key 是否只在内容变化时才变。缓存规则见 `github-free-ci.md` 第 3 节。

## 1. 测量

- `run_stats.py caches`：每个 key 族在默认分支上有没有条目、PR 条目占用的容量、总容量离 10 GB 多远、默认分支上 key 变化是否过于频繁。
- `run_stats.py runs --logs 30`：从日志统计每个 Job 的精确命中、前缀命中和未命中。
- 同一个 Job 每次都是前缀命中：key 里带有每次运行都会变的值（如 run_id），每次都另存一份新缓存。这种 key 也可能藏在第三方 Action 内部，只能从日志看出来。
- 每个 Job 的 setup 时间：恢复缓存加安装依赖的步骤耗时。

Owen 的团队拉取了 150 次运行，发现半数测试 Job 没有命中依赖缓存：PR 的缓存只属于该 PR，默认分支上没有任何运行写过这份缓存，所以大多数 PR 都是冷启动。

## 2. 在默认分支播种

- 每个会产生缓存的 Job，都要有一个在默认分支 `push`（或 `schedule`、`workflow_dispatch`）时运行的版本，并写入同一个 key。
- 只在 `pull_request` 上运行的 workflow，写出的缓存别的 PR 用不到。`workflow_audit.py` 的 `pr-only-cache` 会标出这类情况。
- 默认分支上的运行不要被 `cancel-in-progress` 取消，否则缓存可能没写完。

## 3. 默认分支写，PR 只读

PR 写出的缓存只能被同一 PR 重跑恢复，却占用 10 GB 容量，还可能把默认分支的缓存挤出去。做法：

```yaml
- uses: actions/cache/restore@v6
  id: deps
  with:
    path: node_modules
    key: node-modules-${{ runner.os }}-${{ runner.arch }}-node${{ steps.node.outputs.node-version }}-${{ hashFiles('pnpm-lock.yaml') }}
- if: steps.deps.outputs.cache-hit != 'true'
  run: pnpm install --frozen-lockfile
- if: steps.deps.outputs.cache-hit != 'true' && github.ref == format('refs/heads/{0}', github.event.repository.default_branch)
  uses: actions/cache/save@v6
  with:
    path: node_modules
    key: ${{ steps.deps.outputs.cache-primary-key }}
```

- 自带缓存的 Action 用它自己的写入开关，例如 `Swatinem/rust-cache` 的 `save-if: ${{ github.ref == 'refs/heads/main' }}`。
- 只在 PR 上运行的 workflow 可以在 workflow 或 Job 级写 `cache-mode: read`。
- 同一个 key 只让一个 Job 写入，其他 Job 只读；多个 Job 同时写同一个 key 会浪费上传额度（每仓库每分钟 200 次）。

## 4. Key 设计

- 依赖类：`<名称>-${{ runner.os }}-${{ runner.arch }}-<工具链版本>-${{ hashFiles('<lockfile>') }}`，只用精确匹配。
- 增量类（构建缓存、ESLint 缓存、mypy 缓存、sccache）：主 key 带内容哈希，`restore-keys` 用前缀恢复最近的一份；工具自己会校验缓存是否可用。
- 依赖缓存的主 key 不要带 `github.sha`、`run_id`，否则永远不命中。
- monorepo 用整个仓库的 lockfile 哈希，所有 Job 共用一份依赖缓存。

## 5. 缓存什么

| 缓存 | 说明 |
| --- | --- |
| 包管理器 store（npm、pnpm、yarn、pip、uv、Maven、Gradle、Cargo registry、Go module） | 优先用 setup Action 自带的缓存：`setup-node` 的 `cache`、`setup-python` 的 `cache`、`setup-go` 默认开启、`setup-java` 的 `cache`、`ruby/setup-ruby` 的 `bundler-cache`、`astral-sh/setup-uv` 的 `enable-cache` |
| `node_modules` | 见第 6 节 |
| 工具链和浏览器 | 运行镜像未预装的工具；Playwright 浏览器（`~/.cache/ms-playwright`，key 含 Playwright 版本） |
| 构建缓存 | Turborepo `.turbo`、Nx `.nx/cache`、Next.js `.next/cache`、Gradle 构建缓存、Rust `target`（`Swatinem/rust-cache`）、sccache |
| 检查工具缓存 | `.eslintcache`、Prettier 缓存、`.mypy_cache`、`.tsbuildinfo` |

不缓存：整个工作区、`.git`、发布用的构建产物（用 artifact）、任何含凭据的目录。

每个 Job 只恢复自己用得上的缓存：只构建前端的 Job 不恢复 Rust 的 `target` 和 Cargo registry，只跑 lint 的 Job 不恢复 Playwright 浏览器。共用的 setup composite action 用输入参数决定恢复哪些缓存，不要一律全部恢复。检查方法：在 Job 日志中搜索 `Cache hit for` 和 `Cache Size`，看恢复了哪些缓存、各多大，再对照这个 Job 实际执行的命令。

## 6. `node_modules` 还是 store

Owen 缓存 `node_modules`：恢复用 13 秒，替代 33 秒的安装。判断方法：

1. 分别测量“热 store 下安装”和“恢复 `node_modules` 压缩包”的耗时。
2. 恢复明显更快，并且安装过程没有向 `node_modules` 以外写入必要文件（postinstall 下载二进制、生成代码等），才缓存 `node_modules`。
3. key 必须精确包含操作系统、架构、Node 版本、包管理器版本、lockfile 哈希；不使用 `restore-keys`，精确命中时跳过安装。
4. monorepo 要包含各工作区包的 `node_modules`。

否则缓存 store，由 setup Action 管理。

## 7. 容量

- 默认分支上的缓存总量保持在 8 GB 以下，给 PR 重跑留余量。
- 缓存总量接近 10 GB 时，先去掉 PR 写入，再合并重复的 key 族，最后减少缓存内容。
- 可选：在 `pull_request` 的 `closed` 事件上删除该 PR 的缓存（`gh cache delete`）。

## 8. 完成条件

- `run_stats.py caches` 显示每个 key 族在默认分支上都有条目。
- lockfile 未变的 PR 运行，日志中是精确命中，setup 时间相应下降。
- 缓存总量稳定，没有出现抖动。
