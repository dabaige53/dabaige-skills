# accelerate env：环境准备

覆盖工具链、工具安装、service container、Docker 和 Runner 选择。目标是缩短 Job 从“Set up job”到第一条检查命令之间的时间。

## 1. 工具链

- 版本从项目的版本文件读取（`node-version-file`、`python-version-file`、`go-version-file`），本地和 CI 保持一致。
- runner 镜像的 toolcache 已有的版本，setup Action 会直接使用；需要下载的版本，耗时会明显增加。可在镜像文档中查到预装版本。

## 2. 工具安装

`go install <模块>@<版本>`、`cargo install <crate>` 会在 Runner 上从源码编译工具，每次运行都重新编译一遍，常常要几十秒到几分钟。`workflow_audit.py` 的 `source-install` 会标出这类步骤。改为下载预编译版本：

| 方式 | 说明 |
| --- | --- |
| 工具的官方 Action | 如 `golangci/golangci-lint-action@v9`。golangci-lint 官方文档也不建议用 `go install` 安装 |
| `taiki-e/install-action@v2` | 覆盖 cargo-nextest、cargo-deny、cargo-hack、just、shellcheck 等常用工具，用 `tool: cargo-nextest@0.9` 这样的写法固定版本。清单外的工具默认回退到 cargo-binstall；只接受清单内的预编译文件时设 `fallback: none` |
| `cargo-bins/cargo-binstall` | 依次尝试 crate 仓库的 Release、第三方预编译站 quickinstall，最后才从源码编译；CI 中加 `--no-confirm` |
| 下载 GitHub Release | `gh release download <版本> --repo <owner/repo> --pattern '<文件名>'`，再用发布方提供的 checksum 校验。`gh` 已预装，Job 中需设 `GH_TOKEN: ${{ github.token }}` |
| Runner 镜像预装 | 先查 `actions/runner-images` 中对应镜像的软件清单。预装版本随镜像更新变化，需要固定版本时仍显式安装 |

- 工具版本固定，不用 `latest`。更换安装方式时保持同一版本：lint、format 工具换版本可能改变检查结果，换版本按 `lint.md` 的工具替换处理。
- 确实没有预编译版本时，把装好的二进制做缓存，key 包含工具名、版本、系统和架构，命中时跳过安装。

## 3. Service container

```yaml
services:
  postgres:
    image: postgres:17
    command: -c fsync=off -c synchronous_commit=off -c full_page_writes=off
    env:
      POSTGRES_PASSWORD: postgres
    ports:
      - 5432:5432
    options: >-
      --health-cmd "pg_isready -U postgres"
      --health-interval 2s
      --health-timeout 5s
      --health-retries 20
```

- 每个 Job 或分片使用自己的容器，互不干扰（Owen 的每个分片都有自己的数据库）。
- 关闭 fsync 等持久化选项只影响崩溃后的数据安全，CI 中的测试库可以接受。数据目录还可以用 `--tmpfs` 放进内存，挂载路径按所用镜像版本的数据目录填写。
- 健康检查间隔设短一些，避免容器早已就绪还在等待。
- 镜像用固定版本标签；换成更小的变体（如 alpine）前，确认排序规则、扩展等行为一致。
- 改用模板数据库、事务回滚等方式加速测试，属于测试基础设施改动，按 `test.md` 的规则处理。

## 4. Docker

- 构建镜像用 Buildx 的 GitHub 缓存后端：`cache-from: type=gha`、`cache-to: type=gha,mode=max`，它占用同一个 10 GB 缓存容量。
- Dockerfile 用多阶段构建，依赖层放在源码层之前，依赖下载用 `RUN --mount=type=cache`。层顺序的检查方法见 `build.md` 第 2 节。
- 不在 Job 里构建这个 Job 用不到的镜像。

## 5. 环境变量

按需设置：`NEXT_TELEMETRY_DISABLED=1`、`DO_NOT_TRACK=1`、`CARGO_INCREMENTAL=0`（CI 中增量编译产物只会增大缓存）、`PIP_DISABLE_PIP_VERSION_CHECK=1`。`NODE_OPTIONS=--max-old-space-size` 只在确实内存不足时才设置。

## 6. Runner 选择

| 标签 | 用途 |
| --- | --- |
| `ubuntu-24.04` / `ubuntu-latest` | 默认 |
| `ubuntu-24.04-arm` | 公开仓库同为 4 vCPU、16 GB。部分负载更快：确认工具链和依赖都有 arm64 版本后，对比实测再切换 |
| `ubuntu-slim` | 汇总 Job、变更检测等轻量任务；1 vCPU，15 分钟上限，不能运行 Docker |
| Windows、macOS | 只用于平台相关的测试和构建；macOS 在 Free 计划下最多同时 5 个 Job。与平台无关的检查移回 Ubuntu，见 `organize.md` 第 3 节 |

切换架构会改变检查实际运行的平台。与平台无关的检查（lint、format、多数 typecheck）可以换到 arm；运行时相关的测试和构建，项目以 x64 发布时保留 x64，arm 只能作为额外平台加入。

## 7. 完成条件

“Set up job”到第一条检查命令之间的耗时下降，测试结果与改动前一致。
