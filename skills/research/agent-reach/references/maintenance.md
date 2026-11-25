# 维护

更新失败、浏览器起不来、渠道报错或用户要卸载时读这份。

- 更新：`agent-reach update` 升级 Agent Reach、已加渠道的工具和 skill；`agent-reach update --check` 只查有没有新版本。只在用户同意后执行。
- 离线查看本机状态用 `agent-reach doctor --text`。联网实测用 `agent-reach check <渠道> --text`，加 `--search` 只测搜索或职位。
- 浏览器：`agent-reach browser status` 看状态，`browser setup` 准备内核和扩展，`browser stop` 关闭；CloakBrowser 下载失败后修好网络可 `browser setup --retry-cloak`。
- 分清失败环节：依赖下载、浏览器连接、登录、网页加载、平台限流各是各的；网络超时不要说成登录失效。
- 上游工具报错时记录错误和版本。需要升级时使用上面的更新命令，保留已安装文件供排查。
- `PLATFORM_BLOCKED`、`RATE_LIMITED`、`NEED_LOGIN`、`BUSY` 停止本次尝试，等用户处理后再继续，不反复开窗。
- 密钥和代理：`agent-reach configure groq-key | openai-key | proxy | github-token`，值由用户本人提供。
- 端口冲突（`Port <n> belongs to an unmanaged browser`）：别的程序占了专用浏览器端口（默认 9222）。不要关掉用户的那个程序；用户同意后 `agent-reach configure browser-port <空闲端口>`。
- 卸载：先 `agent-reach uninstall --dry-run` 给用户看范围，确认后 `agent-reach uninstall`。只删 Reach 自己装的东西，用户的其他文件和浏览器保留。
