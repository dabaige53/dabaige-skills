#!/usr/bin/env python3
"""Safely fast-forward the current branch and remove local branches merged into base."""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import subprocess
import sys
from pathlib import Path


def git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(["git", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and p.returncode:
        detail = p.stderr.strip() or p.stdout.strip() or f"git {' '.join(args)} failed"
        raise RuntimeError(detail)
    return p


def repo_root(start: Path) -> Path:
    p = git(["rev-parse", "--show-toplevel"], start, check=False)
    if p.returncode:
        raise RuntimeError("当前目录不在 Git 仓库内。")
    return Path(p.stdout.strip())


def current_branch(root: Path) -> str | None:
    p = git(["symbolic-ref", "--quiet", "--short", "HEAD"], root, check=False)
    return p.stdout.strip() if p.returncode == 0 else None


def upstream(root: Path) -> str | None:
    p = git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], root, check=False)
    return p.stdout.strip() if p.returncode == 0 else None


def remotes(root: Path) -> list[str]:
    return [x for x in git(["remote"], root).stdout.splitlines() if x.strip()]


def default_base(root: Path, remote: str | None) -> tuple[str, str]:
    if remote:
        p = git(["symbolic-ref", "--quiet", "--short", f"refs/remotes/{remote}/HEAD"], root, check=False)
        if p.returncode == 0:
            short = p.stdout.strip()
            return short.rsplit("/", 1)[-1], short
        for name in ("main", "master"):
            ref = f"refs/remotes/{remote}/{name}"
            if git(["show-ref", "--verify", "--quiet", ref], root, check=False).returncode == 0:
                return name, f"{remote}/{name}"
    for name in ("main", "master"):
        if git(["show-ref", "--verify", "--quiet", f"refs/heads/{name}"], root, check=False).returncode == 0:
            return name, name
    raise RuntimeError("无法识别默认分支。请先设置 origin/HEAD，或确保存在 main/master 分支。")


def worktree_branches(root: Path) -> set[str]:
    result: set[str] = set()
    for line in git(["worktree", "list", "--porcelain"], root).stdout.splitlines():
        if line.startswith("branch refs/heads/"):
            result.add(line.removeprefix("branch refs/heads/"))
    return result


def local_branches(root: Path) -> list[str]:
    return [x for x in git(["for-each-ref", "--format=%(refname:short)", "refs/heads"], root).stdout.splitlines() if x]


def is_ancestor(root: Path, branch: str, base_ref: str) -> bool:
    return git(["merge-base", "--is-ancestor", branch, base_ref], root, check=False).returncode == 0


def protected(name: str, base_name: str) -> bool:
    if name == base_name:
        return True
    fixed = {"main", "master", "develop", "dev", "staging", "production"}
    if name in fixed:
        return True
    return any(fnmatch.fnmatch(name, pattern) for pattern in ("release/*", "hotfix/*"))


def plan(root: Path, base_name: str, base_ref: str) -> tuple[list[tuple[str, str]], list[str]]:
    current = current_branch(root)
    checked_out = worktree_branches(root)
    candidates: list[tuple[str, str]] = []
    kept: list[str] = []
    for name in local_branches(root):
        if name == current:
            kept.append(f"{name}: 当前分支")
        elif name in checked_out:
            kept.append(f"{name}: 正在其他 worktree 使用")
        elif protected(name, base_name):
            kept.append(f"{name}: 受保护分支")
        elif is_ancestor(root, name, base_ref):
            oid = git(["rev-parse", f"refs/heads/{name}"], root).stdout.strip()
            candidates.append((name, oid))
        else:
            kept.append(f"{name}: 尚未合入 {base_ref}，保留")
    return candidates, kept


def main() -> int:
    parser = argparse.ArgumentParser(description="预览或安全清理已合入默认分支的本地分支")
    parser.add_argument("--repo-root", default=".", help="Git 仓库目录，默认当前目录")
    parser.add_argument("--base", help="指定清理基准分支或 ref，例如 origin/main")
    parser.add_argument("--apply", action="store_true", help="实际执行 fetch、快进和本地分支清理")
    args = parser.parse_args()
    try:
        root = repo_root(Path(args.repo_root).expanduser().resolve())
        current = current_branch(root)
        if not current:
            raise RuntimeError("当前处于 detached HEAD，无法安全整理分支。")
        dirty = bool(git(["status", "--porcelain"], root).stdout.strip())
        if args.apply and dirty:
            raise RuntimeError("工作区存在未提交改动。为避免影响现场，已停止；请先执行 git 提交或自行处理改动。")

        remote_list = remotes(root)
        remote = "origin" if "origin" in remote_list else (remote_list[0] if remote_list else None)
        if args.apply:
            if remote_list:
                print("[执行] git fetch --prune")
                git(["fetch", "--prune"], root)
            else:
                print("[提示] 仓库没有配置远端，跳过 fetch/prune。")
            up = upstream(root)
            if up:
                print(f"[执行] 将当前分支 {current} 快进到 {up}")
                git(["merge", "--ff-only", "@{upstream}"], root)
            else:
                print("[提示] 当前分支没有 upstream，跳过 upstream 快进。")

        if args.base:
            base_ref = args.base
            base_name = base_ref.rsplit("/", 1)[-1]
            if git(["rev-parse", "--verify", base_ref], root, check=False).returncode:
                raise RuntimeError(f"基准分支不存在：{base_ref}")
        else:
            base_name, base_ref = default_base(root, remote)

        if args.apply and not upstream(root) and current == base_name and base_ref != current:
            print(f"[执行] 将默认分支 {current} 快进到 {base_ref}")
            git(["merge", "--ff-only", base_ref], root)

        candidates, kept = plan(root, base_name, base_ref)
        print(f"仓库：{root}")
        print(f"当前分支：{current}")
        print(f"清理基准：{base_ref}")
        print(f"可安全清理的本地分支（{len(candidates)}）：")
        for name, oid in candidates:
            print(f"  - {name} ({oid[:12]})")
        print(f"保留分支（{len(kept)}）：")
        for item in kept:
            print(f"  - {item}")
        if not args.apply:
            print("\n仅预览，未修改仓库。确认后使用 --apply 执行。")
            return 0

        if not candidates:
            print("没有符合安全清理条件的本地分支。")
            return 0
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        deleted = 0
        for name, oid in candidates:
            # Recheck immediately before deletion to avoid acting on a changed ref.
            current_oid = git(["rev-parse", f"refs/heads/{name}"], root).stdout.strip()
            if current_oid != oid or not is_ancestor(root, name, base_ref):
                print(f"[跳过] {name}: 分支状态已变化或不再满足合入条件")
                continue
            backup_ref = f"refs/backup/git-ops/{stamp}/{name}"
            git(["update-ref", backup_ref, oid], root)
            git(["update-ref", "-d", f"refs/heads/{name}", oid], root)
            print(f"[已清理] {name}；恢复命令：git branch {name} {backup_ref}")
            deleted += 1
        print(f"完成：清理 {deleted} 个本地分支；未删除任何远端分支。")
        return 0
    except RuntimeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
