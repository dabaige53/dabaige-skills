# OASIS DITA 速读

OASIS DITA（Darwin Information Typing Architecture）是 OASIS 维护的主题化写作标准。1.2（2010）和 1.3（2015）是正式标准，2.0 仍是草案。它不规定文风，只规定三件事：内容按类型拆分、每种类型有固定结构、内容标注给谁看。

## 核心原则

- **一块内容只回答一种问题**（信息分型）。“是什么”“怎么做”“查什么”“出错怎么办”分开写，不混在一起。
- **先给短描述**：每个主题有 `title` 和一句 `shortdesc`，读者看完这一句就知道要不要往下读。
- **结构与受众分开**：先按类型写好内容，再按读者筛选显示哪些部分。
- **可组合**：一份完整文档（map）由多个主题拼成，每个主题保持单一类型。

## 主题类型

| 类型 | 回答的问题 | 结构 |
| --- | --- | --- |
| concept 概念 | 是什么、为什么 | 定义、说明段落、示例；不写操作步骤 |
| task 任务 | 怎么做 | prereq 前置条件 → context 背景 → steps 步骤 → result 结果 → example 示例 → postreq 后续 |
| reference 参考 | 查什么 | 表格、属性列表、参数说明；便于扫读 |
| troubleshooting 排错 | 出问题怎么办 | condition 现象 → cause 原因 → remedy 解决步骤；可有多组原因与解决方法 |
| glossentry 术语 | 这个词指什么 | glossterm 术语 + glossdef 定义；一个主题只定义一个词义，多义就拆成多个主题 |

任务的步骤：每个 `step` 必须有一个 `cmd` 动作；可附 `info` 说明、`substeps` 子步骤、`choices` 选项、`stepresult` 本步结果、`steptroubleshooting` 本步排错。`steps` 有顺序，`steps-unordered` 无顺序。

Strict Task 与 General Task 的区别只在结构松紧：Strict 规定各部分顺序且各出现一次；General 允许前置条件和背景多次、任意顺序出现，还允许 `steps-informal` 非正式步骤。两者的受众机制完全相同。

## 受众机制

| 机制 | 作用 |
| --- | --- |
| `<audience>` 元素 | 描述读者：`type` 是什么人、`job` 在做什么、`experiencelevel` 懂到什么程度（novice / general / expert），`name` 给这个受众起名 |
| `@audience` 属性 | 标在任意片段上，表示这一段给谁看；可填多个值，空格分隔 |
| Subject Scheme | 组织级受控词表，限定 `@audience` 只能取哪些值；由信息架构师定义 |
| DITAVAL | 发布时按受众 include 包含、exclude 排除、flag 标记 |

受众只表示读者，不表示作者或执行者。“谁来执行”需另行记录。

在本 Skill 中：项目 `AUDIENCE.md` 相当于 Subject Scheme 和受众定义；按读者裁剪回复相当于 DITAVAL 筛选。

## 官方资料

`oasis-dita/` 下是从 OASIS 官方页面下载并转为文本的原文，每个文件首行注明来源地址。

| 文件 | 内容 |
| --- | --- |
| `v1.3-information-typing.md` | 信息分型原则 |
| `v1.3-concept-topic.md` | 概念主题 |
| `v1.3-strict-task-topic.md` | 严格任务主题 |
| `v1.3-general-task-topic.md` | 通用任务主题 |
| `v1.3-reference-topic.md` | 参考主题 |
| `v1.3-troubleshooting-topic.md` | 排错主题 |
| `v1.3-glossentry-topic.md` | 术语主题 |
| `v1.3-glossentry-element.md` | `<glossentry>` 元素 |
| `v1.3-audience-element.md` | `<audience>` 元素 |
| `v1.3-metadata-attributes.md` | `@audience` 等条件属性 |
| `v1.3-conditional-processing.md` | 条件处理 |
| `v1.3-ditaval-prop.md` | DITAVAL 筛选规则 |
| `v1.3-subject-scheme-controlled-values.md` | Subject Scheme 受控值 |
| `v2.0-draft-audience-element.md` | 2.0 草案 `<audience>`，移除了 `othertype`、`otherjob` |
| `v2.0-draft-strict-task-topic.md` | 2.0 草案严格任务 |
| `v2.0-draft-general-task-topic.md` | 2.0 草案通用任务 |
| `v2.0-draft-glossentry-element.md` | 2.0 草案 `<glossentry>` 元素 |

完整规范：[DITA 1.3 Technical Content](https://docs.oasis-open.org/dita/dita/v1.3/os/part2-tech-content/dita-v1.3-os-part2-tech-content.html)、[DITA 2.0 草案](https://dita-lang.org/2.0/dita/toc.html)。
