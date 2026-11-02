# 文件用途与模板

以下是新建体系的默认文件地址，不是必须全部创建的清单。已有项目有明确路径约定时沿用，统一目录任务按已确定方案迁移。配置跨任务复用的说明和规范。以下按需选用，路径服从项目约定；已有内容不足时原处补充，内容完整时沿用。文档体系整理先按 [文档分层与迁移](document-lifecycle.md) 区分职责，再选模板；下列默认路径不要求迁移已有文件。

## 基础文档

| 模板与默认路径 | 用来做什么 | 什么时候查、查完做什么 | 什么时候更新 |
| --- | --- | --- | --- |
| [项目入口](../assets/templates/overview.md) · `docs/README.md` | 介绍项目用途、开始方式和文档位置 | 初次接触或寻找入口时，找到下一步操作及对应文档 | 用途、使用入口或文档位置变化 |
| [产品与业务](../assets/templates/product.md) · `docs/agent/PRODUCT.md` | 说明使用者、范围和稳定业务规则 | 判断某个需求是否符合产品目标、应该怎样表现 | 已确认的目标、范围或业务规则变化 |
| [开发操作](../assets/templates/development.md) · `docs/implementation/development.md` | 说明当前初始化、开发、验证和交付的操作步骤 | 开始修改或交付前，找到应执行的步骤和检查 | 环境、开发入口、验证或交付流程变化 |
| [PR 规范](../assets/templates/pr.md) · `docs/agent/pr.md` | 约定 PR 要说明什么、提供什么证据 | 编写或审查 PR 时，按统一要求描述变更 | 团队审查要求或 PR 模板变化 |
| [排查与恢复](../assets/templates/troubleshooting.md) · `docs/implementation/troubleshooting.md` | 保存可复用的故障判断和恢复方法 | 遇到相同现象时，按证据定位并恢复 | 新方法经过验证，或旧方法不再适用 |

代码规范和部署规范分别使用以下模板，操作步骤使用开发操作或运行维护模板。

| 模板与默认路径 | 职责 | 更新条件 |
| --- | --- | --- |
| [代码规范](../assets/templates/code-standards.md) · `docs/agent/code-standards.md` | 代码编写与审查规则 | 工程约定改变 |
| [部署规范](../assets/templates/deployment.md) · `docs/agent/deployment.md` | 发布条件、授权、验收与回退原则 | 发布政策改变 |
| `docs/reference/DESIGN.md` | 产品设计总规范，按已有设计材料编写 | 设计原则或通用交互改变 |
| `docs/implementation/release-runbook.md` | 当前发布操作步骤，可选运行维护模板 | 发布工具或流程改变 |

## 按项目需要增加

| 模板与默认路径 | 用来做什么 | 什么时候查、查完做什么 | 什么时候更新 |
| --- | --- | --- | --- |
| [配置说明](../assets/templates/configuration.md) · `docs/implementation/configuration.md` | 说明配置入口、优先级和生效方式 | 更换环境或调整参数时，找到该改哪里及如何确认生效 | 配置入口、默认值、优先级或加载方式变化 |
| [运行维护](../assets/templates/operations.md) · `docs/implementation/operations.md` | 说明启动、停止、健康检查、升级和恢复 | 日常运行或发布时，执行现行操作流程 | 部署方式、运行入口或恢复方法变化 |
| [测试规范](../assets/templates/testing.md) · `docs/agent/testing.md` | 说明各类改动需要哪些验证及通过标准 | 修改功能前或交付前，选择适用检查 | 测试入口、环境或通过标准变化 |
| [系统架构](../assets/templates/architecture.md) · `docs/reference/architecture.md` | 说明模块职责、依赖和数据流 | 判断改动放在哪里、会影响什么 | 模块边界、依赖或数据流变化 |
| [接口约定](../assets/templates/api-contracts.md) · `docs/reference/api-contracts.md` | 说明调用边界、输入输出、错误和副作用 | 对接服务或修改接口时，确认双方约定 | 接口行为或兼容性要求变化 |
| [数据字典](../assets/templates/data-dictionary.md) · `docs/reference/data-dictionary.md` | 说明数据来源、字段、指标、单位和限制 | 查询、计算或展示数据前，确认含义和统计口径 | 来源、字段含义、指标算法或刷新方式变化 |
| [功能对照](../assets/templates/feature-matrix.md) · `docs/implementation/feature-matrix.md` | 说明不同客户端或版本当前支持哪些能力 | 比较平台能力或排查差异时，确认当前支持范围 | 已交付能力或平台支持情况变化 |
| [文件管理](../assets/templates/file-management.md) · `docs/agent/file-management.md` | 说明各目录放什么及长期保留边界 | 新增文件或整理目录时，确定位置和保留方式 | 目录职责或文件保留规则变化 |

