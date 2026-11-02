# accelerate build：构建

让构建只重做变化的部分，构建结果只生成一次。不改变构建产物本身。

## 1. 测量

构建步骤在冷缓存和热缓存下的耗时；哪些 Job 各自构建了同一份产物；构建工具自带的统计输出（如 Turborepo 的 cache hit 摘要、Gradle build scan 的本地报告）。

## 2. 连续构建检查

增量构建正常时：什么都没改再构建一次，几乎不花时间；只改一个源码文件，只有依赖它的部分重做。做不到这两点，CI 里的构建缓存也命中不了。这项检查在本地或临时工作树中完成，不需要推送。

1. 用 `git worktree add` 取一份干净的工作树，用 CI Hook 的构建命令（没有 CI Hook 时用 CI 中的构建命令）连续运行两次，记录耗时。
2. 在一个源码文件里加一行注释，再构建一次：安装依赖等无关步骤应当仍然命中缓存，只有依赖这个文件的部分重做。
3. 不符合预期时，用工具自带的方式找出被重做的部分：

| 工具 | 符合预期时 | 查原因 |
| --- | --- | --- |
| Make | `make -q <目标>` 返回 0 | `make --debug=b <目标>` 列出被判定为过期的目标 |
| Cargo | 只输出 `Finished` | `CARGO_LOG=cargo::core::compiler::fingerprint=info cargo build` 说明重新编译的原因 |
| TypeScript 项目引用 | 很快结束 | `tsc -b --verbose` 说明每个项目是否最新及原因 |
| Turborepo | `FULL TURBO` | 两次都加 `--summarize`，对比生成的摘要中各任务的输入哈希 |
| Nx | 全部任务从缓存读取 | 检查 `nx.json` 和项目配置中各任务的 inputs、outputs |
| Gradle | 任务均为 `UP-TO-DATE` 或 `FROM-CACHE` | `--info` 输出任务过期的原因 |
| Docker | 第二次每一步都是 `CACHED`；改源码后，安装依赖的步骤仍是 `CACHED` | 找第一个不是 `CACHED` 的步骤，看它前面的 `COPY` 复制了什么 |

4. 常见原因：
   - **Dockerfile 先复制整个仓库再装依赖。** 改任何源码文件都会让依赖层失效，第 2 步会暴露这个问题。改为先只复制依赖清单（`package.json` 和 lockfile、`go.mod` 和 `go.sum`、`Cargo.toml` 和 `Cargo.lock` 等），安装依赖，再复制源码；同时用 `.dockerignore` 排除 `.git`、`node_modules` 和构建产物。monorepo 要先复制每个工作区包的清单文件，否则依赖装不全。
   - **构建规则指向不存在的文件。** 输入或输出路径写错、文件已经删除，或 Make 目标名与它实际生成的文件不一致，工具每次都判断为过期。
   - **输入里有每次都变的值。** 时间戳、提交哈希、随机数、绝对路径写进生成的文件，或进入参与缓存哈希的环境变量。例如把 `GITHUB_SHA` 列入 Turborepo 的 `globalEnv`，每个提交都会让所有任务的缓存失效。
   - **生成步骤每次都改写文件。** 内容没变，重新写入也会更新修改时间，下游随之重建。改为内容变化时才写入。
   - **构建前无条件清理。** 构建脚本先执行 `clean` 或删除输出目录。

## 3. 增量缓存

| 工具 | 缓存位置 | 说明 |
| --- | --- | --- |
| Turborepo | `.turbo` 或 `--cache-dir` 指定的目录 | 用 `actions/cache` 保存，key 含 lockfile 与 `github.sha`，`restore-keys` 用前缀；只在默认分支写入 |
| Nx | `.nx/cache` | 同上 |
| Next.js | `.next/cache` | key 含 lockfile 与源码哈希 |
| TypeScript 项目引用 | `*.tsbuildinfo` 与输出目录 | `tsc -b` 增量构建 |
| webpack | `cache: { type: 'filesystem' }` 的缓存目录 | — |
| Gradle | `gradle/actions/setup-gradle` 自带 | 默认只在默认分支写入 |
| Rust | `Swatinem/rust-cache` 或 sccache（`mozilla-actions/sccache-action`，`SCCACHE_GHA_ENABLED=true`） | 设 `CARGO_INCREMENTAL=0` |
| C/C++ | ccache 或 sccache | 缓存目录放进 `actions/cache` |

增量缓存的写入规则同 `cache.md`：默认分支写，PR 读，用前缀恢复最近的一份。

远程缓存（Nx Cloud、Vercel Remote Cache、Bazel 远程缓存）只在项目已经免费使用时保留，本 Skill 不新增。

## 4. 构建一次，到处使用

- 多个 Job 需要同一份产物时，在一个 Job 中构建，用 `actions/upload-artifact` 上传，下游 `download-artifact`。
- 先比较“上传加下载”与“直接重新构建”的耗时；重新构建更快时，让各 Job 并行构建。
- 产物已经压缩（tar.gz、zip、二进制）时上传设 `compression-level: 0`。
- Rust 测试可用 `cargo nextest archive` 构建一次，分片 Job 解压后运行。

## 5. 只作为建议提出

以下会改变产物或构建行为，需用户决定：

- 更换打包工具（webpack 换 Rspack，Rollup 换 Rolldown 等），需要验证产物与运行行为一致。
- PR 检查中跳过压缩、sourcemap 等生产步骤。如果这样做，至少保留一个 Job 走完整的生产构建。
- 调整构建目标或编译选项。

## 6. 完成条件

构建 Job 在冷、热缓存下的耗时下降；本地连续构建时第二次接近零耗时，改一个源码文件只重做相关部分；产物与改动前一致（关键文件的哈希或体积对比），下游 Job 全部通过。
