# dabaige-skills

个人整理的 Agent Skills，适用于 Claude Code、Codex 等支持 `SKILL.md` 的工具。

## 安装

把需要的 Skill 目录复制或链接到工具的 Skills 目录，例如：

```bash
git clone https://github.com/dabaige53/dabaige-skills.git
ln -s "$PWD/dabaige-skills/skills/workflow/project-maintenance" ~/.claude/skills/project-maintenance
```

## 自写 Skills（19）

| Skill | 说明 |
| --- | --- |
| [decompose-ui](skills/creative/decompose-ui) | 将网页、网站、可视化和图表需求拆成抽象、可复用的组件。 |
| [readable-text](skills/creative/readable-text) | 撰写或优化便于阅读和扫读的文本；用于说明、邮件、报告正文的表达优化，以及标题、通知、摘要、列表和看板文案的批量生成与统一。 |
| [writing-project-achievements](skills/creative/writing-project-achievements) | 撰写面向领导的年度述职、阶段总结和项目成果汇报；将任务记录与产品材料转为具体交付、业务内容和应用价值，并复核或重写偏重开发过程的旧稿。 |
| [ci-tuning](skills/development/ci-tuning) | 基于项目现有 GitHub Actions CI 做工程化提速：建立 CI.md 与统一 CI Hook，重组 Lint、Typecheck、Test、Bu… |
| [fixit](skills/development/fixit) | 排查系统、开发环境和工具配置故障，结合本机证据、Search、GitHub Issues 与 Context7 查找相似问题，核实原因并验证修复。 |
| [project-development-standards](skills/development/project-development-standards) | 统一开发项目的文档、环境变量、配置和运行入口；按业务口径调整数据源，定位并验证性能优化。 |
| [value-cleaner](skills/development/value-cleaner) | Use when users want to remove low-value logic, redundant checks, filler, or me… |
| [getnote](skills/research/getnote) | 管理得到笔记。 |
| [1password-project-secrets](skills/tools/1password-project-secrets) | 配置、迁移项目凭据或排查认证失败时使用。 |
| [codex-handoff](skills/workflow/codex-handoff) | 交接当前工作到新 Codex 任务。 |
| [codex-thread-doctor](skills/workflow/codex-thread-doctor) | Audit and repair Codex task history and sidebar anomalies, individually or in … |
| [hermes-project-handoff](skills/workflow/hermes-project-handoff) | 将项目或任务交接给 Hermes，整理可访问的材料、工作进度、关键决策与验收条件，完成已授权的前置准备并生成独立可用的接力提示词。 |
| [linear-task-submission](skills/workflow/linear-task-submission) | Manage Linear issues and projects. |
| [oasis-dita](skills/workflow/oasis-dita) | 按 OASIS DITA 风格回复或写入文档 |
| [project-maintenance](skills/workflow/project-maintenance) | 盘点、构建和整理项目规范，统一文档职责、存放位置与 AGENTS.md 阅读入口。 |
| [skills-check](skills/workflow/skills-check) | 检查并清理 Skill 文件中的低价值内容与跨 Skill 依赖：没人要的证明、叠加否认、重复检查、空洞收尾、无条件告诫、重复规则，以及引用其他 Skill… |
| [think-hard](skills/workflow/think-hard) | Use $think-hard for independent reasoning and alternative solutions. |
| [todoist-task-writing](skills/workflow/todoist-task-writing) | 规范 Todoist 个人待办及 AI 自动化异常的创建、更新、去重、简洁描述、复杂子任务、人工决策与回读。 |
| [user-doctor](skills/workflow/user-doctor) | 复核需求落实与工作偏差。 |

## 收录的第三方 Skills（58）

保留上游许可证，部分有本地修改，详见 [第三方声明](THIRD_PARTY_NOTICES.md)。

