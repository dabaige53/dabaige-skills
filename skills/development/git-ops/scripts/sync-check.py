#!/usr/bin/env python3
"""Read-only preflight for syncing the current branch with its configured upstream."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def git(args: list[str], root: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(["git", *args], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and p.returncode:
        raise RuntimeError(p.stderr.strip() or f"git {' '.join(args)} failed")
    return p


def main() -> int:
    parser = argparse.ArgumentParser(description="检查当前分支是否可以安全同步")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    try:
        start = Path(args.repo_root).expanduser().resolve()
        p = git(["rev-parse", "--show-toplevel"], start, check=False)
        if p.returncode:
            raise RuntimeError("当前目录不在 Git 仓库内。")
        root = Path(p.stdout.strip())
        branch = git(["symbolic-ref", "--quiet", "--short", "HEAD"], root, check=False)
        if branch.returncode:
            raise RuntimeError("当前处于 detached HEAD，无法确定同步目标分支。")
        branch_name = branch.stdout.strip()
        status = git(["status", "--porcelain"], root).stdout
        if status:
            raise RuntimeError("工作区存在未提交改动。请先执行 git 提交，或自行处理后再同步。")
        for marker in ("rebase-merge", "rebase-apply", "MERGE_HEAD", "CHERRY_PICK_HEAD"):
            path = Path(git(["rev-parse", "--git-path", marker], root).stdout.strip())
            if not path.is_absolute():
                path = root / path
            if path.exists():
                raise RuntimeError(f"检测到进行中的 Git 操作：{marker}。请先完成该操作，再同步。")
        up = git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], root, check=False)
        if up.returncode:
            raise RuntimeError("当前分支没有配置 upstream。请先明确远端和目标分支；脚本不会擅自设置。")
        upstream = up.stdout.strip()
        counts = git(["rev-list", "--left-right", "--count", f"HEAD...{upstream}"], root).stdout.split()
        ahead, behind = (int(counts[0]), int(counts[1]))
        print(f"仓库：{root}")
        print(f"当前分支：{branch_name}")
        print(f"同步目标：{upstream}")
        print(f"本地领先：{ahead} 个提交；本地落后：{behind} 个提交")
        print("检查通过。下一步：fetch --prune、rebase upstream、普通 push。")
        return 0
    except RuntimeError as exc:
        print(f"停止同步：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
