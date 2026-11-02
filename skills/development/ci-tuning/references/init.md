# init：建立 CI 工程规范

产出四样东西：统一 CI Hook、共享的环境准备入口、CI.md、写进 workflow 的基础约定。目标是本地和 CI 跑同一套命令，后续 `organize`、`parallel`、`accelerate` 只调整编排，不再改检查本身。

## 1. 盘点

1. 运行 `workflow_audit.py <项目根> --json .ci-tuning/<日期>-before/audit.json`，得到各 workflow 的触发事件、Job、质量命令和重复项。
2. 找出项目已有的任务入口：`package.json` scripts、`Makefile`、`justfile`、`Taskfile.yml`、`noxfile.py`/`tox.ini`、`pyproject.toml` 中的任务（poe、hatch scripts）、`cargo xtask` 或 `.cargo/config.toml` alias、`magefile.go`、`composer.json` scripts、`Rakefile`、Gradle/Maven 任务。
3. 找出版本来源：`.nvmrc`、`.node-version`、`.python-version`、`.tool-versions`、`mise.toml`、`rust-toolchain.toml`、`go.mod` 的 `toolchain`、`packageManager` 字段。
4. 对照 workflow 里的 `run` 与任务入口：哪些检查只写在 YAML 里、哪些本地命令和 CI 命令参数不同（严格级别、路径、`--max-warnings` 等）。
5. 读取必需检查：`gh api repos/<o>/<r>/rules/branches/<默认分支>`（ruleset），以及有权限时的 `gh api repos/<o>/<r>/branches/<默认分支>/protection/required_status_checks`。

## 2. 选择 CI Hook 形式

优先沿用项目已有的任务入口，不为此引入新工具。

| 项目 | CI Hook 形式 |
| --- | --- |
| JS/TS 单包 | `package.json` 的 `ci:lint`、`ci:typecheck`、`ci:test`、`ci:build`、`ci:quick` |
| JS/TS monorepo（Turborepo、Nx） | 同上，脚本内部调用 `turbo run <task>` 或 `nx run-many -t <task>`，按改动运行时换成 affected 形式 |
| Python | 已有 nox、tox、poe、Makefile 时沿用；没有时加 `scripts/ci.sh`，内部用 `uv run` 等项目已有命令 |
| Go | `Makefile` 的 `ci-lint`、`ci-test` 等目标 |
| Rust | 已有 `cargo xtask` 或 justfile 时沿用；否则 `Makefile` 或 `scripts/ci.sh` |
| JVM | 沿用 Gradle/Maven 任务（如 `./gradlew check`），只补齐缺失的聚合任务 |
| 多语言 | `scripts/ci.sh <task>` 分发到各语言命令 |

分发脚本用 `case` 分支，每个任务一个分支，`workflow_audit.py` 能据此识别任务内容：

```sh
#!/usr/bin/env bash
set -euo pipefail
task="${1:-}"
shift || true
case "$task" in
  lint)      uv run ruff check . ;;
  format)    uv run ruff format --check . ;;
  typecheck) uv run mypy src ;;
  test)      uv run pytest "$@" ;;
  build)     uv build ;;
  all)       for t in format lint typecheck test build; do "$0" "$t"; done ;;
  *)         echo "usage: $0 {lint|format|typecheck|test|build|all} [args]" >&2; exit 2 ;;
esac
```

## 3. CI Hook 约定

- **任务名稳定**：`lint`、`format`（检查模式）、`typecheck`、`test`、`build`、`quick`、`all`，按项目习惯加前缀（`ci:lint`、`ci-lint`）。
- **`test` 透传参数**：`test` 接受额外参数（分片参数、文件列表），`parallel` 模块的分片直接复用。
- **CI 与本地同一命令**：严格级别（`--max-warnings=0`、`--strict`、`-D warnings` 等）写在 Hook 里，不在 YAML 里另加。差异只通过环境变量（如 `CI=true`）表达。
- **不在 Hook 里装依赖**：安装放在 workflow 的环境准备步骤，便于缓存；本地需要时另设 `setup` 任务。
- **非交互、失败即非零退出**：CI 中只检查不修复（formatter 用检查模式）。
- **`quick` 只服务本地**：对改动文件跑 format、lint、typecheck，目标几秒内完成。

## 4. 共享环境准备

