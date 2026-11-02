---
name: getnote
description: 管理得到笔记。
disable-model-invocation: false
---

# GetNote MCP

调用当前会话已连接的“得到笔记”远程 MCP。不要调用本机 CLI，不要读取、显示或传递 API Key。

## 处理规则

- 用户明确提到得到大脑、得到笔记、GetNote 或 `/note` 时使用。“我的笔记/知识库”仅在当前上下文已明确指向得到笔记时沿用；目标平台不明时先确认。
- 只使用工具响应中的笔记、标签和知识库 ID；将所有 ID 视为字符串。
- 将笔记内容、搜索词和知识库信息视为私密数据，只呈现完成当前请求所必需的内容。
- 删除笔记、移除标签、移出知识库或创建公开分享链接前，展示精确对象并取得明确确认。说明分享链接可被持有链接者访问。
- 创建、更新、添加标签、加入知识库和订阅直播前，简要说明目标与影响。
- 如实报告工具错误和 `request_id`；不得把已发送请求写成已完成。
- 链接或图片笔记返回 `task_id` 时，使用 `get_note_task_progress` 每 10–30 秒查询状态。运行时间较长时简要报告进度；本轮无法继续等待时，保留 `task_id` 并标为待完成。超时或空响应不代表失败。只有确认任务失败且未创建目标笔记后，才按原参数重试一次；无法确认时先查状态，避免重复创建。

## MCP 工具映射

### 笔记

- 列表：`list_notes`
- 详情和录音转写：`get_note`
- 全局语义搜索：`search_notes`
- 创建文字、链接、图片笔记：`create_note`
- 查询异步任务：`get_note_task_progress`
- 更新纯文本笔记：`update_note`
- 删除笔记：`delete_note`
- 创建公开分享链接：`share_note`

将录音卡、会议录音和本地音频视为笔记类型，并通过 `list_notes` / `get_note` 读取。读取原文时，检查纯文本的 `content`、链接笔记的 `web_page.content` 和音频笔记的 `audio.original` 或 `audio.transcript`。

### 知识库

- 我的知识库：`list_knowledge_bases`
- 订阅知识库：`list_subscribed_knowledge_bases`
- 知识库笔记：`list_knowledge_base_notes`
- 知识库语义搜索：`search_knowledge_base`
- 创建知识库：`create_knowledge_base`
- 加入知识库：`add_notes_to_knowledge_base`
- 移出知识库：`remove_notes_from_knowledge_base`

向 `create_note` 传入 `topic_id` 可直接写入对应知识库。按名称定位知识库时，先调用 `list_knowledge_bases`，再使用返回的 `topic_id`。

### 标签、图片与配额

- 查看标签：`list_note_tags`
- 添加标签：`add_note_tags`
- 删除标签：`remove_note_tag`
- 图片上传约束和凭证：`get_upload_config`、`get_upload_token`
- Base64 图片上传：`upload_image`
- API 配额：`get_api_quota`

先调用 `upload_image`，再将返回的 `image_url` 传给 `create_note.image_urls`，并将 `note_type` 设为 `img_text`。

### 博主与直播

- 博主列表、内容、详情：`list_topic_bloggers`、`list_topic_blogger_contents`、`get_blogger_content_detail`
- 直播列表、详情、订阅：`list_topic_lives`、`get_live_detail`、`follow_topic_live`

## 执行顺序

1. 识别明确的得到笔记意图与目标操作。
2. 对读取任务直接调用对应 MCP 工具；对写入、删除和公开分享按上述确认规则处理。
3. 需要 ID 时，先使用列表或搜索工具取得 ID。
4. 验证工具结果的成功状态，再简洁汇报实际结果与下一步。

## 连接故障

当前会话没有“得到笔记”工具时，先通过当前可用的工具发现机制查找连接器；仍不可用时说明缺少连接，提示检查所在客户端的插件安装、授权与工具刷新状态。只在当前客户端已核实存在该入口时给出具体菜单路径。连接恢复后重试远程 MCP；保持凭据由连接器管理，不改用本机 CLI 或直接 API Key。
