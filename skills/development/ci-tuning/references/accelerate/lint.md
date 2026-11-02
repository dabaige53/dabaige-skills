# accelerate lint：Lint、Formatter、Typechecker

覆盖 `lint`、`format`、`typecheck` 三类静态检查。先做不改规则的提速，再考虑换工具；换工具必须先证明规则等价。

## 1. 测量

- 从 `run_stats.py` 的步骤耗时，或本地 `time <Hook 任务>`，取得每个工具的耗时。
- ESLint 用 `TIMING=1 npx eslint .` 找出最慢的规则（常见：typescript-eslint 的类型感知规则、`import/no-cycle`）。
- 记录检查范围（文件数、是否类型感知）和工具版本。

## 2. 不改规则的提速

| 工具 | 做法 |
| --- | --- |
| ESLint | `--cache --cache-strategy content --cache-location .eslintcache`，缓存文件用 `actions/cache` 保存，key 含 lockfile 与配置文件哈希，允许 `restore-keys` 前缀匹配；类型感知规则改用 typescript-eslint 的 `projectService` |
| ESLint 多线程 | `--concurrency <线程数>` 或 `--concurrency auto`，默认关闭。类型感知规则在每个线程里都要加载一遍项目，开了未必更快；在 CI 中分别实测关闭、2、4、`auto`，取最快的一档 |
| Prettier | `--check --cache`（默认缓存位于 `node_modules/.cache/prettier`） |
| tsc | `--incremental` 或 `tsc -b`，缓存 `.tsbuildinfo` |
| mypy | 缓存 `.mypy_cache`，key 含 Python 版本、lockfile 与配置；mypy 会校验缓存，允许前缀恢复 |
| golangci-lint | 官方 Action 自带缓存；只在 Go 版本或配置变化时冷启动 |
| clippy | 与构建共用 `Swatinem/rust-cache` |

`skipLibCheck` 等会减少检查范围的选项属于门禁调整，不在这里启用。

## 3. 替换为更快的工具

| 原工具 | 候选 | 迁移辅助 |
| --- | --- | --- |
| ESLint | Oxlint（未覆盖的规则继续由 ESLint 检查） | `npx @oxlint/migrate` 由 flat config 生成 `.oxlintrc.json`；`eslint-plugin-oxlint` 在 ESLint 中关闭 Oxlint 已覆盖的规则 |
| ESLint + Prettier | Biome | `biome migrate eslint --write`、`biome migrate prettier --write` |
| flake8、isort、pyupgrade、部分 pylint | Ruff | 按插件对照 Ruff 规则码 |
| Black | `ruff format` | — |
| tsc | TypeScript 7（`tsgo`）、`bun check`、`tsrs`，见下表 | 以各工具的兼容性说明为准 |
| mypy | pyright、basedpyright、ty、pyrefly | 语义不同，很少能直接替换 |

Owen 的团队 Lint 从 2 分钟降到 5 秒，冷启动类型检查从 70 秒降到 5 秒以内。是否值得替换，取决于该检查是否在关键路径上、在本仓库实测能省多少。

### TypeScript 类型检查器

| 工具 | 用法 | 注意 |
| --- | --- | --- |
| TypeScript 7（`tsgo`） | 官方原生实现，多核检查 | 以官方兼容性说明为准 |
| `bun check` | Bun 自带的检查器，读同一份 `tsconfig.json`，报错与 TypeScript 7 一致，用满所有核。`tsc --noEmit` 换成 `bun check`，`tsc -b` 换成 `bun check -b`；CI 中用 `oven-sh/setup-bun@v2` 安装 | 只检查，不生成文件；需要 `.d.ts` 时保留 tsc。不论项目装的是哪个 TypeScript 版本，都按 TypeScript 7 的默认值检查（默认开启 `strict`、`types` 默认为空、移除了旧选项），从 TypeScript 5 迁移会出现新报错，这属于门禁变化，交用户决定。项目不在 Bun 上运行时，先实测能否直接使用 |
| `tsrs` | Oxc 团队用 Rust 实现的 TypeScript 7 检查器，`tsrs --noEmit --fast` | 2026 年 10 月发布，尚未稳定，官方列有已知差异。先用于本地加速；进入 CI 前按下方等价验证 |

Owen 的服务端冷启动类型检查：tsc 70 秒，TypeScript 7 13 秒，CI 中的 `bun check` 不到 5 秒，本地 `tsrs` 0.6 秒。

### 等价验证（必须）

1. **规则映射**：用迁移工具生成新配置，列出没有对应规则的旧规则。
2. **诊断对比**：在同一代码树上运行新旧工具，把结果统一成 `文件:行:规则`，再比较两边集合。范围包括：当前默认分支，以及两三个在 CI 中真实出现过 lint 或类型错误的历史提交（从 `run_stats.py` 的失败记录中找）。凡是映射过的规则，旧工具报出的问题新工具都要报出。
3. **未覆盖的规则**：保留旧工具，只跑这些规则。例如先跑 Oxlint，再跑关闭了重叠规则的 ESLint，整体仍然更快。
4. **Formatter 替换**：会改变输出格式。先统计 `--check` 会改动的文件数，一次性格式化提交需用户同意。
5. **Typechecker 替换**：比较全项目诊断的数量和错误码，以及已知有错的历史提交的结果。构建依赖 `tsc` 生成声明文件时，声明生成仍用 `tsc`。
6. **固定版本**：新工具写入 lockfile，避免版本漂移带来新的诊断。

新工具多报出的问题，修复后再合入，或由用户决定是否接受。“规则全开”会提高门禁，应作为单独的建议提出。

## 4. 只检查改动文件

只用于本地 `quick` 任务。跨文件的规则（循环依赖、类型感知规则）只检查改动文件会漏报，所以 CI 门禁仍检查完整范围。

## 5. 完成条件

- 该 Job 改动前后的耗时（冷缓存和热缓存各一次）。
- 替换工具时附上等价验证结果。
- `compare.py coverage` 中的工具替换已标记，CI 全部通过。