多个 Job 重复的 checkout 之后的步骤（工具链、包管理器、依赖安装、缓存）抽成本地 composite action，例如 `.github/actions/setup/action.yml`：

```yaml
name: Setup
description: Toolchain and dependencies for CI jobs
runs:
  using: composite
  steps:
    - uses: pnpm/action-setup@v6
    - uses: actions/setup-node@v7
      with:
        node-version-file: .nvmrc
        cache: pnpm
    - run: pnpm install --frozen-lockfile
      shell: bash
```

Job 只保留 checkout、setup 和一行 Hook 调用：

```yaml
jobs:
  lint:
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v7
      - uses: ./.github/actions/setup
      - run: pnpm run ci:lint
```

缓存的写入策略（默认分支写、PR 读）由 `accelerate cache` 决定；init 阶段保留项目原有的缓存配置。

## 5. 基础约定

写进 workflow，并记录在 CI.md：

- **唯一必需检查**：加一个汇总 Job（如 `ci-ok`）`needs` 所有检查 Job，`if: always()`；有失败或取消时失败，只允许事先声明的跳过。之后重组 Job 不用再改分支保护。把必需检查切到汇总 Job 是仓库设置，由用户操作。

  ```yaml
  ci-ok:
    if: always()
    needs: [changes, lint, typecheck, test, build]
    runs-on: ubuntu-slim
    steps:
      - uses: re-actors/alls-green@<SHA> # v1.3.0
        with:
          jobs: ${{ toJSON(needs) }}
          allowed-skips: ${{ needs.changes.outputs.code != 'true' && 'test, build' || '' }}
  ```

- **Job id 和名称稳定**：名称就是检查名，改名会让必需检查一直 Pending。
- **并发控制**：PR 新推送取消旧运行，默认分支不取消：

  ```yaml
  concurrency:
    group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.sha }}
    cancel-in-progress: ${{ github.event_name == 'pull_request' }}
  ```

- **超时**：每个 Job 设 `timeout-minutes`，取历史 P95 的 2～3 倍。
- **权限**：workflow 级 `permissions: contents: read`，个别 Job 按需提升。
- **Runner**：只用标准托管 Runner；`ubuntu-latest` 还是固定版本，沿用项目习惯。
- **新增检查**：先加到 CI Hook，再放进对应 Job 组，然后更新 CI.md，最后运行 `$ci-tuning validate`。

## 6. CI.md

放在项目根目录或现有文档目录，使用项目文档的语言。只写与实际一致的内容；没有的章节不写。

```markdown
# CI

检查入口：`<CI Hook>`。本地与 CI 运行同一命令。只使用 GitHub 标准托管 Runner。必需检查：`ci-ok`。

## 任务

| 任务 | 命令 | CI Job | 触发 | P50 |
| --- | --- | --- | --- | --- |
| lint | `pnpm run ci:lint` | static | PR、main | 40 s |

## Job 关系

`ci.yml`：changes → static、typecheck、test（4 片）、build → ci-ok

## 触发与按改动运行

PR 按改动运行；main 和每晚定时任务跑全量。lockfile、CI 配置、根配置变化时全量。

## 缓存

| 缓存 | key | 写入 | 读取 |
| --- | --- | --- | --- |
| pnpm store | OS、Node 版本、lockfile 哈希 | main push | 全部 |

## 并发

PR 新推送取消旧运行；main 每个提交单独运行。

## 性能基线

| 日期 | 样本 | 提交级 P50 / P95 | 关键路径 |
| --- | --- | --- | --- |

## 修改检查

1. 在 CI Hook 中增改任务。2. 放进对应 Job。3. 更新本文。4. 运行 `$ci-tuning validate`。

## 本地检查

`pnpm run ci:quick`。需要 pre-push Hook 时自行启用：`<命令>`。
```

## 7. 本地 Git Hook

不默认安装。CI.md 写明 `quick` 任务和可选的启用方式（项目已在用 husky、lefthook、pre-commit 时沿用；否则给出 `git config core.hooksPath` 方案）。只有用户明确要求时才安装。

## 8. 完成条件

- 本地能运行 Hook 的快速任务（至少 `lint`、`format`，可行时加 `typecheck`）；耗时长的任务交给 CI 验证。
- 所有检查 Job 都通过 Hook 调用，`compare.py coverage` 显示没有检查丢失。
- 推送到分支后 CI 全部通过（推送前征得用户同意）。
- CI.md 与 workflow 一致。