| Skill | 来源 | 许可证 |
| --- | --- | --- |
| [diagram-design](skills/creative/diagram-design) | [cathrynlavery/diagram-design](https://github.com/cathrynlavery/diagram-design/tree/main/skills/diagram-design) | MIT |
| [frontend-slides](skills/creative/frontend-slides) | [zarazhangrui/frontend-slides](https://github.com/zarazhangrui/frontend-slides/tree/main/plugins/frontend-slides/skills/frontend-slides) | MIT |
| [impeccable](skills/creative/impeccable) | [pbakaus/impeccable](https://github.com/pbakaus/impeccable/tree/main/.agents/skills/impeccable) | Apache-2.0 |
| [interface-bts](skills/creative/interface-bts) | [nomanjack/interface-bts](https://github.com/nomanjack/interface-bts) | MIT |
| [kami](skills/creative/kami) | [tw93/Kami](https://github.com/tw93/Kami/tree/main/plugins/kami/skills/kami) | MIT |
| [shadcn](skills/creative/shadcn) | [shadcn-ui/ui](https://github.com/shadcn-ui/ui/tree/main/skills/shadcn) | MIT |
| [show-me](skills/creative/show-me) | [humanlayer/skills](https://github.com/humanlayer/skills/tree/main/plugins/show-me/skills/show-me) | MIT |
| [show-me-your-work](skills/creative/show-me-your-work) | [cursor/plugins](https://github.com/cursor/plugins/tree/main/pstack/skills/show-me-your-work) | MIT |
| [stageshow](skills/creative/stageshow) | [benjitaylor/skills](https://github.com/benjitaylor/skills/tree/main/stageshow) | MIT |
| [ui-skills-root](skills/creative/ui-skills-root) | [ibelick/ui-skills](https://github.com/ibelick/ui-skills/tree/main/skills/ui-skills-root) | MIT |
| [unslop](skills/creative/unslop) | [cursor/plugins](https://github.com/cursor/plugins/tree/main/pstack/skills/unslop) | MIT |
| [writing-beats](skills/creative/writing-beats) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/in-progress/writing-beats) | MIT |
| [writing-fragments](skills/creative/writing-fragments) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/in-progress/writing-fragments) | MIT |
| [writing-shape](skills/creative/writing-shape) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/in-progress/writing-shape) | MIT |
| [benchmark-checklist](skills/development/benchmark-checklist) | [cursor/plugins](https://github.com/cursor/plugins/tree/main/pstack/skills/benchmark-checklist) | MIT |
| [cli-creator](skills/development/cli-creator) | [openai/skills](https://github.com/openai/skills/tree/main/skills/.curated/cli-creator) | Apache-2.0 |
| [code-review](skills/development/code-review) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/code-review) | MIT |
| [codebase-design](skills/development/codebase-design) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/codebase-design) | MIT |
| [correct](skills/development/correct) | [cursor/plugins](https://github.com/cursor/plugins/tree/main/pstack/skills/correct) | MIT |
| [diagnosing-bugs](skills/development/diagnosing-bugs) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/diagnosing-bugs) | MIT |
| [domain-modeling](skills/development/domain-modeling) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/domain-modeling) | MIT |
| [implement](skills/development/implement) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/implement) | MIT |
| [implement-spec](skills/development/implement-spec) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/implement-spec) | MIT |
| [improve-codebase-architecture](skills/development/improve-codebase-architecture) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/improve-codebase-architecture) | MIT |
| [matt-prototype](skills/development/matt-prototype) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/prototype) | MIT |
| [playwright-interactive](skills/development/playwright-interactive) | [openai/skills](https://github.com/openai/skills/tree/main/skills/.curated/playwright-interactive) | Apache-2.0 |
| [pr](skills/development/pr) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/pr) | MIT |
| [retro](skills/development/retro) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/retro) | MIT |
| [tdd](skills/development/tdd) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/tdd) | MIT |
| [Search](skills/research/Search) | [exa-labs/exa-mcp-server](https://github.com/exa-labs/exa-mcp-server/tree/main/skills/search) | MIT |
| [agent-reach](skills/research/agent-reach) | [Panniantong/agent-reach](https://github.com/Panniantong/agent-reach/tree/main/agent_reach/skill) | MIT |
| [find-docs](skills/research/find-docs) | [upstash/context7](https://github.com/upstash/context7/tree/master/skills/find-docs) | MIT |
| [how](skills/research/how) | [cursor/plugins](https://github.com/cursor/plugins/tree/main/pstack/skills/how) | MIT |
| [research](skills/research/research) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/research) | MIT |
| [why](skills/research/why) | [cursor/plugins](https://github.com/cursor/plugins/tree/main/pstack/skills/why) | MIT |
| [antigravity-cli](skills/tools/antigravity-cli) | [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent/tree/main/optional-skills/autonomous-ai-agents/antigravity-cli) | MIT |
| [engram-memory](skills/tools/engram-memory) | [Gentleman-Programming/engram](https://github.com/Gentleman-Programming/engram/tree/main/plugin/codex/skills/memory) | MIT |
| [hatch-pet](skills/tools/hatch-pet) | [openai/skills](https://github.com/openai/skills/tree/main/skills/.curated/hatch-pet) | Apache-2.0 |
| [i-have-adhd](skills/tools/i-have-adhd) | [ayghri/i-have-adhd](https://github.com/ayghri/i-have-adhd/tree/main/skills/i-have-adhd) | MIT |
| [typesafe-ai](skills/tools/typesafe-ai) | [typesafe-ai/skills](https://github.com/typesafe-ai/skills) | MIT |
| [ask-matt](skills/workflow/ask-matt) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/ask-matt) | MIT |
| [grill-me](skills/workflow/grill-me) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/productivity/grill-me) | MIT |
| [grill-with-docs](skills/workflow/grill-with-docs) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/grill-with-docs) | MIT |
| [grilling](skills/workflow/grilling) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/productivity/grilling) | MIT |
| [handoff](skills/workflow/handoff) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/productivity/handoff) | MIT |
| [ponytail](skills/workflow/ponytail) | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail/tree/main/skills/ponytail) | MIT |
| [ponytail-audit](skills/workflow/ponytail-audit) | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail/tree/main/skills/ponytail-audit) | MIT |
| [setup-matt-pocock-skills](skills/workflow/setup-matt-pocock-skills) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/setup-matt-pocock-skills) | MIT |
| [skill-doctor](skills/workflow/skill-doctor) | [warpdotdev/common-skills](https://github.com/warpdotdev/common-skills/tree/main/.agents/skills/skill-doctor) | MIT |
| [teach](skills/workflow/teach) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/productivity/teach) | MIT |
| [to-questionnaire](skills/workflow/to-questionnaire) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/productivity/to-questionnaire) | MIT |
| [to-spec](skills/workflow/to-spec) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/to-spec) | MIT |
| [to-tickets](skills/workflow/to-tickets) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/to-tickets) | MIT |
| [triage](skills/workflow/triage) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/triage) | MIT |
| [wait-what](skills/workflow/wait-what) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/productivity/wait-what) | MIT |
| [wayfinder](skills/workflow/wayfinder) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/wayfinder) | MIT |
| [wizard](skills/workflow/wizard) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/wizard) | MIT |
| [writing-for-agents](skills/workflow/writing-for-agents) | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/productivity/writing-for-agents) | MIT |

## 许可证

自写部分使用 [MIT](LICENSE)。第三方 Skill 沿用各自目录内的 LICENSE。
