# git-ops

一个精简的 Git Skill，只提供三个常用入口：

- `git 分支整理`
- `git 提交`
- `git 同步`

## 文件

```text
git-ops/
├── SKILL.md
├── README.md
└── scripts/
    ├── branch-cleanup.py
    ├── commit-check.py
    └── sync-check.py
```

要求：Python 3.9+、Git。无需第三方 Python 依赖。

## 安装

将整个 `git-ops` 文件夹放入 Agent 支持的 Skills 目录。Codex 用户级目录示例：

```bash
mkdir -p ~/.agents/skills
cp -R git-ops ~/.agents/skills/git-ops
```

## 手动检查脚本

```bash
# 预览本地分支清理
python3 scripts/branch-cleanup.py

# 执行分支整理（会 fetch/prune、快进当前分支 upstream，并删除安全确认已合并的本地分支）
python3 scripts/branch-cleanup.py --apply

# 检查准备提交的所有本地改动
python3 scripts/commit-check.py

# 检查指定目录（从仓库根目录运行）
python3 scripts/commit-check.py -- skills/workflow/wu-mode

# 检查已暂存的提交内容
python3 scripts/commit-check.py --staged-only

# 检查当前分支能否同步
python3 scripts/sync-check.py
```

`branch-cleanup.py` 默认只预览。执行前会检查工作区是否干净；删除分支前会保存恢复引用。脚本不会删除远端分支。