测试规范保存长期标准，不收集每次测试报告；功能对照只描述当前能力，不建立任务清单；文件管理只规定存放方式，不生成任务产物。具体测试命令与环境说明放在 `docs/implementation/testing.md`；小项目可把这些操作说明合并到开发文档。

## 其他项目文件

以下文件按实际需要纳入方案。可执行配置的步骤见 [开发配置](development-setup.md)，仅配置文档时记录现行方式。

| 文件 | 作用与推荐条件 |
| --- | --- |
| `AGENTS.md` | 项目文档的阅读入口，按主流程维护 |
| 环境变量入口 | 沿用项目注入、挂载或文件方式，向运行进程传递环境参数；不默认新建 `.env` |
| 配置文件 | 保存数据源映射、路径与运行参数，沿用现有格式和覆盖规则 |
| `.env.example` | 项目用环境变量配置时，列出变量名称和非敏感示例；已有配置机制优先 |
| `.gitignore` | 项目产生不应提交的本地文件时，按实际工具配置忽略规则 |
| 依赖声明与锁文件 | 项目已有包管理器时，按其机制固定依赖；不并行引入另一套 |
| 运行脚本 | 启动或检查存在重复操作时提供统一入口；优先沿用现有命令 |
| `Dockerfile`、Compose、`.dockerignore` | 已选择容器运行方式时使用；先确定运行需求，再按现有技术栈配置 |

## Agent 协作文档

项目使用相关流程时，将下列文档纳入产出。沿用现有管理工具和读取路径；没有约定时采用下表路径，按项目实际情况填写。

| 文档 | 何时需要 | 写清什么 |
| --- | --- | --- |
| `docs/agent/issue-tracker.md` | Agent 需要读写事项时 | 管理工具（GitHub、GitLab、本地 Markdown 或其他）；创建、读取、列出、评论、加减标签、关闭的具体命令或文件操作；父子事项与阻塞关系的表示方式；外部 PR/MR 是否作为需求入口；规格存放位置。仓库从 Git remote 推断，只作候选依据。本地 Markdown 时写明目录（如 `.scratch/<feature>/` 下的 `spec.md` 与 `issues/<NN>-<slug>.md`）、状态行和评论位置 |
| `docs/agent/domain.md` | 需要统一业务术语或遵循架构决策时 | 术语表位置（单一 `GLOSSARY.md`，或多上下文时由 `GLOSSARY-MAP.md` 指向各自术语表）和 ADR 目录；先读哪些文件；输出中的领域概念使用术语表用词；结论与现有 ADR 冲突时明确指出，不静默覆盖 |
| `docs/agent/triage-labels.md` | 已使用 triage 流程时 | 五个角色与项目实际标签的对应：`needs-triage` 待评估、`needs-info` 等待补充信息、`ready-for-agent` 已完整描述可交给 Agent、`ready-for-human` 需人工实现、`wontfix` 不处理 |

领域文档的路径服从项目约定及使用它的流程；术语和 ADR 根据已确认的讨论形成，不预建空文件。标签文档记录映射，创建外部标签按用户授权处理。具体规格、PR 和任务状态继续使用项目原有入口。
