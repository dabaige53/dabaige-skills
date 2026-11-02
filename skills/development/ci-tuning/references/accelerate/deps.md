# accelerate deps：依赖安装

依赖安装通常是 setup 中最大的一段。先确保缓存命中（`cache.md`），再减少每个 Job 实际安装的内容。

## 1. 测量

从 `run_stats.py` 取安装步骤在冷缓存和热缓存下的耗时；本地复现时清空缓存后计时。

## 2. 按 lockfile 安装

| 生态 | 命令 |
| --- | --- |
| npm | `npm ci --no-audit --no-fund` |
| pnpm | `pnpm install --frozen-lockfile --prefer-offline` |
| Yarn（Berry） | `yarn install --immutable` |
| Bun | `bun install --frozen-lockfile` |
| uv | `uv sync --locked` |
| Poetry | `poetry install --sync` |
| pip | 带哈希的 requirements；或改用 `uv pip install`（需验证解析结果一致） |
| Bundler | 配合 `ruby/setup-ruby` 的 `bundler-cache: true` |
| Go | `go mod download`，或交给 `setup-go` 的缓存 |
| Cargo | `cargo fetch --locked` |

lockfile 安装既能复现，又能跳过依赖解析。不按 lockfile 安装的 Job 可能装到与本地不同的版本，这本身就是质量问题。

## 3. 只装需要的部分

- monorepo：`pnpm install --filter <包>...`、`npm ci --workspace <包>`、`uv sync --package <包>`，前提是这个 Job 只检查这些包。
- Python 依赖组：lint Job 只装 lint 工具组（`uv sync --only-group lint` 等），测试 Job 装测试组。
- Playwright 只安装用到的浏览器：`npx playwright install --with-deps chromium`。
- 系统包：先查 runner-images 文档，镜像已预装的就不再 `apt-get install`；必须安装时加 `--no-install-recommends`，并且只在需要的 Job 安装。

## 4. 谨慎处理的选项

- `--ignore-scripts`：只有确认依赖不靠安装脚本下载二进制或生成文件时才用。
- 更换包管理器（npm 换 pnpm 或 Bun）是项目级决定，不属于 CI 调优，只作为建议提出。
- 不在 CI 中升级或改写 lockfile。

## 5. 完成条件

各 Job 冷、热缓存下的安装耗时下降，依赖版本与改动前一致（lockfile 未变），CI 全部通过。
