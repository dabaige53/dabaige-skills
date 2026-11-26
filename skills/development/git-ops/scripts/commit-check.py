#!/usr/bin/env python3
"""Preflight checks for committing the requested repository paths."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

SECRET_PATTERNS = [
    ("private key", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("GitHub token", re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("AWS access key", re.compile(rb"\bAKIA[0-9A-Z]{16}\b")),
    ("OpenAI-style API key", re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("Google API key", re.compile(rb"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("Slack token", re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
]
SENSITIVE_NAMES = {".env", "id_rsa", "id_ed25519", "credentials.json", "service-account.json"}
SENSITIVE_SUFFIXES = {".pem", ".p12", ".pfx", ".key"}
EXAMPLE_NAMES = {".env.example", ".env.sample", "credentials.example.json", "credentials.sample.json"}
MAX_SCAN_BYTES = 2 * 1024 * 1024


def git(args: list[str], root: Path, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    p = subprocess.run(["git", *args], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and p.returncode:
        raise RuntimeError(p.stderr.decode(errors="replace").strip() or f"git {' '.join(args)} failed")
    return p


def root_from(path: str) -> Path:
    p = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=Path(path).expanduser().resolve(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode:
        raise RuntimeError("当前目录不在 Git 仓库内。")
    return Path(p.stdout.strip())


def changed_paths(root: Path, staged_only: bool, scope: list[str]) -> list[str]:
    args = [["diff", "--cached", "--name-only", "-z"]] if staged_only else [
        ["diff", "--cached", "--name-only", "-z"],
        ["diff", "--name-only", "-z"],
    ]
    paths: set[str] = set()
    for command in args:
        raw = git(["--literal-pathspecs", *command, "--", *scope], root).stdout
        paths.update(x.decode("utf-8", "surrogateescape") for x in raw.split(b"\0") if x)
    if not staged_only:
        other = git(["--literal-pathspecs", "ls-files", "--others", "--exclude-standard", "-z", "--", *scope], root).stdout
        paths.update(x.decode("utf-8", "surrogateescape") for x in other.split(b"\0") if x)
    return sorted(paths)


def inspect_file(root: Path, rel: str, staged_only: bool) -> list[str]:
    path = Path(rel)
    base = path.name.lower()
    if base not in EXAMPLE_NAMES:
        if base in SENSITIVE_NAMES or (base.startswith(".env.") and base not in EXAMPLE_NAMES) or path.suffix.lower() in SENSITIVE_SUFFIXES:
            return ["疑似凭据文件名"]
    if staged_only:
        p = git(["show", f":{rel}"], root, check=False)
        data = p.stdout if p.returncode == 0 else b""
    else:
        full = root / path
        try:
            if not full.is_file() or full.stat().st_size > MAX_SCAN_BYTES:
                return []
            data = full.read_bytes()
        except OSError:
            return []
    if len(data) > MAX_SCAN_BYTES or b"\0" in data[:8192]:
        return []
    reasons = [label for label, pattern in SECRET_PATTERNS if pattern.search(data)]
    return reasons


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 Git 提交内容")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--staged-only", action="store_true", help="只检查暂存区内容")
    parser.add_argument("paths", nargs="*", help="限定到仓库根目录下的文件或目录")
    args = parser.parse_args()
    try:
        root = root_from(args.repo_root)
        paths = changed_paths(root, args.staged_only, args.paths)
        if not paths:
            print("没有可提交的改动。")
            return 1
        print(f"仓库：{root}")
        print(f"待检查文件：{len(paths)}")
        for rel in paths:
            print(f"  - {rel}")
        blocked: list[tuple[str, list[str]]] = []
        for rel in paths:
            reasons = inspect_file(root, rel, args.staged_only)
            if reasons:
                blocked.append((rel, reasons))
        if blocked:
            print("\n发现疑似敏感内容，停止提交：")
            for rel, reasons in blocked:
                print(f"  - {rel}: {', '.join(reasons)}")
            print("请先确认并从提交内容中移除真实凭据；脚本不会打印凭据值。")
            return 2
        checks = [["diff", "--cached", "--check"]] if args.staged_only else [
            ["diff", "--check"], ["diff", "--cached", "--check"]
        ]
        for diff_args in checks:
            check = git(["--literal-pathspecs", *diff_args, "--", *args.paths], root, check=False)
            if check.returncode:
                print("发现 diff whitespace 错误：")
                print(check.stdout.decode(errors="replace"))
                print(check.stderr.decode(errors="replace"))
                return 2
        ident = git(["var", "GIT_AUTHOR_IDENT"], root, check=False)
        if ident.returncode:
            print("Git 作者身份未配置，请先设置 user.name 和 user.email。", file=sys.stderr)
            return 2
        print("检查通过。仍需由 Agent 阅读完整 diff，确认改动范围和提交说明。")
        return 0
    except RuntimeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
