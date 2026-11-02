#!/usr/bin/env python3
"""List skills-check candidates in Skill directories.

    scan.py [paths ...] [--signal NAME] [--max N]

Each path is a Skill directory, a folder of Skills, or a Markdown file inside a Skill.
Candidates print under each signal as `path:line  text`. The script never edits files.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from bisect import bisect_right
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import unquote

SIGNALS = ["cross-skill", "skill-reference", "install-path", "broken-link", "missing-path", "duplicate", "denial",
           "vague-caution", "every-output", "exception-chain", "closing-summary"]

MAX_BYTES = 1_000_000
NEAR_LIMIT = 2000
TEXT_EXTS = {".md", ".mdx", ".markdown"}
IGNORED_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache", ".cache"}
SKIP_TEXT = re.compile(r"^(?:LICEN[CS]E|COPYING|NOTICE|CHANGELOG)", re.I)
SKILL_DIRS = ("references/", "assets/", "agents/", "templates/", "examples/")

FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+")
BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
SENTENCE_END = re.compile(r"[。！？；]+|[!?]+(?=\s|$)|\.(?=\s+[A-Z0-9\"“(\[`*]|\s*$)")
LINK = re.compile(r"\]\(\s*<?([^)\s>]+)>?(?:\s+[\"'][^\"']*[\"'])?\s*\)")
CODE_SPAN = re.compile(r"`([^`\n]+)`")
LINE_SUFFIX = re.compile(r":\d+(?:-\d+)?$")
PUNCT = re.compile(r"[`*_~>#|\[\](){}\"'“”‘’.,;:!?。，、；：！？（）《》【】—–-]+")
CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")

INSTALL_PATH = re.compile(r"(?:~|\$HOME|/Users/[^/\s`]+|/home/[^/\s`]+)/\.(?:claude|codex|agents|pi|cursor)"
                          r"(?:/[\w.-]+)*/skills\b")
SKILL_REFERENCE = re.compile(
    r"(?i:\b(?:see|per|follow|according\s+to|as\s+(?:defined|described)\s+in|based\s+on)\s+(?:the\s+)?`?[\w:-]+`?"
    r"\s+skill\b|\bskill'?s\s+`[^`]+\.(?:md|ya?ml|json|py)`)"
    r"|(?:参考|参照|参见|详见|见|按照?|遵循|依据|沿用|取自)\s*[\[`「]?[\w:-]+[`\]」]?\s*(?:Skill|skill)"
    r"|(?:`[\w:-]+`|[A-Za-z0-9_:-]{3,})\s*(?:Skill|skill)\s*(?:中|里)?的\s*`[^`]+\.(?:md|ya?ml|json|py)`"
    r"|该\s*(?:Skill|skill)\s*的")
DENIAL = re.compile(
    r"(?i:\b(?:does|do|did|is|are|was|were|will|would|can|could|should|must)(?:\s+not|n't)\s+(?:necessarily\s+)?"
    r"(?:prove|imply|mean|guarantee|represent|replace|constitute|establish|indicate|reflect|ensure|claim)\b"
    r"|\bcannot\s+(?:prove|guarantee|confirm|establish|replace)\b|\bnot\s+(?:a\s+|an\s+)?(?:proof|guarantee)\b"
    r"|\bnot\s+(?:a|an)\s+substitute\b|\bno\s+guarantee\b|\bfor\s+reference\s+only\b|\bnot\s+necessarily\b)"
    r"|不能证明|无法证明|不足以证明|不能说明|不代表|不等于|不意味着|不构成|不保证|无法保证|不能保证|仅供参考|不能替代|不声称|并非")
IMPERATIVE_HEAD = re.compile(r"(?:^|[;:,(—*_-])\s*$")
VAGUE = re.compile(
    r"(?i:\b(?:be\s+careful|make\s+sure|pay\s+(?:close\s+)?attention|keep\s+in\s+mind|always\s+remember|be\s+mindful"
    r"|use\s+(?:good\s+|your\s+)?judge?ment|exercise\s+caution|with\s+care|as\s+(?:appropriate|needed|necessary)"
    r"|where\s+appropriate|(?:when|if)\s+(?:appropriate|necessary|needed))\b)"
    r"|注意(?![：:])|务必|切记|谨慎|小心|适当|必要时|酌情|尽量|尽可能")
EVERY = re.compile(
    r"(?i:\b(?:every|each|all)\s+(?:repl(?:y|ies)|responses?|answers?|outputs?|reports?|messages?|turns?)\b"
    r"|\balways\s+(?:end|close|finish)\s+with\b|\balways\s+(?:include|add|append|state|mention|list)\s+(?:an?\s+|the\s+)?"
    r"(?:\w+\s+)?(?:sections?|summary|summaries|disclaimers?|caveats?|warnings?|limitations?|risks?|notes?)\b)"
    r"|每次(?:回复|输出|回答|报告|交付|提交|响应)|所有(?:回复|输出|回答|报告)|每条(?:回复|消息)"
    r"|始终(?:包含|附上|说明|列出|报告|注明)|一律(?:附上|包含|说明|注明)")
EXCEPTION = re.compile(r"(?i:\b(?:except|unless|otherwise|only\s+(?:if|when))\b)|除非|除外|例外|否则|仅当|只有在")
CONTRAST = re.compile(r"(?i:\b(?:but|however|although)\b)|但是|但|然而|不过")
SUMMARY = re.compile(r"^(?:(?i:in\s+summary|in\s+short|overall|to\s+summarize|in\s+conclusion|all\s+in\s+all"
                     r"|to\s+sum\s+up)\b|总之|综上|总的来说|总而言之|总结来说|简而言之|概括来说)")


def read(path):
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        return path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return None


def markdown_files(bases):
    seen, found = set(), []
    for base in bases:
        if base.is_file():
            paths = [base]
        else:
            paths = []
            for current, dirs, names in os.walk(base):
                dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS)
                paths += [Path(current, n) for n in sorted(names)
                          if Path(n).suffix.lower() in TEXT_EXTS and not SKIP_TEXT.match(n)]
        for path in paths:
            key = os.path.realpath(path)
            if key not in seen:
                seen.add(key)
                found.append(path)
    return found


def skill_root(path):
    """The nearest folder holding SKILL.md, or None when the file is not inside a Skill."""
    for folder in [path.parent, *path.parent.parents]:
        if (folder / "SKILL.md").is_file():
            return folder
    return None


def show(path):
    absolute, cwd = os.path.abspath(path), os.getcwd()
    return os.path.relpath(absolute, cwd) if absolute.startswith(cwd + os.sep) else absolute


def clip(text, width=110):
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1] + "…"


class Report:
    def __init__(self, only):
        self.only = set(only or SIGNALS)
        self.items = defaultdict(list)
        self.groups = defaultdict(list)
        self.notes = []

    def add(self, signal, path, line, text):
        if signal in self.only:
            self.items[signal].append((show(path), line, clip(text)))

    def group(self, signal, label, members):
        if signal in self.only:
            self.groups[signal].append((clip(label), sorted((show(p), n) for p, n in members)))

    def render(self, files, limit):
        count = sum(map(len, self.items.values())) + sum(map(len, self.groups.values()))
        out = [f"skills-check: {count} candidates in {files} files"] + self.notes
        for signal in SIGNALS:
            items, groups = sorted(self.items[signal]), self.groups[signal]
            if not items and not groups:
                continue
            out += ["", f"{signal} ({len(items) + len(groups)})"]
            out += [f"  {path}:{line}  {text}" for path, line, text in items[:limit]]
            for label, members in groups[:limit]:
                out.append(f"  {label}")
                out += [f"    {path}:{line}" for path, line in members]
            hidden = max(0, len(items) - limit) + max(0, len(groups) - limit)
            if hidden:
                out.append(f"  … {hidden} more")
        return "\n".join(out)


def md_units(text):
    """Split Markdown into (kind, first line, [(line, text)]) units, skipping frontmatter and code fences."""
    rows = text.splitlines()
    start = 0
    if rows and rows[0].strip() == "---":
        start = next((i + 1 for i in range(1, len(rows)) if rows[i].strip() in ("---", "...")), 0)
    units, current, fence = [], None, None
    for index in range(start, len(rows)):
        raw, number = rows[index], index + 1
        stripped = raw.strip()
        if fence:
            if stripped.startswith(fence):
                fence = None
            continue
        opened = FENCE.match(raw)
        if opened or not stripped or stripped.startswith("<!--") or HEADING.match(raw):
            if current:
                units.append(current)
            current = None
            if opened:
                fence = opened.group(1)
            elif HEADING.match(raw):
                units.append(("heading", number, [(number, HEADING.sub("", raw).strip())]))
            continue
        if stripped.startswith("|"):
            if not current or current[0] != "table":
                if current:
                    units.append(current)
                current = ("table", number, [])
            current[2].append((number, stripped))
            continue
        bullet = BULLET.match(raw)
        if bullet or not current or current[0] == "table":
            if current:
                units.append(current)
            current = ("item" if bullet else "para", number, [])
            stripped = raw[bullet.end():].strip() if bullet else stripped
        current[2].append((number, stripped.lstrip("> ").strip() if stripped.startswith(">") else stripped))
    if current:
        units.append(current)
    return units


def sentences(segments):
    text, offsets, numbers = "", [], []
    for number, segment in segments:
        offsets.append(len(text))
        numbers.append(number)
        text += segment + " "
    found, start = [], 0
    for m in list(SENTENCE_END.finditer(text)) + [None]:
        end = m.end() if m else len(text)
        chunk = text[start:end]
        if chunk.strip():
            at = start + len(chunk) - len(chunk.lstrip())
            found.append((numbers[bisect_right(offsets, at) - 1], chunk.strip()))
        start = end
    return found


def normalize(sentence):
    plain = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", sentence).lower()
    return " ".join(PUNCT.sub(" ", plain).split())


def weight(text):
    return len(text) + len(CJK.findall(text))


def denial(sentence):
    for m in DENIAL.finditer(sentence):
        if re.match(r"(?i)do(?:\s+not|n't)", m.group()) and IMPERATIVE_HEAD.search(sentence[:m.start()]):
            continue
        return True
    return False


def link_target(raw):
    if re.match(r"^[a-zA-Z][\w+.-]*://", raw) or raw.startswith(("mailto:", "#", "{", "$", "<")):
        return None
    target = LINE_SUFFIX.sub("", unquote(raw.split("#", 1)[0].split("?", 1)[0]))
    return target if target and ":" not in target and ("/" in target or "." in target) else None


def check_links(path, home, number, segment, rep):
    for match in INSTALL_PATH.finditer(segment):
        rep.add("install-path", path, number, match.group())
    for raw in LINK.findall(segment):
        target = link_target(raw)
        if not target:
            continue
        resolved = Path(os.path.abspath(Path(target).expanduser() if target.startswith(("/", "~"))
                                        else path.parent / target))
        if home and resolved != home and home not in resolved.parents:
            rep.add("cross-skill", path, number, f"({raw})")
        elif not resolved.exists():
            rep.add("broken-link", path, number, f"({raw})")
    if not home:
        return
    for span in CODE_SPAN.findall(segment):
        text = LINE_SUFFIX.sub("", span.strip())
        if text.startswith(SKILL_DIRS) and "." in text.rsplit("/", 1)[-1] and " " not in text and not any(c in text for c in "<>*{}$"):
            if not (home / text).exists():
                rep.add("missing-path", path, number, f"`{span}`")


def duplicates(entries, rep):
    exact = defaultdict(list)
    for path, number, original, key in entries:
        if weight(key) >= 30:
            exact[key].append((path, number, original))
    for members in exact.values():
        if len(members) > 1:
            rep.group("duplicate", f"×{len(members)}: {members[0][2]}", [(p, n) for p, n, _ in members])
    keys = sorted((k for k in exact if weight(k) >= 40), key=len)
    if len(keys) > NEAR_LIMIT:
        rep.notes.append(f"near-duplicate check skipped: {len(keys)} sentences exceed {NEAR_LIMIT}")
        return
    matcher = SequenceMatcher(autojunk=False)
    for i, a in enumerate(keys):
        matcher.set_seq2(a)
        for b in keys[i + 1:]:
            if len(b) > len(a) * 1.25:
                break
            matcher.set_seq1(b)
            if matcher.real_quick_ratio() >= 0.85 and matcher.quick_ratio() >= 0.85 and matcher.ratio() >= 0.85:
                first, second = exact[a][0], exact[b][0]
                rep.group("duplicate", f"{matcher.ratio():.0%} similar: {first[2]}",
                          [(first[0], first[1]), (second[0], second[1])])


def scan(paths, rep):
    files = markdown_files(paths)
    entries = []
    for path in files:
        text = read(path)
        if text is None:
            continue
        home = skill_root(path)
        home = Path(os.path.abspath(home)) if home else None
        section = []
        for kind, start, segments in md_units(text) + [("heading", 0, [])]:
            for number, segment in segments:
                check_links(path, home, number, segment, rep)
                if SKILL_REFERENCE.search(segment):
                    rep.add("skill-reference", path, number, segment)
            if kind == "heading":
                if section:
                    found = sentences(section[-1])
                    for number, sentence in found[:1] + found[-1:]:
                        if SUMMARY.match(sentence):
                            rep.add("closing-summary", path, number, sentence)
                            break
                section = []
                continue
            if kind == "table":
                continue
            section.append(segments)
            joined = " ".join(s for _, s in segments)
            exceptions = len(EXCEPTION.findall(joined))
            if exceptions >= 2 and exceptions + len(CONTRAST.findall(joined)) >= 3:
                rep.add("exception-chain", path, start, joined)
            for number, sentence in sentences(segments):
                entries.append((path, number, sentence, normalize(sentence)))
                if denial(sentence):
                    rep.add("denial", path, number, sentence)
                for pattern, signal in ((VAGUE, "vague-caution"), (EVERY, "every-output")):
                    if pattern.search(sentence):
                        rep.add(signal, path, number, sentence)
    duplicates(entries, rep)
    return files


def main(argv=None):
    parser = argparse.ArgumentParser(description="List skills-check candidates. Never edits files.")
    parser.add_argument("paths", nargs="*", default=["."], help="Skill directories or files (default: .)")
    parser.add_argument("--signal", action="append", default=[], metavar="NAME", help="show only this signal; repeatable")
    parser.add_argument("--max", type=int, default=30, metavar="N", help="candidates shown per signal (default: 30)")
    args = parser.parse_args(argv)
    unknown = sorted(set(args.signal) - set(SIGNALS))
    if unknown:
        parser.error(f"unknown signal: {', '.join(unknown)}; choose from {', '.join(SIGNALS)}")
    paths = [Path(p).expanduser() for p in args.paths]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        parser.error("not found: " + ", ".join(missing))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    report = Report(args.signal)
    files = scan(paths, report)
    print(report.render(len(files), max(args.max, 1)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
