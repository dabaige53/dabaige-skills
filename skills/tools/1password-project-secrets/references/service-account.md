# 本机认证与映射

## 运行入口

`project-run` 位于 `~/.local/bin/project-run`，调用仓库外 `~/.local/share/1password-local/project-run.py`。PATH 缺失时使用入口绝对路径。参数为 `<项目目录名> -- <原命令>`；项目名称、根目录、条目与字段 ID 来自同目录 `projects.json`，仅已验证映射可运行。

入口读取所需业务字段，在内存注入原进程环境再执行项目命令；已有真实进程变量优先，应用不继承认证 Token。同一任务连续运行需凭据命令时，复用同一父进程的环境。具体用法和当前未完成项按需读该私有目录的 `README.md`、`migration-status.json`，不把快照视为实时运行结果。

## 认证与故障

管理条目使用私有 `op-service-account.py <op 参数>`。Token 在同目录 `service-account-token`，文件 0600、目录 0700；不输出值、不写进技能或仓库。当前账号和保险库元数据按需从 `service-account-metadata.json` 读取。

- 检查认证时捕获 `user get --me --format json` 和 `vault list --format json`，只报告状态及可访问保险库；连续操作复用已确认身份。
- 条目操作明确传 `--vault <ID>`；读写结果在本机解析，只输出元数据。入口清除冲突的 Connect/会话变量，阻止 Token 进入业务子进程。
- 映射缺失时先完成已授权入库和回读验证，再登记映射；不指向未经验证的条目。
- Token 失效或权限不足时报告原因，不自动扩权或回退桌面/MCP。更换 Token 需用户指定条目及读取授权，验证新账号与保险库后替换本机文件。
- 只读账号无法增加写权限时，新建仅对项目保险库具备 Read Items / Write Items 的账号；不让用户发送 Token。

Service Account 管理保险库条目，不认证 Environment/MCP。业务数据库、部署、发送和删除授权仍按当前任务确定。

[官方认证与支持命令](https://www.1password.dev/service-accounts/use-with-1password-cli)
