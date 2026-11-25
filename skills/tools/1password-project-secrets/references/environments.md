# Environment 管理与本机挂载

## 官方工具与连接


本机 macOS 程序路径可用 `/Applications/1Password.app/Contents/MacOS/1password-mcp`；其他系统发现实际可用路径。核对官方工具 schema，参数通常为 `accountId`、`environmentId`、`mountPath`，不根据旧文档推断返回字段。

1. 无可复用账号上下文时调用 `authenticate`，取得账号 ID；不为每个变量重新认证。
2. `list_environments` 解析目标，复用服务返回的 ID。存在多个无法区分的目标时只问关键选择。
3. `list_variables` 检查名称；只读请求到此结束。
4. 已授权创建或改名时使用 `create_environment`、`rename_environment`。
5. 已授权变量迁移或更新时使用 `append_variables`。结构化 schema 支持时，敏感字段 `concealed: true`；非敏感配置才使用 false。若 schema 为字符串列表，先读服务文档确定格式。
6. 创建前使用 `list_local_env_files` 核对挂载；使用 `create_local_env_file` 和绝对路径。普通文件占用该路径时先保留原配置并选专用路径，不直接覆盖。
7. 回读变量名及挂载元数据确认结果。遇到未知结果先回读，不盲目重建。

服务资源为 `1password://docs/getting-started`、`1password://docs/environments-guide`，可用时读取。MCP 不返回已有变量值；保存原值核对和实际加载验证在本地进程内完成，只输出布尔结果。原值转移不得把真实值嵌入模型可见的 MCP 参数；优先复用经过验证的本地迁移工具，或让用户在桌面应用导入。私有工具 stderr 同样需要捕获和清理。

## FIFO 加载合同

挂载是 UNIX 命名管道，不是普通文件。目前支持 macOS/Linux，每台设备最多 10 个启用挂载；创建前检查容量。挂载置于仓库外的本机私有目录，例如 `~/.local/share/project-credentials/<project>/<environment>/env`；仅本机包装器知道此路径。项目源码、Docker 上下文和仓库文档不记录挂载或工具信息。

首次访问需要授权，授权保持到 1Password 锁定；锁定后再次授权。MCP 连接和 Environment 访问也可能分别授权。不要承诺永久白名单或完全免授权。重复失败时说明具体等待哪种提示，完成后续接，不逐条调用 CLI。

仓库外的本机私有启动包装器按以下合同加载：

- 帮助、版本、静态配置检查在读取之前返回。
- 检查挂载确为 FIFO；单进程读取一次，内存解析后注入目标子进程。避免编辑器持续打开、并发读取和监听触发重启。
- 真实父进程环境优先；挂载值覆盖本机私有引用配置；项目只接收已解析的通用环境变量，保留非敏感配置和原有环境约定。
- 挂载存在但读取失败、空值或缺必需变量时明确失败，避免自动改走 CLI 再弹授权。仅挂载不存在且有已验证回退方案时使用 `op run`。
- 使用有界读取和不含值的错误消息。解析器警告可能打印输入，捕获 stdout/stderr 后只报告失败位置和变量名。
- 多行 JSON、换行、引号及转义需用虚构凭据验证。不要未经验证用 shell source、简单逐行切分或 `uv --env-file` 加载复杂内容。
- Python 优先显式打开流并 `dotenv_values(stream=stream, interpolate=False)`；旧 python-dotenv 按路径检测可能跳过 FIFO，官方路径支持从 1.1.2 起。Node 核对当前版本支持的 dotenv 解析器。避免展开值中的 `$`。
- 挂载位于项目监听范围外，让本机包装器先读取再启动 Vite 等工具。Compose 需核对宿主环境如何传入容器，禁止输出展开后的配置。

## 验证

先用 MCP 元数据和文件类型确认挂载存在；需要验证运行时读取时，通过项目实际入口读取一次，捕获输出，只报告变量是否解析。在内存将迁移前后值逐字段比较；挂载刚更新可能尚未同步，有限重试后明确失败。

验证秘密加载入口、非秘密帮助路径、多行解析、进程环境优先级和缺变量失败。连接数据库/API 是独立验收，未执行就标记未验证。移除本地明文前检查所有旧入口，保留未迁移消费者的必要配置并列出原因。

## 来源与维护

融合自官方 1Password 插件 `1password-environments` 0.2.0（MIT），保留全局 CLI 默认选择，并加入本机挂载接入经验。官方插件缓存由插件更新维护；在全局 skill 配置中停用重复入口，维护本全局 skill，不修改官方缓存文件。

- [官方 MCP 工具与授权](https://www.1password.dev/environments/mcp-server)
- [本地挂载、授权期限与兼容性](https://www.1password.dev/environments/local-env-file)

工具能力、平台限制和版本条件改变时重新核对官方文档与当前 schema。
