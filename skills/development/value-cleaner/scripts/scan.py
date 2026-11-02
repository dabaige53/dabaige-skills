#!/usr/bin/env python3
"""List value-cleaner candidates in code, tests, rules, or docs.

    scan.py {code,test,rule,docs} [paths ...] [--root DIR] [--signal NAME] [--max N]

Candidates print under each signal as `path:line  text`. The script never edits files.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
from bisect import bisect_right
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import unquote

SIGNALS = {
    "code": ["broad-except", "repeated-guard", "unreferenced", "test-only", "single-implementation", "commented-code"],
    "test": ["no-assertion", "weak-assertion", "mock-only", "duplicate-body", "large-parametrize", "skipped",
             "sleep", "unused-fixture", "unreferenced-fixture", "large-snapshot", "orphan-snapshot"],
    "rule": ["duplicate", "denial", "vague-caution", "every-output", "exception-chain", "closing-summary",
             "broken-link", "missing-path"],
    "docs": ["duplicate", "denial", "closing-summary", "stale-status", "todo", "broken-link", "missing-path"],
}

MAX_BYTES = 1_000_000
PARAM_CASES = 8
SNAPSHOT_LINES = 300
NEAR_LIMIT = 2000

IGNORED_DIRS = {
    ".git", ".hg", ".svn", ".idea", ".vscode", ".venv", "venv", "env", "node_modules", "vendor", "dist",
    "build", "out", "target", "coverage", "htmlcov", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    ".nox", ".gradle", ".cache", "__pycache__", ".next", ".turbo",
}
JS_EXTS = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}
HASH_EXTS = {".py", ".rb", ".sh", ".bash", ".zsh", ".pl", ".pm", ".r", ".ex", ".exs"}
SLASH_EXTS = JS_EXTS | {".c", ".cc", ".cpp", ".cs", ".dart", ".fs", ".fsx", ".go", ".groovy", ".h", ".hpp",
                        ".java", ".kt", ".kts", ".m", ".mm", ".php", ".rs", ".scala", ".sol", ".swift"}
CODE_EXTS = HASH_EXTS | SLASH_EXTS | {".lua", ".vb"}
TEXT_EXTS = {".md", ".mdx", ".markdown", ".mdc", ".rst", ".txt", ".adoc"}
RULE_NAMES = {".cursorrules", ".windsurfrules", ".clinerules"}
SKIP_TEXT = re.compile(r"^(?:LICEN[CS]E|COPYING|NOTICE|CHANGELOG|HISTORY|requirements)", re.I)
CORPUS_EXTS = CODE_EXTS | TEXT_EXTS | {".json", ".yaml", ".yml", ".toml", ".html", ".vue", ".svelte", ".xml",
                                       ".cfg", ".ini", ".gradle", ".properties", ".erb", ".j2", ".jinja"}
CORPUS_NAMES = RULE_NAMES | {"Makefile", "Dockerfile", "Justfile", "Procfile"}
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


# ---------- shared ----------

def read(path):
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


def walk(bases, accept):
    """Files under the given paths that pass `accept`; explicitly named files always pass."""
    seen, found = set(), []
    for base in bases:
        if base.is_file():
            paths = [base]
        else:
            paths = []
            for current, dirs, names in os.walk(base):
                dirs[:] = sorted(d for d in dirs
                                 if d not in IGNORED_DIRS and not os.path.islink(os.path.join(current, d)))
                paths += [Path(current, n) for n in sorted(names)
                          if not os.path.islink(os.path.join(current, n)) and accept(Path(current, n))]
        for path in paths:
            key = os.path.realpath(path)
            if key not in seen:
                seen.add(key)
                found.append(path)
    return found


def rel(root, path):
    absolute, base = os.path.abspath(path), os.path.abspath(root)
    return Path(os.path.relpath(absolute, base)) if absolute.startswith(base + os.sep) else Path(absolute)


def show(path):
    absolute, cwd = os.path.abspath(path), os.getcwd()
    return os.path.relpath(absolute, cwd) if absolute.startswith(cwd + os.sep) else absolute


def git_root(path):
    folder = path if path.is_dir() else path.parent
    try:
        result = subprocess.run(["git", "-C", str(folder), "rev-parse", "--show-toplevel"],
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return folder
    top = result.stdout.strip()
    return Path(top) if result.returncode == 0 and top else folder


class Lines:
    def __init__(self, text):
        self.rows = text.splitlines()
        self.starts = [0] + [m.end() for m in re.finditer(r"\n", text)]

    def at(self, offset):
        return bisect_right(self.starts, offset)

    def __getitem__(self, number):
        return self.rows[number - 1] if 0 < number <= len(self.rows) else ""


def clip(text, width=110):
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1] + "…"


def closing_bracket(text, start):
    """Index of the bracket that closes the one at `start`, skipping strings and comments."""
    depth, i, end = 0, start, len(text)
    while i < end:
        char = text[i]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth == 0:
                return i
        elif char in "'\"`":
            i += 1
            while i < end and text[i] != char and (char == "`" or text[i] != "\n"):
                i += 2 if text[i] == "\\" else 1
        elif text.startswith("//", i):
            i = text.find("\n", i)
            i = end if i < 0 else i
        elif text.startswith("/*", i):
            i = text.find("*/", i + 2)
            i = end if i < 0 else i + 1
        i += 1
    return end - 1


class Report:
    def __init__(self, obj, only):
        self.obj = obj
        self.only = set(only or SIGNALS[obj])
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
        out = [f"{self.obj}: {count} candidates in {files} files"] + self.notes
        for signal in SIGNALS[self.obj]:
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


def name_of(node):
    node = node.func if isinstance(node, ast.Call) else node
    return node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "")


# ---------- test file classification ----------

TEST_DIRS = {"test", "tests", "testing", "__tests__", "spec", "specs", "e2e", "integration-test", "integration-tests",
             "integration_test", "integration_tests", "unit-test", "unit-tests", "unit_test", "unit_tests"}
SUPPORT_DIRS = {"fixture", "fixtures", "factory", "factories", "fake", "fakes", "mock", "mocks", "stub", "stubs",
                "snapshot", "snapshots", "golden", "goldens"}
DATA_DIRS = {"testdata", "test-data", "test_data", "__fixtures__", "__mocks__"}
SNAPSHOT_EXTS = {".snap", ".golden", ".approved", ".received", ".ambr"}
TEST_DOC_TOKENS = {"test", "tests", "testing", "qa", "quality", "coverage", "e2e", "test-plan", "test-strategy",
                   "test-matrix", "testing-guide"}
TEST_CONFIG = re.compile(r"^(?:\.coveragerc|pytest\.ini|tox\.ini|noxfile\.py|codecov\.ya?ml|phpunit\.xml(?:\.dist)?"
                         r"|phpunit\..+\.xml|(?:jest|vitest|playwright|cypress)\.config\..+|karma\.conf\..+"
                         r"|protractor\.conf\..+|\.nycrc.*)$", re.I)
TEST_NAME = re.compile(r"^test[_-].+|.+[_-](?:test|tests|spec|specs)$|.+\.(?:test|spec)$|.+(?:Test|Tests|Spec|Specs)$")


def test_kind(path):
    """Classify a root-relative path as code, support, snapshot, config, or doc; None for non-test files."""
    dirs = [part.lower() for part in path.parts[:-1]]
    name, suffix = path.name, path.suffix.lower()
    in_tests = any(d in TEST_DIRS for d in dirs)
    if TEST_CONFIG.match(name):
        return "config"
    if suffix in SNAPSHOT_EXTS or "__snapshots__" in dirs or re.search(r"\.(?:golden|approved|received)\.", name.lower()):
        return "snapshot"
    if any(d in DATA_DIRS for d in dirs) or (in_tests and any(d in SUPPORT_DIRS for d in dirs)):
        return "support"
    if suffix in TEXT_EXTS:
        stem = path.stem.lower().replace("_", "-").replace(" ", "-")
        if in_tests or any(d in {"qa", "quality", "coverage"} for d in dirs) or any(
                stem == t or stem.startswith(t + "-") or stem.endswith("-" + t) for t in TEST_DOC_TOKENS):
            return "doc"
        return None
    if suffix in CODE_EXTS:
        if name == "conftest.py":
            return "support"
        return "code" if in_tests or TEST_NAME.match(path.stem) else None
    return "support" if in_tests else None


# ---------- code ----------

BROAD = {"Exception", "BaseException"}
PLAIN_DECORATORS = {"property", "staticmethod", "classmethod", "cached_property", "abstractmethod", "override",
                    "cache", "lru_cache", "wraps", "setter", "getter", "deleter"}
ENTRY_NAME = re.compile(r"^(?:__\w+__|_?[Tt]est\w*|setUp\w*|tearDown\w*|setup\w*|teardown\w*|main|init|initialize"
                        r"|new|default|constructor|render|visit_\w+|generic_visit|pytest_\w+|Benchmark\w*|Example\w*"
                        r"|Fuzz\w*|to_\w+|method_missing|respond_to_missing)$")
JS_DEFS = (
    re.compile(r"^[ \t]*(?:export[ \t]+)?(?:async[ \t]+)?function\b[ \t]*\*?[ \t]*([A-Za-z_]\w*)", re.M),
    re.compile(r"^[ \t]*(?:export[ \t]+)?(?:const|let|var)[ \t]+([A-Za-z_]\w*)[ \t]*(?::[^=\n]+)?=[ \t]*"
               r"(?:async[ \t]+)?(?:function\b|\([^)\n]*\)[ \t]*(?::[^=\n]+)?=>|[A-Za-z_]\w*[ \t]*=>)", re.M),
    re.compile(r"^[ \t]*(?:export[ \t]+)?(?:abstract[ \t]+)?class[ \t]+([A-Za-z_]\w*)", re.M),
)
DEFS = {
    **{ext: JS_DEFS for ext in JS_EXTS},
    ".go": (re.compile(r"^func[ \t]+(?:\([^)]*\)[ \t]*)?([A-Za-z_]\w*)[ \t]*[\[(]", re.M),),
    ".rs": (re.compile(r"^[ \t]*(?:pub(?:\([^)]*\))?[ \t]+)?(?:const[ \t]+)?(?:async[ \t]+)?(?:unsafe[ \t]+)?"
                       r"fn[ \t]+([A-Za-z_]\w*)", re.M),),
    ".rb": (re.compile(r"^[ \t]*def[ \t]+(?:self\.)?([A-Za-z_]\w*)", re.M),),
}
ABSTRACT = re.compile(r"^[ \t]*(?:export[ \t]+)?(?:public[ \t]+)?abstract[ \t]+class[ \t]+([A-Za-z_]\w*)", re.M)
INTERFACE = re.compile(r"^[ \t]*(?:export[ \t]+)?(?:public[ \t]+)?interface[ \t]+([A-Za-z_]\w*)", re.M)
PY_BASES = re.compile(r"^[ \t]*class[ \t]+\w+[ \t]*\(([^)]*)\)", re.M)
EXTENDS = re.compile(r"\bextends[ \t]+([A-Za-z_][\w.]*)")
IMPLEMENTS = re.compile(r"\bimplements[ \t]+([^{;]+?)[ \t]*\{")
EMPTY_CATCH = re.compile(r"\bcatch\b[ \t]*(?:\([^)]*\))?[ \t]*\{\s*(?:(?://[^\n]*|/\*[\s\S]*?\*/)\s*)*\}")
DEFAULT_CATCH = re.compile(r"\.catch\(\s*(?:\(\s*\w*\s*\)|\w+)\s*=>\s*(?:\{\s*\}|null|undefined|false|true|0|\[\]|''|\"\")\s*\)")
GO_SWALLOW = re.compile(r"\bif[ \t]+err[ \t]*!=[ \t]*nil[ \t]*\{\s*(?:return(?:[ \t]+[^\n{}]*,[ \t]*nil|[ \t]+nil)?|continue)\s*\}")
C_GUARD = re.compile(r"\bif\s*\((?P<cond>[^\n{};]{1,160}?)\)\s*\{?\s*throw\b")
GO_GUARD = re.compile(r"^[ \t]*if[ \t]+(?P<cond>[^\n{]{1,160}?)[ \t]*\{\s*return\b[^\n]*(?:errors\.New|fmt\.Errorf)", re.M)
CODE_LIKE = re.compile(r"""^(?:
    (?:def|class|return|import|from|elif|else|try|except|finally|raise|with|const|let|var|function|export|func|fn
       |public|private|protected|await|yield)\b
  | (?:if|for|while|switch)\b.*[:{)]\s*$
  | [\w.\[\]'"]+\s*(?:=|\+=|-=|\*=|/=|:=)\s*\S
  | [\w.$]+\(.*\)\s*;?\s*$
  | [{}()\[\]]+;?\s*$
  | .*;\s*$
)""", re.X)
HASH_COMMENT = re.compile(r"^\s*#(?![!#\[])\s?(.*)$")
SLASH_COMMENT = re.compile(r"^\s*//(?![/!])\s?(.*)$")
DIRECTIVE = re.compile(r"^(?:type:|noqa|pragma|fmt:|-\*-|region|endregion|eslint|@ts-|prettier-|go:|nolint|istanbul"
                       r"|c8 |tslint|biome-ignore|deno-lint|swiftlint|NOSONAR)", re.I)


def broad(node):
    if node is None:
        return True
    if isinstance(node, ast.Tuple):
        return any(broad(e) for e in node.elts)
    return name_of(node) in BROAD


def py_definitions(tree):
    bodies = [tree.body]
    while bodies:
        for node in bodies.pop():
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                yield node
                if isinstance(node, ast.ClassDef):
                    bodies.append(node.body)


def py_abstract(cls):
    if any(name_of(b) == "ABC" for b in cls.bases):
        return True
    if any(k.arg == "metaclass" and name_of(k.value) == "ABCMeta" for k in cls.keywords):
        return True
    return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and any(name_of(d) == "abstractmethod" for d in n.decorator_list) for n in cls.body)


def code_corpus(root):
    """Identifier counts across the root, the same outside test files, and implementation counts per base."""
    total, outside, impls = Counter(), Counter(), Counter()
    for path in walk([root], lambda p: p.suffix.lower() in CORPUS_EXTS or p.name in CORPUS_NAMES):
        text = read(path)
        if text is None:
            continue
        tokens = IDENT.findall(text)
        total.update(tokens)
        if test_kind(rel(root, path)) is None:
            outside.update(tokens)
        suffix = path.suffix.lower()
        if suffix == ".py":
            bases = [b.strip() for group in PY_BASES.findall(text) for b in group.split(",") if "=" not in b]
            impls.update(re.split(r"[\[(]", b)[0].split(".")[-1] for b in bases if b)
        elif suffix in SLASH_EXTS:
            impls.update(name.split(".")[-1] for name in EXTENDS.findall(text))
            impls.update(name.strip().split(".")[-1] for group in IMPLEMENTS.findall(text)
                         for name in re.sub(r"<[^>]*>", "", group).split(","))
    return total, outside, impls


def commented_code(path, lines, pattern, rep):
    block = []

    def flush():
        code = [text for _, text in block if CODE_LIKE.match(text)]
        if len(code) >= 3 and len(code) >= 0.6 * len(block):
            rep.add("commented-code", path, block[0][0], f"{len(block)} lines: {block[0][1]}")
        block.clear()

    for number, row in enumerate(lines.rows, 1):
        m = pattern.match(row)
        if m and not DIRECTIVE.match(m.group(1).strip()):
            if m.group(1).strip():
                block.append((number, m.group(1).strip()))
        else:
            flush()
    flush()


def scan_code(paths, root, rep):
    files = walk(paths, lambda p: p.suffix.lower() in CODE_EXTS and test_kind(rel(root, p)) is None)
    total, outside, impls = code_corpus(root)
    guards = defaultdict(list)
    for path in files:
        text = read(path)
        if text is None:
            continue
        lines, suffix = Lines(text), path.suffix.lower()
        defs, abstracts = [], []
        if suffix == ".py":
            try:
                tree = ast.parse(text)
            except (SyntaxError, ValueError):
                tree = None
            if tree is not None:
                for node in ast.walk(tree):
                    if isinstance(node, ast.ExceptHandler) and broad(node.type) and not any(
                            isinstance(n, ast.Raise) for s in node.body for n in ast.walk(s)):
                        rep.add("broad-except", path, node.lineno, lines[node.lineno])
                    elif isinstance(node, ast.If) and len(node.body) == 1 and isinstance(node.body[0], ast.Raise):
                        cond = " ".join(ast.unparse(node.test).split())
                        if "__name__" not in cond:
                            guards[cond].append((path, node.lineno))
                for node in py_definitions(tree):
                    if isinstance(node, ast.ClassDef) and py_abstract(node):
                        abstracts.append((node.lineno, node.name, True))
                    if not ENTRY_NAME.match(node.name) and all(
                            name_of(d) in PLAIN_DECORATORS for d in node.decorator_list):
                        defs.append((node.lineno, node.name))
        else:
            for pattern in DEFS.get(suffix, ()):
                for m in pattern.finditer(text):
                    if suffix == ".rs" and re.search(r"#\[(?:\w+::)?test\b", text[max(0, m.start() - 120):m.start()]):
                        continue
                    if not ENTRY_NAME.match(m.group(1)):
                        defs.append((lines.at(m.start(1)), m.group(1)))
            if suffix in SLASH_EXTS:
                for pattern in (EMPTY_CATCH, DEFAULT_CATCH, GO_SWALLOW):
                    for m in pattern.finditer(text):
                        rep.add("broad-except", path, lines.at(m.start()), lines[lines.at(m.start())])
                for pattern in (C_GUARD, GO_GUARD):
                    for m in pattern.finditer(text):
                        cond = " ".join(m.group("cond").split())
                        if cond != "err != nil":
                            guards[cond].append((path, lines.at(m.start())))
                abstracts += [(lines.at(m.start(1)), m.group(1), True) for m in ABSTRACT.finditer(text)]
                abstracts += [(lines.at(m.start(1)), m.group(1), False) for m in INTERFACE.finditer(text)]
        for line, name in defs:
            if total[name] <= 1:
                rep.add("unreferenced", path, line, lines[line])
            elif outside[name] <= 1:
                rep.add("test-only", path, line, lines[line])
        for line, name, is_abstract in abstracts:
            count = impls[name]
            if count == 1 or (is_abstract and count == 0):
                rep.add("single-implementation", path, line, f"{lines[line].strip()}  [implementations: {count}]")
        comment = HASH_COMMENT if suffix in HASH_EXTS else SLASH_COMMENT if suffix in SLASH_EXTS else None
        if comment:
            commented_code(path, lines, comment, rep)
    for cond, members in guards.items():
        if len(members) > 1:
            rep.group("repeated-guard", f"×{len(members)}: if {cond}", members)
    return files


# ---------- test ----------

MOCK_ASSERTS = {"assert_called", "assert_called_once", "assert_called_with", "assert_called_once_with",
                "assert_any_call", "assert_has_calls", "assert_not_called", "assert_awaited", "assert_awaited_once",
                "assert_awaited_with", "assert_awaited_once_with", "assert_any_await", "assert_has_awaits",
                "assert_not_awaited"}
CHECK_NAME = re.compile(r"assert|raises|expect|fail|verify", re.I)
JS_TEST = re.compile(r"(?<![\w.$])(?P<kind>x?it|x?test|x?describe|fit|fdescribe)"
                     r"(?P<mod>\.(?:only|skip|todo|concurrent|failing))?\s*\(")
JS_CHECK = re.compile(r"\bexpect(?:TypeOf)?\s*[(.]|\bassert\w*\s*[(.]|\.should\b|\bshould\.|\bt\.\w+\s*\(|\bverify\w*\s*\(")
OTHER_CHECK = re.compile(r"\bassert\w*\s*[(.]|\.should\b|\bshould\.|\bt\.\w+\s*\(|\bverify\w*\s*\(")
JS_MATCHER = re.compile(r"\.((?:not\.)?(?:resolves\.|rejects\.)?(?:not\.)?to[A-Z]\w*)\s*\(")
JS_SLEEP = re.compile(r"\bsetTimeout\s*\(|\bsleep\s*\(|\.waitForTimeout\s*\(|\bcy\.wait\s*\(\s*\d|\bdelay\s*\(\s*\d")
WEAK_JS = {"toBeDefined", "toBeTruthy", "toBeInstanceOf", "not.toBeNull", "not.toBeUndefined", "not.toBeFalsy",
           "not.toBeNaN"}
MOCK_JS = {"toHaveBeenCalled", "toHaveBeenCalledTimes", "toHaveBeenCalledWith", "toHaveBeenLastCalledWith",
           "toHaveBeenNthCalledWith", "toBeCalled", "toBeCalledTimes", "toBeCalledWith", "not.toHaveBeenCalled",
           "not.toBeCalled"}
TEST_TITLE = re.compile(r"\s*(['\"`])(?:\\.|(?!\1)[\s\S])*?\1\s*,?")
C_COMMENT = re.compile(r"//[^\n]*|/\*[\s\S]*?\*/")
GO_TEST = re.compile(r"^func[ \t]+(Test\w*)[ \t]*\([ \t]*\w+[ \t]+\*testing\.T[ \t]*\)[^{\n]*\{", re.M)
GO_CHECK = re.compile(r"\bt\.(?:Error|Errorf|Fatal|Fatalf|Fail|FailNow)\s*\(|\b(?:assert|require|is|qt|check|must)\.\w+\s*\("
                      r"|\bcmp\.Diff\s*\(")
GO_SKIP = re.compile(r"\bt\.Skip(?:f|Now)?\s*\(")
GO_SLEEP = re.compile(r"\btime\.Sleep\s*\(")
OTHER_SKIP = re.compile(r"@Disabled\b|@Ignore\b|#\[ignore\b|\[Ignore\b|\bSkip\s*=\s*\"|markTestSkipped\s*\("
                        r"|^\s*(?:xit|xdescribe|pending|skip)\b", re.M)
OTHER_SLEEP = re.compile(r"\bThread\.sleep\s*\(|\bthread::sleep\s*\(|\bTask\.Delay\s*\(|\busleep\s*\(|^\s*sleep[ \t(]+\d",
                         re.M)


def weak_assert(node):
    test = node.test
    if isinstance(test, (ast.Name, ast.Attribute)):
        return True
    if isinstance(test, ast.Call):
        return name_of(test) in {"isinstance", "hasattr", "callable"}
    if isinstance(test, ast.Compare) and len(test.ops) == 1:
        op, right = test.ops[0], test.comparators[0]
        if isinstance(op, ast.IsNot) and isinstance(right, ast.Constant) and right.value is None:
            return True
        if isinstance(test.left, ast.Call) and name_of(test.left) == "len" and isinstance(right, ast.Constant):
            return (isinstance(op, (ast.Gt, ast.NotEq)) and right.value == 0) or (
                isinstance(op, ast.GtE) and right.value == 1)
    return False


def weak_call(call):
    name = name_of(call)
    if name in {"assertIsNotNone", "assertIsInstance"}:
        return True
    return name == "assertTrue" and bool(call.args) and isinstance(call.args[0], (ast.Name, ast.Attribute))


def py_test_functions(tree):
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            yield node, []
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test"):
                    yield item, node.decorator_list


def scan_python_tests(path, text, lines, rep, bodies, fixtures):
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for deco in node.decorator_list:
                autouse = isinstance(deco, ast.Call) and any(
                    k.arg == "autouse" and isinstance(k.value, ast.Constant) and k.value.value for k in deco.keywords)
                if name_of(deco) == "fixture" and not autouse:
                    fixtures.append((path, node.lineno, node.name))
    for func, class_decorators in py_test_functions(tree):
        line, here = func.lineno, lines[func.lineno]
        decorators = list(func.decorator_list) + list(class_decorators)
        if any(re.search(r"skip|xfail", name_of(d), re.I) for d in decorators) or any(
                isinstance(s, ast.Expr) and isinstance(s.value, ast.Call) and name_of(s.value) in {"skip", "skipTest"}
                for s in func.body[:2]):
            rep.add("skipped", path, line, here)
        for deco in func.decorator_list:
            if (isinstance(deco, ast.Call) and name_of(deco) == "parametrize" and len(deco.args) > 1
                    and isinstance(deco.args[1], (ast.List, ast.Tuple)) and len(deco.args[1].elts) >= PARAM_CASES):
                rep.add("large-parametrize", path, deco.lineno, f"{len(deco.args[1].elts)} cases: {here}")
        body = func.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(
                body[0].value.value, str):
            body = body[1:]
        nodes = [n for s in body for n in ast.walk(s)]
        asserts = [n for n in nodes if isinstance(n, ast.Assert)]
        checks = [n for n in nodes if isinstance(n, ast.Call) and CHECK_NAME.search(name_of(n))]
        mocks = [c for c in checks if name_of(c) in MOCK_ASSERTS]
        if not asserts and not checks:
            rep.add("no-assertion", path, line, here)
        elif not asserts and len(mocks) == len(checks):
            rep.add("mock-only", path, line, here)
        elif not mocks and all(map(weak_assert, asserts)) and all(map(weak_call, checks)):
            rep.add("weak-assertion", path, line, here)
        sleeps = [n for n in nodes if isinstance(n, ast.Call) and name_of(n) == "sleep"]
        if sleeps:
            rep.add("sleep", path, sleeps[0].lineno, lines[sleeps[0].lineno])
        if any(not isinstance(s, ast.Pass) and not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
               for s in body):
            bodies["\n".join(ast.dump(s) for s in body)].append((path, line, func.name))


def scan_js_tests(path, text, lines, rep, bodies):
    for m in JS_TEST.finditer(text):
        kind, mod = m.group("kind"), m.group("mod") or ""
        line = lines.at(m.start())
        if kind[0] in "xf" or mod in (".only", ".skip", ".todo"):
            rep.add("skipped", path, line, lines[line])
        if kind.endswith("describe") or mod == ".todo":
            continue
        close = closing_bracket(text, m.end() - 1)
        title = TEST_TITLE.match(text, m.end(), close)
        offset = title.end() if title else m.end()
        body = text[offset:close]
        matchers = {re.sub(r"(?:resolves|rejects)\.", "", x) for x in JS_MATCHER.findall(body)}
        if not JS_CHECK.search(body):
            rep.add("no-assertion", path, line, lines[line])
        elif matchers and not OTHER_CHECK.search(body) and matchers <= MOCK_JS:
            rep.add("mock-only", path, line, lines[line])
        elif matchers and not OTHER_CHECK.search(body) and matchers <= WEAK_JS:
            rep.add("weak-assertion", path, line, lines[line])
        sleep = JS_SLEEP.search(body)
        if sleep:
            number = lines.at(offset + sleep.start())
            rep.add("sleep", path, number, lines[number])
        key = re.sub(r"\s+", "", C_COMMENT.sub("", body))
        if len(key) >= 20:
            bodies[key].append((path, line, clip(lines[line], 60)))


def scan_go_tests(path, text, lines, rep, bodies):
    for m in GO_TEST.finditer(text):
        line, start = lines.at(m.start()), m.end() - 1
        body = text[start:closing_bracket(text, start) + 1]
        for pattern, signal in ((GO_SKIP, "skipped"), (GO_SLEEP, "sleep")):
            hit = pattern.search(body)
            if hit:
                number = lines.at(start + hit.start())
                rep.add(signal, path, number, lines[number])
        if not GO_CHECK.search(body):
            rep.add("no-assertion", path, line, lines[line])
        key = re.sub(r"\s+", "", C_COMMENT.sub("", body))
        if len(key) >= 20:
            bodies[key].append((path, line, m.group(1)))


def scan_test(paths, root, rep):
    files = walk(paths, lambda p: test_kind(rel(root, p)) is not None)
    kinds = {}
    for path in files:
        suffix = path.suffix.lower()
        kinds[path] = test_kind(rel(root, path)) or (
            "code" if suffix in CODE_EXTS else "doc" if suffix in TEXT_EXTS else "support")
    counts = Counter(kinds.values())
    if counts:
        rep.notes.append("files: " + ", ".join(f"{counts[k]} {k}" for k in ("code", "support", "snapshot", "config", "doc")
                                               if counts[k]))
    docs = [show(p) for p, k in kinds.items() if k == "doc"]
    if docs:
        rep.notes.append("test docs: " + ", ".join(docs[:10]) + (f" and {len(docs) - 10} more" if len(docs) > 10 else ""))
    test_texts = [t for p in walk([root], lambda p: p.suffix.lower() in CODE_EXTS
                                  and test_kind(rel(root, p)) in ("code", "support", "config")) if (t := read(p))]
    tokens = Counter(token for t in test_texts for token in IDENT.findall(t))
    bodies, fixtures = defaultdict(list), []
    for path, kind in kinds.items():
        suffix = path.suffix.lower()
        if kind == "snapshot":
            text = read(path)
            size = text.count("\n") + 1 if text is not None else 0
            if text is None and path.stat().st_size > MAX_BYTES:
                rep.add("large-snapshot", path, 1, "over 1 MB")
            elif size > SNAPSHOT_LINES:
                rep.add("large-snapshot", path, 1, f"{size} lines")
            if path.parent.name == "__snapshots__":
                source = path.parent.parent / (path.stem + ".py" if suffix == ".ambr" else path.stem)
                if not source.exists():
                    rep.add("orphan-snapshot", path, 1, f"{show(source)} does not exist")
            continue
        if kind == "support" and suffix not in CODE_EXTS:
            key = path.stem if len(path.stem) >= 4 else path.name
            if not any(key in t for t in test_texts):
                rep.add("unreferenced-fixture", path, 1, path.name)
            continue
        text = read(path) if kind in ("code", "support") and suffix in CODE_EXTS else None
        if text is None:
            continue
        lines = Lines(text)
        if suffix == ".py":
            scan_python_tests(path, text, lines, rep, bodies, fixtures)
        elif kind != "code":
            continue
        elif suffix in JS_EXTS:
            scan_js_tests(path, text, lines, rep, bodies)
        elif suffix == ".go":
            scan_go_tests(path, text, lines, rep, bodies)
        else:
            for pattern, signal in ((OTHER_SKIP, "skipped"), (OTHER_SLEEP, "sleep")):
                for m in pattern.finditer(text):
                    number = lines.at(m.start())
                    rep.add(signal, path, number, lines[number])
    for path, line, name in fixtures:
        if tokens[name] <= 1:
            rep.add("unused-fixture", path, line, f"fixture {name}")
    for members in bodies.values():
        if len(members) > 1:
            rep.group("duplicate-body", f"×{len(members)}: " + ", ".join(label for _, _, label in members[:4]),
                      [(p, n) for p, n, _ in members])
    return files


# ---------- rule and docs ----------

FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+")
BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
TABLE_RULE = re.compile(r"^\|?[\s:|-]+\|?$")
SENTENCE_END = re.compile(r"[。！？；]+|[!?]+(?=\s|$)|\.(?=\s+[A-Z0-9\"“(\[`*]|\s*$)")
LINK = re.compile(r"\]\(\s*<?([^)\s>]+)>?(?:\s+[\"'][^\"']*[\"'])?\s*\)")
CODE_SPAN = re.compile(r"`([^`\n]+)`")
LINE_SUFFIX = re.compile(r":\d+(?:-\d+)?$")
PATH_CHARS = re.compile(r"^[\w.@~/+-]+$")
PUNCT = re.compile(r"[`*_~>#|\[\](){}\"'“”‘’.,;:!?。，、；：！？（）《》【】—–-]+")
CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
DENIAL = re.compile(
    r"(?i:\b(?:does|do|did|is|are|was|were|will|would|can|could|should|must)(?:\s+not|n't)\s+(?:necessarily\s+)?"
    r"(?:prove|imply|mean|guarantee|represent|replace|constitute|establish|indicate|reflect|ensure|claim)\b"
    r"|\bcannot\s+(?:prove|guarantee|confirm|establish|replace)\b|\bnot\s+(?:a\s+|an\s+)?(?:proof|guarantee)\b"
    r"|\bnot\s+(?:a|an)\s+substitute\b"
    r"|\bno\s+guarantee\b|\bfor\s+reference\s+only\b|\bnot\s+necessarily\b)"
    r"|不能证明|无法证明|不足以证明|不能说明|不代表|不等于|不意味着|不构成|不保证|无法保证|不能保证|仅供参考|不能替代|不声称|并非")
VAGUE = re.compile(
    r"(?i:\b(?:be\s+careful|make\s+sure|pay\s+(?:close\s+)?attention|keep\s+in\s+mind|always\s+remember|be\s+mindful"
    r"|use\s+(?:good\s+|your\s+)?judge?ment|exercise\s+caution|with\s+care|as\s+(?:appropriate|needed|necessary)"
    r"|where\s+appropriate|(?:when|if)\s+(?:appropriate|necessary|needed))\b)"
    r"|注意(?![：:])|务必|切记|谨慎|小心|适当|必要时|酌情|尽量|尽可能")
EVERY = re.compile(
    r"(?i:\b(?:every|each|all)\s+(?:repl(?:y|ies)|responses?|answers?|outputs?|reports?|messages?|turns?|deliverables?)\b"
    r"|\balways\s+(?:end|close|finish)\s+with\b|\balways\s+(?:include|add|append|state|mention|list)\s+(?:an?\s+|the\s+)?"
    r"(?:\w+\s+)?(?:sections?|summary|summaries|disclaimers?|caveats?|warnings?|limitations?|risks?|notes?)\b)"
    r"|每次(?:回复|输出|回答|报告|交付|提交|对话|响应|任务)|所有(?:回复|输出|回答|报告)|每条(?:回复|消息)"
    r"|始终(?:包含|附上|说明|列出|报告|注明)|一律(?:附上|包含|说明|注明)")
EXCEPTION = re.compile(r"(?i:\b(?:except|unless|otherwise|only\s+(?:if|when))\b)|除非|除外|例外|否则|仅当|只有在")
CONTRAST = re.compile(r"(?i:\b(?:but|however|although)\b)|但是|但|然而|不过")
IMPERATIVE_HEAD = re.compile(r"(?:^|[;:,(—*_-])\s*$")
SUMMARY = re.compile(r"^(?:(?i:in\s+summary|in\s+short|overall|to\s+summarize|in\s+conclusion|all\s+in\s+all"
                     r"|to\s+sum\s+up|in\s+a\s+nutshell)\b|总之|综上|总的来说|总而言之|总结来说|简而言之|概括来说)")
STATUS = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,3}(?:\.\d+)?\s?%|[✅❌⚠✔✖☑]"
                    r"|(?i:\b(?:todo|wip|done|pending|blocked|in progress|passed|failed|passing|failing)\b)"
                    r"|已完成|未完成|进行中|待办|待处理|已通过|未通过|失败")
DATED = re.compile(r"^(?:(?i:last\s+updated|updated|as\s+of)\b|(?:更新|最后更新|截至|截止)[于：:\s])")
TODO = re.compile(r"\b(?:TODO|FIXME|TBD|XXX)\b|待补充|待完善|待定|待确认|稍后补充")


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


def link_target(raw):
    if re.match(r"^[a-zA-Z][\w+.-]*://", raw) or raw.startswith(("mailto:", "tel:", "data:", "javascript:", "#", "{",
                                                                   "$", "<")):
        return None
    target = LINE_SUFFIX.sub("", unquote(raw.split("#", 1)[0].split("?", 1)[0]))
    return target if target and ":" not in target and ("/" in target or "." in target) else None


def span_target(span):
    text = LINE_SUFFIX.sub("", span.strip())
    if "/" not in text or "://" in text or not PATH_CHARS.match(text) or text.startswith(("@", "-")):
        return None
    parts = [p for p in text.split("/") if p not in ("", ".", "..", "~")]
    last = parts[-1] if parts else ""
    if text.startswith("/") and len(parts) < 2:
        return None
    return text if text.startswith(("./", "../", "~/", "/")) or "." in last[1:] or len(parts) >= 3 else None


def ancestors(folder, root):
    """The folder and each parent up to the root, so paths written relative to a package or skill root resolve."""
    folder, root = Path(os.path.abspath(folder)), Path(os.path.abspath(root))
    chain = [folder]
    while folder != root and root in folder.parents:
        folder = folder.parent
        chain.append(folder)
    return chain if chain[-1] == root else chain + [root]


def denial(sentence):
    for m in DENIAL.finditer(sentence):
        if re.match(r"(?i)do(?:\s+not|n't)", m.group()) and IMPERATIVE_HEAD.search(sentence[:m.start()]):
            continue
        return True
    return False


def check_paths(path, number, segment, root, rep):
    folder = path.parent
    for raw in LINK.findall(segment):
        target = link_target(raw)
        if target and not (Path(target).expanduser() if target.startswith(("/", "~")) else folder / target).exists():
            rep.add("broken-link", path, number, f"({raw})")
    for span in CODE_SPAN.findall(segment):
        target = span_target(span)
        if target is None:
            continue
        candidate = Path(target).expanduser()
        bases = [Path("/")] if candidate.is_absolute() else [*ancestors(folder, root), Path.cwd()]
        if not any((base / candidate).exists() for base in bases):
            rep.add("missing-path", path, number, f"`{span}`")


def closing_summary(path, section, rep):
    if section:
        found = sentences(section[-1])
        for number, sentence in found[:1] + found[-1:]:
            if SUMMARY.match(sentence):
                rep.add("closing-summary", path, number, sentence)
                return


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


def scan_text(paths, root, rep, names=frozenset()):
    files = walk(paths, lambda p: (p.suffix.lower() in TEXT_EXTS or p.name in names) and not SKIP_TEXT.match(p.name))
    entries = []
    for path in files:
        text = read(path)
        if text is None:
            continue
        section = []
        for kind, start, segments in md_units(text) + [("heading", 0, [])]:
            for number, segment in segments:
                check_paths(path, number, segment, root, rep)
            if kind == "heading":
                closing_summary(path, section, rep)
                section = []
                continue
            if kind == "table":
                rows = [n for n, s in segments if not TABLE_RULE.match(s) and STATUS.search(s)]
                if len(rows) >= 2:
                    rep.add("stale-status", path, start, f"{len(rows)} dated or status rows: {segments[0][1]}")
                continue
            section.append(segments)
            joined = " ".join(s for _, s in segments)
            if DATED.match(joined):
                rep.add("stale-status", path, start, joined)
            exceptions = len(EXCEPTION.findall(joined))
            if exceptions >= 2 and exceptions + len(CONTRAST.findall(joined)) >= 3:
                rep.add("exception-chain", path, start, joined)
            for number, sentence in sentences(segments):
                entries.append((path, number, sentence, normalize(sentence)))
                if denial(sentence):
                    rep.add("denial", path, number, sentence)
                for pattern, signal in ((VAGUE, "vague-caution"), (EVERY, "every-output"), (TODO, "todo")):
                    if pattern.search(sentence):
                        rep.add(signal, path, number, sentence)
    duplicates(entries, rep)
    return files


SCANNERS = {
    "code": scan_code,
    "test": scan_test,
    "rule": lambda paths, root, rep: scan_text(paths, root, rep, RULE_NAMES),
    "docs": scan_text,
}


def main(argv=None):
    parser = argparse.ArgumentParser(description="List value-cleaner candidates. Never edits files.")
    parser.add_argument("object", choices=list(SIGNALS))
    parser.add_argument("paths", nargs="*", default=["."], help="files or directories (default: .)")
    parser.add_argument("--root", help="where references are counted and paths resolve (default: repository root)")
    parser.add_argument("--signal", action="append", default=[], metavar="NAME", help="show only this signal; repeatable")
    parser.add_argument("--max", type=int, default=30, metavar="N", help="candidates shown per signal (default: 30)")
    args = parser.parse_args(argv)
    unknown = sorted(set(args.signal) - set(SIGNALS[args.object]))
    if unknown:
        parser.error(f"unknown {args.object} signal: {', '.join(unknown)}; choose from {', '.join(SIGNALS[args.object])}")
    paths = [Path(p).expanduser() for p in args.paths]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        parser.error("not found: " + ", ".join(missing))
    root = Path(args.root).expanduser() if args.root else git_root(paths[0])
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    report = Report(args.object, args.signal)
    files = SCANNERS[args.object](paths, root, report)
    print(report.render(len(files), max(args.max, 1)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
