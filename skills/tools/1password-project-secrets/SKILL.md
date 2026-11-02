---
name: 1password-project-secrets
description: 配置、迁移项目凭据或排查认证失败时使用。
---

# 项目凭据与运行

1. 优先使用产品已有插件、连接器的授权完成任务；项目进程仍需凭据时，再使用本机入口。读取项目规则和原运行命令，帮助、测试及离线检查直接运行：

   ```sh
   project-run <项目目录名> -- <原运行命令>
   ```

2. 按当前授权验证实际入口，只输出配置状态。注入成功与业务运行成功分开报告；缺值或失败先修复，不生成替代密钥。
3. 交付只给用户可执行的项目命令、验证结果和仍阻塞运行的事项。

凭据工具、Token、映射和包装器留在仓库外。线上、仓库、产品及项目文档只使用通用环境变量，不出现相关依赖或文案；密钥不进入输出，不自动回退桌面授权。

## 按需读取

- 产品有插件或连接器：[授权优先级](references/connector-auth.md)。

- 入口缺失、项目未登记或认证失败：[本机认证与映射](references/service-account.md)。
- 发现待迁移凭据或用户要求盘点、迁移：[检查与迁移](references/audit-migration.md)。
- 迁移涉及固定配置文件、容器或引用模板：[配置消费方式](references/migration-patterns.md)。
- 用户明确要求 Environment 或挂载：[Environment 配置](references/environments.md)。

只读取当前分支需要的材料，复用本次已确认的状态。
