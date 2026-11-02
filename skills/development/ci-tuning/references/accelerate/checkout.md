# accelerate checkout：代码拉取

`actions/checkout` 默认 `fetch-depth: 1`（浅克隆），大多数 Job 不用改。需要优化的是需要历史的 Job，以及仓库很大、带 LFS 或 submodule 的情况。用 `run_stats.py` 的步骤耗时找到 checkout 慢的 Job。

## 需要 git 历史时

读取历史的场景：按改动运行（merge-base、`nx affected`）、`git describe` 生成版本号、changelog、基于 blame 的工具。浅克隆会让这些工具出错或静默得出错误结果（Owen 的原话：shallow breaks anything that reads git history）。

| 做法 | 写法 | 说明 |
| --- | --- | --- |
| blobless 全历史 | `fetch-depth: 0` 加 `filter: blob:none` | 拉取全部提交和树，文件内容按需下载。Owen 的 checkout 从 36 秒降到 12 秒 |
| 先浅后补 | 默认浅克隆，再运行 `git fetch --no-tags --filter=blob:none --unshallow origin` | ruff 的做法，注释写明比 `fetch-depth: 0` 快 |
| 只取 base | `git fetch --no-tags --depth=<n> origin <base sha>` | 只需要 base 与 HEAD 的差异时 |

`filter: tree:0`（treeless）更小，但遍历历史的命令会频繁按需下载，通常更慢；只有实测更快时才用。

## 其他选项

- **标签**：`fetch-tags` 保持默认 `false`，只有生成版本号的 Job 才拉取标签。
- **sparse checkout**：只需要部分目录的 Job（文档、单个包）用 `sparse-checkout`。工具读取根目录配置（如 `package.json`、`tsconfig.json`、lint 配置）时，把这些文件一并列入。
- **LFS**：`lfs` 默认关闭；只在用到 LFS 文件的 Job 打开，并以 LFS 指针列表的哈希为 key 缓存 `.git/lfs`。
- **submodule**：只在需要的 Job 打开；能用 `submodules: true` 就不用 `recursive`。
- **凭据**：不需要推送的 Job 设 `persist-credentials: false`。这是安全设置，不影响速度。

## 完成条件

需要历史的 Job 结果与原来一致（例如 affected 计算出的项目列表相同），checkout 步骤耗时下降。
