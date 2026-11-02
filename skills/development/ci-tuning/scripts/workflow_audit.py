#!/usr/bin/env python3
"""Audit GitHub Actions workflows for ci-tuning.

    workflow_audit.py [ROOT] [--json OUT] [--default-branch NAME]

Reads ROOT/.github/workflows/*.yml|*.yaml and the local composite actions they
use. Prints a Markdown report (workflows, job levels, quality commands,
findings) and optionally writes the inventory as JSON for compare.py.
Package scripts, Makefile/justfile targets and `case` arms of local shell
scripts are expanded so commands routed through a CI hook are still classified.
The script only reads files. Requires PyYAML.
"""

from __future__ import annotations

import argparse
import fnmatch
import itertools
import json
import re
import shlex
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: uv run --no-project --with pyyaml python " + " ".join(sys.argv))


# ---------- YAML loading with line numbers ----------

class Map(dict):
    """Mapping that remembers where it and each of its keys start (1-based lines)."""

    line = 0
    key_lines: dict = {}


class Loader(yaml.SafeLoader):
    """SafeLoader with YAML 1.2 booleans, so the `on:` key stays a string."""


Loader.yaml_implicit_resolvers = {
    first: [(tag, rx) for tag, rx in resolvers if tag != "tag:yaml.org,2002:bool"]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
Loader.add_implicit_resolver("tag:yaml.org,2002:bool",
                             re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF"))


def _construct_map(loader, node):
    loader.flatten_mapping(node)
    data = Map()
    data.line = node.start_mark.line + 1
    data.key_lines = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        data[key] = loader.construct_object(value_node, deep=True)
        data.key_lines[key] = key_node.start_mark.line + 1
    return data


Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_map)


def load_yaml(path: Path):
    return yaml.load(path.read_text(encoding="utf-8"), Loader=Loader)


def as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def line_of(mapping, key=None) -> int:
    if isinstance(mapping, Map):
        if key is not None and key in mapping.key_lines:
            return mapping.key_lines[key]
        return mapping.line
    return 0


# ---------- command classification ----------

TOOLS = [(name, cat, re.compile(rx, re.I)) for name, cat, rx in [
    ("oxlint", "lint", r"\boxlint\b"),
    ("eslint", "lint", r"\beslint\b(?!-)"),
    ("biome", "lint", r"\bbiome\s+(?:lint|check|ci)\b"),
    ("ruff", "lint", r"\bruff\s+check\b"),
    ("flake8", "lint", r"\bflake8\b"),
    ("pylint", "lint", r"\bpylint\b"),
    ("golangci-lint", "lint", r"\bgolangci-lint\b"),
    ("go-vet", "lint", r"\bgo\s+vet\b"),
    ("staticcheck", "lint", r"\bstaticcheck\b"),
    ("clippy", "lint", r"\bclippy\b"),
    ("rubocop", "lint", r"\brubocop\b"),
    ("stylelint", "lint", r"\bstylelint\b"),
    ("markdownlint", "lint", r"\bmarkdownlint"),
    ("shellcheck", "lint", r"\bshellcheck\b"),
    ("actionlint", "lint", r"\bactionlint\b"),
    ("hadolint", "lint", r"\bhadolint\b"),
    ("ktlint", "lint", r"\bktlint\b"),
    ("detekt", "lint", r"\bdetekt\b"),
    ("swiftlint", "lint", r"\bswiftlint\b"),
    ("phpstan", "lint", r"\bphpstan\b"),
    ("phpcs", "lint", r"\bphpcs\b"),
    ("pre-commit", "lint", r"\bpre-commit\s+run\b|\bprek\s+run\b"),
    ("typos", "lint", r"\btypos\b|\bcodespell\b"),
    ("prettier", "format", r"\bprettier\b"),
    ("biome-format", "format", r"\bbiome\s+format\b"),
    ("oxfmt", "format", r"\boxfmt\b"),
    ("ruff-format", "format", r"\bruff\s+format\b"),
    ("black", "format", r"\bblack\b"),
    ("isort", "format", r"\bisort\b"),
    ("gofmt", "format", r"\bgofmt\b|\bgoimports\b|\bgofumpt\b"),
    ("rustfmt", "format", r"\bcargo\s+fmt\b|\brustfmt\b"),
    ("dprint", "format", r"\bdprint\b"),
    ("clang-format", "format", r"\bclang-format\b"),
    ("tsgo", "typecheck", r"\btsgo\b"),
    ("tsc", "typecheck", r"(?<![\w-])tsc\b"),
    ("vue-tsc", "typecheck", r"\bvue-tsc\b"),
    ("svelte-check", "typecheck", r"\bsvelte-check\b"),
    ("mypy", "typecheck", r"\bd?mypy\b"),
    ("pyright", "typecheck", r"\b(?:based)?pyright\b"),
    ("ty", "typecheck", r"\bty\s+check\b"),
    ("pyrefly", "typecheck", r"\bpyrefly\b"),
    ("bun-check", "typecheck", r"\bbun\s+check\b"),
    ("tsrs", "typecheck", r"\btsrs\b"),
    ("vitest", "test", r"\bvitest\b"),
    ("jest", "test", r"\bjest\b"),
    ("playwright", "test", r"\bplaywright\s+test\b"),
    ("cypress", "test", r"\bcypress\s+run\b"),
    ("mocha", "test", r"\bmocha\b"),
    ("node-test", "test", r"\bnode\s+(?:\S+\s+)*--test\b"),
    ("bun-test", "test", r"\bbun\s+test\b"),
    ("deno-test", "test", r"\bdeno\s+test\b"),
    ("pytest", "test", r"\bpytest\b"),
    ("unittest", "test", r"-m\s+unittest\b"),
    ("tox", "test", r"\btox\b"),
    ("nox", "test", r"\bnox\b"),
    ("go-test", "test", r"\bgo\s+test\b|\bgotestsum\b"),
    ("nextest", "test", r"\bnextest\b"),
    ("cargo-test", "test", r"\bcargo\s+test\b"),
    ("rspec", "test", r"\brspec\b"),
    ("phpunit", "test", r"\bphpunit\b|\bpest\b"),
    ("maven-test", "test", r"\bmvnw?\b.*\b(?:test|verify)\b"),
    ("gradle-test", "test", r"\bgradlew?\b.*\b(?:test|check)\b"),
    ("dotnet-test", "test", r"\bdotnet\s+test\b"),
    ("ctest", "test", r"\bctest\b"),
    ("cargo-build", "build", r"\bcargo\s+build\b"),
    ("go-build", "build", r"\bgo\s+build\b"),
    ("docker-build", "build", r"\bdocker\s+(?:buildx\s+)?build\b"),
    ("dotnet-build", "build", r"\bdotnet\s+build\b"),
    ("gradle-build", "build", r"\bgradlew?\b.*\b(?:build|assemble)\b"),
    ("maven-package", "build", r"\bmvnw?\b.*\bpackage\b"),
    ("bundler", "build", r"\b(?:vite|next|nuxt|astro|remix|rolldown|rspack|tsup|tsdown|parcel)\s+build\b"
                          r"|\bwebpack\b|\brollup\s+(?:-c|--config)\b|\besbuild\b"),
    ("audit", "security", r"\b(?:npm|pnpm|yarn)\s+audit\b|\bpip-audit\b|\bcargo\s+(?:audit|deny)\b|\bgovulncheck\b"),
    ("install", "install", r"\bnpm\s+(?:ci|install)\b|\b(?:pnpm|yarn|bun)\s+(?:install|i)\b|\buv\s+sync\b"
                           r"|\bpip3?\s+install\b|\buv\s+pip\s+install\b|\bpoetry\s+install\b"
                           r"|\bbundle\s+install\b|\bgo\s+mod\s+download\b|\bcargo\s+fetch\b|\bcomposer\s+install\b"),
]]

USES_TOOLS = [(name, cat, re.compile(rx, re.I)) for name, cat, rx in [
    ("golangci-lint", "lint", r"^golangci/golangci-lint-action"),
    ("ruff", "lint", r"^(?:astral-sh|chartboost)/ruff-action"),
    ("pre-commit", "lint", r"^pre-commit/action"),
    ("super-linter", "lint", r"^(?:super-linter|github)/super-linter"),
    ("actionlint", "lint", r"^(?:rhysd/actionlint|raven-actions/actionlint|reviewdog/action-actionlint)"),
    ("cypress", "test", r"^cypress-io/github-action"),
    ("codeql", "security", r"^github/codeql-action/analyze"),
    ("dependency-review", "security", r"^actions/dependency-review-action"),
]]

TASK_CATEGORIES = [
    ("typecheck", re.compile(r"type-?check|check-?types|^types?$|typings|\btsc\b|mypy|pyright", re.I)),
    ("format", re.compile(r"format|fmt|prettier", re.I)),
    ("lint", re.compile(r"lint|clippy|\bvet\b", re.I)),
    ("test", re.compile(r"test|spec|e2e|unit|integration|coverage", re.I)),
    ("build", re.compile(r"build|compile|bundle", re.I)),
]

STRICT_FLAGS = [(name, re.compile(rx)) for name, rx in [
    ("max-warnings=0", r"--max-warnings[= ]0\b"),
    ("strict", r"--strict\b"),
    ("deny-warnings", r"-D\s*warnings\b|--deny[= ]warnings\b"),
    ("warnings-as-errors", r"-Werror\b|-W\s*error\b|--warnings-as-errors\b|--error-on-warnings?\b"),
    ("fail-under", r"--(?:cov-)?fail-under[= ]\S+"),
    ("frozen-lockfile", r"--frozen-lockfile\b|--immutable\b"),
    ("locked", r"--locked\b"),
    ("check", r"--check\b"),
    ("ci", r"--ci\b"),
]]

WEAKEN = [(name, re.compile(rx, re.I)) for name, rx in [
    ("or-true", r"\|\|\s*(?:true\b|:(?=\s|;|$)|exit\s+0\b)"),
    ("pass-with-no-tests", r"--pass-?with-?no-?tests\b"),
    ("set+e", r"\bset\s+\+e\b"),
]]

QUALITY = {"lint", "format", "typecheck", "test", "build", "security"}
PACKAGE_MANAGERS = {"npm", "pnpm", "yarn", "bun"}
PM_BUILTINS = {"install", "i", "ci", "add", "remove", "exec", "dlx", "x", "create", "init", "publish",
               "pack", "link", "audit", "outdated", "update", "up", "why", "list", "ls", "config", "set"}
PM_OPTS_WITH_VALUE = {"--filter", "-F", "-C", "--dir", "--prefix", "--workspace", "--cwd"}
TASK_RUNNERS = {"poe", "task", "mage", "invoke", "inv", "rake"}

STANDARD_RUNNER = re.compile(
    r"^(?:ubuntu-(?:latest|slim|\d{2}\.\d{2}(?:-arm)?)"
    r"|windows-(?:latest|\d{4}(?:-vs\d{4})?|11-arm|11-vs\d{4}-arm)"
    r"|macos-(?:latest|\d{2}(?:-intel)?)|xcode-\d+)$")
STEP_SETUP = re.compile(r"^(?:actions/checkout|actions/setup-|actions/cache|astral-sh/setup-uv|pnpm/action-setup"
                        r"|oven-sh/setup-bun|ruby/setup-ruby|dtolnay/rust-toolchain|Swatinem/rust-cache"
                        r"|gradle/actions/setup-gradle|denoland/setup-deno)", re.I)
VOLATILE_KEY = re.compile(r"github\.(?:sha|run_id|run_number|run_attempt)")
SOURCE_INSTALL = re.compile(r"\bgo\s+install\s+(?:-\S+\s+)*\S+@\S+|\bcargo\s+(?:\+\S+\s+)?install\b[^\n;&|]*")
# Results of these tools do not depend on the runner OS. Platform-aware checks (clippy, go vet,
# golangci-lint, staticcheck, mypy, pyright, pylint, govulncheck, pip-audit) are left out on purpose.
OS_AGNOSTIC_TOOLS = {"oxlint", "eslint", "biome", "ruff", "flake8", "rubocop", "stylelint", "markdownlint",
                     "shellcheck", "actionlint", "hadolint", "ktlint", "detekt", "phpcs", "typos", "prettier",
                     "biome-format", "oxfmt", "ruff-format", "black", "isort", "gofmt", "rustfmt", "dprint",
                     "clang-format", "tsgo", "tsc", "vue-tsc", "svelte-check", "bun-check", "tsrs",
                     "dependency-review"}
OS_AGNOSTIC_AUDIT = re.compile(r"\b(?:npm|pnpm|yarn)\s+audit\b|\bcargo\s+(?:audit|deny)\b")
PLATFORM_AUDIT = re.compile(r"\bpip-audit\b|\bgovulncheck\b")
LINUX_GUARD = re.compile(r"linux|ubuntu", re.I)
WORKSPACE_PATH = re.compile(r"^(?:\.|\./|\*|\*\*|\*\*/\*|\$\{\{\s*github\.workspace\s*\}\})/?$")
HISTORY_EVENTS = {"push", "schedule"}


def classify(text: str) -> list[tuple[str, str]]:
    found = [(name, cat) for name, cat, rx in TOOLS if rx.search(text)]
    categories = {cat for _, cat in found}
    for task in re.findall(r"task:([\w:./-]+)", text):
        cat = task_category(task)
        if cat and cat not in categories:
            found.append((f"task:{task}", cat))
            categories.add(cat)
    return found


def task_category(task: str):
    for cat, rx in TASK_CATEGORIES:
        if rx.search(task):
            return cat
    return None


def logical_lines(script) -> list[str]:
    lines, buf = [], ""
    for raw in str(script).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            buf += line[:-1].strip() + " "
            continue
        lines.append(re.sub(r"\s+", " ", (buf + line).strip()))
        buf = ""
    if buf.strip():
        lines.append(re.sub(r"\s+", " ", buf.strip()))
    return lines


def tokenize(cmd: str) -> list[str]:
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        tokens = cmd.split()
    while tokens and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
        tokens.pop(0)
    return tokens


class Resolver:
    """Expand package scripts, make/just targets and local scripts into the commands they run."""

    def __init__(self, root: Path):
        self.root = root
        self.scripts = {}
        package = root / "package.json"
        if package.is_file():
            try:
                self.scripts = json.loads(package.read_text(encoding="utf-8")).get("scripts") or {}
            except (OSError, ValueError):
                pass
        self.makefile = self._read("Makefile", "makefile", "GNUmakefile")
        self.justfile = self._read("justfile", "Justfile", ".justfile")

    def _read(self, *names):
        for name in names:
            path = self.root / name
            if path.is_file():
                return path.read_text(encoding="utf-8", errors="replace")
        return ""

    def expand(self, cmd: str, depth: int = 0) -> str:
        if depth > 3:
            return ""
        tokens = tokenize(cmd)
        if not tokens:
            return ""
        head = Path(tokens[0]).name
        if head in PACKAGE_MANAGERS:
            return self._package(head, tokens[1:], depth)
        if head in ("make", "gmake"):
            return self._recipes(self.makefile, tokens[1:], depth, make=True)
        if head == "just":
            return self._recipes(self.justfile, tokens[1:], depth, make=False)
        extra = []
        for i, tok in enumerate(tokens[:-1]):
            if Path(tok).name in TASK_RUNNERS or (tok == "xtask" and i > 0):
                extra.append(f"task:{tokens[i + 1]}")
        if head in ("turbo", "nx") or (head in ("npx", "pnpx", "bunx") and len(tokens) > 1
                                        and tokens[1] in ("turbo", "nx")):
            extra += [f"task:{t}" for t in self._monorepo_tasks(tokens)]
        if head in ("bash", "sh", "zsh") and len(tokens) > 1:
            script, script_args = tokens[1], tokens[2:]
        else:
            script, script_args = tokens[0], tokens[1:]
        extra.append(self._local_script(script, script_args, depth))
        return " ".join(e for e in extra if e)

    def _package(self, head, rest, depth):
        i = 0
        while i < len(rest) and rest[i].startswith("-"):
            i += 2 if rest[i] in PM_OPTS_WITH_VALUE else 1
        if i >= len(rest):
            return ""
        word = rest[i]
        if word in ("exec", "dlx", "x"):
            return self.expand(shlex.join(rest[i + 1:]), depth + 1)
        if word in ("run", "run-script"):
            name = rest[i + 1] if i + 1 < len(rest) else ""
        elif head == "npm" and word in ("test", "t"):
            name = "test"
        elif word in PM_BUILTINS or head == "npm":
            return ""
        else:
            name = word
        body = self.scripts.get(name)
        if body is None:
            if word == name and head != "npm":
                # pnpm, yarn and bun run a binary when no script has that name.
                return f"task:{name} " + self.expand(shlex.join(rest[i:]), depth + 1)
            return f"task:{name}" if name else ""
        nested = " ".join(self.expand(part, depth + 1) for part in re.split(r"&&|\|\||;", body))
        return f"task:{name} {body} {nested}"

    def _recipes(self, text, args, depth, make):
        targets = []
        skip = False
        for arg in args:
            if skip:
                skip = False
                continue
            if arg in ("-C", "-f", "--directory", "--file", "--justfile", "--working-directory"):
                skip = True
            elif not arg.startswith("-") and "=" not in arg:
                targets.append(arg)
                if not make:
                    break
        out = []
        for target in targets:
            out.append(f"task:{target}")
            if make:
                rx = rf"(?m)^{re.escape(target)}\s*:(?!=)([^\n]*)\n((?:\t[^\n]*(?:\n|$))*)"
            else:
                rx = rf"(?m)^@?{re.escape(target)}(?:\s+[^:\n]*)?:(?!=)([^\n]*)\n((?:[ \t]+[^\n]*(?:\n|$))*)"
            match = re.search(rx, text)
            if not match:
                continue
            prereqs = [p for p in re.split(r"[\s|]+", match.group(1)) if p and not p.startswith("#")]
            body = match.group(2)
            out.append(body)
            for line in logical_lines(body):
                out.append(self.expand(line.lstrip("@-"), depth + 1))
            if prereqs and depth < 3:
                out.append(self._recipes(text, prereqs, depth + 1, make))
        return " ".join(o for o in out if o)

    @staticmethod
    def _monorepo_tasks(tokens):
        tasks, take = [], False
        for tok in tokens[1:]:
            if tok in ("-t", "--target", "--targets"):
                take = True
            elif take and not tok.startswith("-"):
                tasks += tok.split(",")
                take = False
            elif tok.startswith("--target=") or tok.startswith("--targets="):
                tasks += tok.split("=", 1)[1].split(",")
            elif ":" in tok and not tok.startswith("-"):
                tasks.append(tok.split(":")[-1])
            elif tok not in ("run", "run-many", "affected", "exec", "turbo", "nx") and not tok.startswith("-"):
                tasks.append(tok)
        return tasks

    def _local_script(self, script, args, depth):
        if not (script.startswith("./") or "/" in script or script.endswith(".sh")):
            return ""
        path = (self.root / script).resolve()
        try:
            path.relative_to(self.root.resolve())
        except ValueError:
            return ""
        if not path.is_file() or path.stat().st_size > 200_000:
            return ""
        text = path.read_text(encoding="utf-8", errors="replace")
        task = next((a for a in args if not a.startswith("-")), None)
        if task:
            arm = re.search(rf"(?ms)^[ \t]*\(?(?:[\w.:*-]+\|)*{re.escape(task)}(?:\|[\w.:*-]+)*\)(.*?);;", text)
            if arm:
                body = arm.group(1)
                nested = " ".join(self.expand(line, depth + 1) for line in logical_lines(body))
                return f"task:{task} {body} {nested}"
        return text


# ---------- workflow parsing ----------

def triggers(doc) -> dict:
    on = doc.get("on", doc.get(True))
    if isinstance(on, str):
        return {on: {}}
    if isinstance(on, list):
        return {str(e): {} for e in on}
    if isinstance(on, dict):
        return {str(k): (v if isinstance(v, dict) else {}) for k, v in on.items()}
    return {}


def branch_matches(branch, patterns) -> bool:
    result = False
    for pattern in as_list(patterns):
        pattern = str(pattern)
        negated = pattern.startswith("!")
        if fnmatch.fnmatchcase(branch, pattern[1:] if negated else pattern):
            result = not negated
    return result


def pushes_default(events, default_branch) -> bool:
    push = events.get("push")
    if push is None:
        return False
    if "branches" in push:
        return branch_matches(default_branch, push["branches"])
    if "branches-ignore" in push:
        return not branch_matches(default_branch, push["branches-ignore"])
    return not ("tags" in push or "tags-ignore" in push)


def matrix_combos(strategy):
    """Return (combos, dynamic). combos is [None] for a job without a matrix."""
    matrix = strategy.get("matrix") if isinstance(strategy, dict) else None
    if matrix is None:
        return [None], False
    if not isinstance(matrix, dict):
        return [], True
    dims = {k: v for k, v in matrix.items() if k not in ("include", "exclude")}
    include, exclude = matrix.get("include") or [], matrix.get("exclude") or []
    if any(not isinstance(v, list) for v in dims.values()) or not isinstance(include, list) \
            or not isinstance(exclude, list):
        return [], True
    keys = list(dims)
    combos = [dict(zip(keys, values)) for values in itertools.product(*dims.values())] if keys else []
    combos = [c for c in combos
              if not any(isinstance(e, dict) and all(c.get(k) == v for k, v in e.items()) for e in exclude)]
    extra = []
    for inc in include:
        if not isinstance(inc, dict):
            continue
        matched = False
        for combo in combos:
            if all(combo.get(k) == v for k, v in inc.items() if k in keys):
                combo.update({k: v for k, v in inc.items() if k not in keys})
                matched = True
        if not matched:
            extra.append(dict(inc))
    return combos + extra, False


def render_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def check_names(display, combos, dynamic) -> list[str]:
    if dynamic:
        return [f"{display} (*)"]
    if combos == [None]:
        return [display]
    names = []
    for combo in combos:
        if re.search(r"\$\{\{\s*matrix\.", display):
            names.append(re.sub(r"\$\{\{\s*matrix\.([\w-]+)\s*\}\}",
                                lambda m: render_value(combo.get(m.group(1), "")), display))
        else:
            names.append(f"{display} ({', '.join(render_value(v) for v in combo.values())})")
    return names


def resolve_matrix(text: str, combo) -> str:
    def value(match):
        current = combo or {}
        for part in match.group(1).split("."):
            current = current.get(part, "") if isinstance(current, dict) else ""
        return render_value(current)
    return re.sub(r"\$\{\{\s*matrix\.([\w.-]+)\s*\}\}", value, text)


def os_of(label: str):
    label = label.lower()
    if "${{" in label:
        return None
    if label.startswith(("macos", "xcode")):
        return "macOS"
    if label.startswith("windows"):
        return "Windows"
    return "Linux" if label.startswith("ubuntu") else None


def runner_os(labels, combos, dynamic) -> dict:
    """Count matrix combinations per runner OS; unresolved and custom labels count as unknown."""
    counts = Counter()
    for combo in ([None] if dynamic else combos):
        kinds = [os_of(resolve_matrix(label, combo)) for label in labels]
        counts[next((k for k in kinds if k), "unknown")] += 1
    return dict(counts)


def cache_usage(uses: str, with_: dict, root: Path):
    action = uses.split("@")[0].lower()
    major = re.search(r"@v?(\d+)", uses)
    major = int(major.group(1)) if major else None
    with_ = with_ if isinstance(with_, dict) else {}

    def flag(name, default=False):
        value = with_.get(name, default)
        return value if isinstance(value, bool) else str(value).lower() == "true"

    if action in ("actions/cache", "actions/cache/restore", "actions/cache/save"):
        mode = {"actions/cache": "restore+save", "actions/cache/restore": "restore",
                "actions/cache/save": "save"}[action]
        path = " ".join(logical_lines(with_.get("path", "")))
        return {"kind": f"actions/cache:{path}", "mode": mode, "path": path,
                "key": str(with_.get("key", "")), "restore_keys": bool(with_.get("restore-keys"))}
    if action == "actions/setup-node":
        if with_.get("cache"):
            return {"kind": f"setup-node:{with_['cache']}", "mode": "restore+save"}
        if major and major >= 5 and flag("package-manager-cache", True):
            try:
                package = json.loads((root / "package.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                package = {}
            if str(package.get("packageManager", "")).startswith("npm"):
                return {"kind": "setup-node:npm", "mode": "restore+save"}
        return None
    if action in ("actions/setup-python", "actions/setup-java") and with_.get("cache"):
        return {"kind": f"{action.split('/')[1]}:{with_['cache']}", "mode": "restore+save"}
    if action == "actions/setup-go" and flag("cache", major is None or major >= 4):
        return {"kind": "setup-go", "mode": "restore+save"}
    if action == "actions/setup-dotnet" and flag("cache"):
        return {"kind": "setup-dotnet", "mode": "restore+save"}
    if action == "ruby/setup-ruby" and flag("bundler-cache"):
        return {"kind": "setup-ruby:bundler", "mode": "restore+save"}
    if action == "astral-sh/setup-uv" and str(with_.get("enable-cache", "auto")).lower() != "false":
        return {"kind": "setup-uv", "mode": "restore+save"}
    if action == "swatinem/rust-cache":
        return {"kind": "rust-cache", "mode": "restore+save", "save_if": str(with_.get("save-if", ""))}
    if action == "gradle/actions/setup-gradle":
        return {"kind": "setup-gradle", "mode": "restore+save(default-branch)"}
    if action == "mozilla-actions/sccache-action":
        return {"kind": "sccache", "mode": "restore+save"}
    return None


class Audit:
    def __init__(self, root: Path, default_branch: str):
        self.root = root
        self.default_branch = default_branch
        self.resolver = Resolver(root)
        self.workflows = []
        self.findings = []
        self.errors = []

    def rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)

    def add(self, fid, severity, location, message, hint=""):
        self.findings.append({"id": fid, "severity": severity, "location": location,
                              "message": message, "hint": hint})

    # ----- parsing -----

    def run(self):
        wf_dir = self.root / ".github" / "workflows"
        files = sorted(list(wf_dir.glob("*.yml")) + list(wf_dir.glob("*.yaml"))) if wf_dir.is_dir() else []
        for path in files:
            try:
                doc = load_yaml(path)
            except (yaml.YAMLError, UnicodeDecodeError) as exc:
                self.errors.append(f"{self.rel(path)}: {exc}")
                continue
            if isinstance(doc, dict):
                self.workflows.append(self.parse_workflow(path, doc))
        self.link_reusable()
        self.compute_findings()
        return self

    def parse_workflow(self, path, doc):
        events = triggers(doc)
        concurrency = doc.get("concurrency")
        wf = {
            "file": self.rel(path), "name": str(doc.get("name") or path.stem),
            "events": sorted(events), "event_filters": {}, "push_default": pushes_default(events, self.default_branch),
            "concurrency": concurrency if isinstance(concurrency, (dict, str)) else None,
            "line": line_of(doc, "on"), "jobs": [], "callers": [],
        }
        for event, config in events.items():
            filters = {k: as_list(v) for k, v in config.items()
                       if k in ("branches", "branches-ignore", "paths", "paths-ignore", "tags", "types")}
            if filters:
                wf["event_filters"][event] = filters
        jobs = doc.get("jobs") if isinstance(doc.get("jobs"), dict) else {}
        for job_id, job in jobs.items():
            if isinstance(job, dict):
                wf["jobs"].append(self.parse_job(wf, path, jobs, str(job_id), job))
        return wf

    def parse_job(self, wf, path, jobs, job_id, job):
        display = str(job.get("name") or job_id)
        combos, dynamic = matrix_combos(job.get("strategy"))
        runs_on = job.get("runs-on")
        if isinstance(runs_on, dict):
            labels = [str(x) for x in as_list(runs_on.get("labels"))] or [f"group:{runs_on.get('group')}"]
        else:
            labels = [str(x) for x in as_list(runs_on)]
        strategy = job.get("strategy") if isinstance(job.get("strategy"), dict) else {}
        entry = {
            "id": job_id, "name": display, "line": line_of(jobs, job_id),
            "runs_on": labels, "runner_os": runner_os(labels, combos, dynamic),
            "needs": [str(n) for n in as_list(job.get("needs"))],
            "if": str(job.get("if", "")) or None,
            "uses": str(job.get("uses")) if job.get("uses") else None,
            "matrix_size": None if dynamic else (1 if combos == [None] else len(combos)),
            "matrix_dynamic": dynamic, "fail_fast": strategy.get("fail-fast", True),
            "check_names": check_names(display, combos, dynamic),
            "timeout": job.get("timeout-minutes"), "continue_on_error": job.get("continue-on-error", False),
            "concurrency": job.get("concurrency"), "services": sorted(str(s) for s in (job.get("services") or {})),
            "steps": [], "commands": [], "caches": [], "source_installs": [], "setup_steps": 0,
            "downloads_artifacts": False,
            "reads_needs": bool(re.search(r"needs\.\*|tojson\(\s*needs\s*\)|needs\.[\w-]+\.(?:outputs|result)",
                                          json.dumps(job, default=str), re.I)),
        }
        self.walk_steps(entry, path, job.get("steps") or [], depth=0)
        return entry

    def walk_steps(self, entry, path, steps, depth):
        for step in steps:
            if not isinstance(step, dict):
                continue
            location = f"{self.rel(path)}:{line_of(step)}"
            uses = str(step.get("uses") or "")
            run = step.get("run")
            first = logical_lines(run)[:1] if run else []
            entry["steps"].append({"location": location, "name": step.get("name"), "uses": uses or None,
                                   "with": step.get("with") if isinstance(step.get("with"), dict) else None,
                                   "run": first[0] if first else None,
                                   "if": str(step.get("if")) if step.get("if") else None,
                                   "continue_on_error": step.get("continue-on-error", False)})
            if uses:
                if STEP_SETUP.match(uses):
                    entry["setup_steps"] += 1
                if uses.split("@")[0].lower() == "actions/download-artifact":
                    entry["downloads_artifacts"] = True
                cache = cache_usage(uses, step.get("with") or {}, self.root)
                if cache:
                    cache["location"] = location
                    entry["caches"].append(cache)
                for name, cat, rx in USES_TOOLS:
                    if rx.search(uses):
                        entry["commands"].append({"cmd": uses, "tools": [name], "categories": [cat],
                                                  "checks": [f"{cat}:{name}"], "flags": [], "weaken": [],
                                                  "os_agnostic": [f"{cat}:{name}"] if name in OS_AGNOSTIC_TOOLS
                                                  else [],
                                                  "location": location,
                                                  "continue_on_error": step.get("continue-on-error", False)})
                if uses.startswith("./") and depth < 3:
                    self.walk_composite(entry, uses, depth)
            if run:
                for line in logical_lines(run):
                    self.add_command(entry, line, location, step.get("continue-on-error", False),
                                     str(step.get("if") or ""))

    def walk_composite(self, entry, uses, depth):
        base = self.root / uses[2:].split("@")[0]
        for name in ("action.yml", "action.yaml"):
            path = base / name
            if path.is_file():
                try:
                    doc = load_yaml(path)
                except (yaml.YAMLError, UnicodeDecodeError) as exc:
                    self.errors.append(f"{self.rel(path)}: {exc}")
                    return
                runs = doc.get("runs") if isinstance(doc, dict) else None
                if isinstance(runs, dict) and runs.get("using") == "composite":
                    self.walk_steps(entry, path, runs.get("steps") or [], depth + 1)
                return

    def add_command(self, entry, line, location, continue_on_error, step_if=""):
        weaken = [name for name, rx in WEAKEN if rx.search(line)]
        for segment in re.split(r"\s&&\s|\s;\s", line):
            segment = segment.strip()
            expanded = self.resolver.expand(segment)
            if "cache-hit" not in step_if:
                self.note_source_installs(entry, segment, expanded, location)
            text = f"{segment} {expanded}"
            found = classify(text)
            if not found:
                continue
            flags = sorted({name for name, rx in STRICT_FLAGS if rx.search(text)})
            agnostic = {f"{c}:{t}" for t, c in found if t in OS_AGNOSTIC_TOOLS
                        or (t == "audit" and OS_AGNOSTIC_AUDIT.search(text) and not PLATFORM_AUDIT.search(text))}
            entry["commands"].append({
                "cmd": segment, "tools": sorted({t for t, _ in found}),
                "categories": sorted({c for _, c in found}), "checks": sorted({f"{c}:{t}" for t, c in found}),
                "flags": flags, "weaken": weaken, "os_agnostic": sorted(agnostic), "location": location,
                "continue_on_error": continue_on_error,
            })

    @staticmethod
    def note_source_installs(entry, segment, expanded, location):
        # A step guarded by a cache hit only compiles on a miss, which is the documented fallback.
        for source, via in ((segment, None), (expanded, segment)):
            for match in SOURCE_INSTALL.finditer(source):
                cmd = re.sub(r"\s+", " ", match.group(0)).strip()
                if re.search(r"\s--(?:path|list)\b", cmd):
                    continue
                if not any(i["cmd"] == cmd and i["location"] == location for i in entry["source_installs"]):
                    entry["source_installs"].append({"cmd": cmd, "via": via, "location": location})

    def link_reusable(self):
        by_file = {wf["file"]: wf for wf in self.workflows}
        for wf in self.workflows:
            for job in wf["jobs"]:
                target = job["uses"]
                if target and target.startswith("./"):
                    called = by_file.get(target[2:].split("@")[0])
                    if called:
                        called["callers"].append({"workflow": wf["file"], "job": job["name"],
                                                  "events": wf["events"], "push_default": wf["push_default"]})
        for wf in self.workflows:
            events = set(wf["events"])
            push_default = wf["push_default"]
            for caller in wf["callers"]:
                events |= set(caller["events"])
                push_default = push_default or caller["push_default"]
            if wf["callers"]:
                events.discard("workflow_call")
                for job in wf["jobs"]:
                    job["check_names"] = [f"{c['job']} / {n}" for c in wf["callers"] for n in job["check_names"]]
            wf["effective_events"] = sorted(events)
            wf["seeds_default_cache"] = push_default or "schedule" in events
            wf["jobs_per_run"] = sum(job["matrix_size"] or 1 for job in wf["jobs"])

    # ----- findings -----

    def compute_findings(self):
        seeded_kinds = {c["kind"] for wf in self.workflows if wf["seeds_default_cache"]
                        for job in wf["jobs"] for c in job["caches"]}
        command_owners = defaultdict(list)
        no_timeout = []
        for wf in self.workflows:
            events = set(wf["effective_events"])
            pr = bool(events & {"pull_request", "pull_request_target", "merge_group"})
            self.workflow_findings(wf, events, pr)
            for job in wf["jobs"]:
                where = f"{wf['file']}:{job['line']}"
                if pr and job["timeout"] is None and not job["uses"]:
                    no_timeout.append((where, f"{wf['file']}#{job['id']}"))
                self.job_findings(wf, job, where, seeded_kinds)
                for command in job["commands"]:
                    if set(command["categories"]) & QUALITY:
                        command_owners[(command["cmd"], tuple(command["tools"]))].append((wf, job, command))
        for (cmd, _), owners in command_owners.items():
            jobs = {(wf["file"], job["id"]) for wf, job, _ in owners}
            event_sets = [set(wf["effective_events"]) for wf, _, _ in owners]
            if len(jobs) > 1 and set.intersection(*event_sets):
                locations = ", ".join(sorted({c["location"] for _, _, c in owners}))
                self.add("duplicate-command", "medium", owners[0][2]["location"],
                         f"`{cmd}` runs in {len(jobs)} jobs on overlapping events ({locations}).",
                         "Keep one copy and union its triggers (organize.md §4).")
        if no_timeout:
            labels = [label for _, label in no_timeout]
            self.add("no-timeout", "low", no_timeout[0][0],
                     f"{len(labels)} PR job(s) without timeout-minutes: {', '.join(labels[:8])}"
                     + (" …" if len(labels) > 8 else ""),
                     "Set timeout-minutes to 2-3x the job's P95.")

    def workflow_findings(self, wf, events, pr):
        where = f"{wf['file']}:{wf['line']}"
        concurrency = wf["concurrency"]
        if pr and not concurrency and not all(job["concurrency"] for job in wf["jobs"]):
            self.add("no-concurrency", "medium", where,
                     f"Workflow `{wf['name']}` runs on pull requests without a concurrency group; superseded "
                     "runs keep running and use the shared job concurrency.",
                     "Add a concurrency group that cancels in-progress PR runs only (parallel.md §7).")
        if isinstance(concurrency, dict) and concurrency.get("cancel-in-progress") is True and wf["push_default"]:
            group = str(concurrency.get("group", ""))
            if not re.search(r"github\.(?:sha|run_id|run_number)|pull_request\.number\s*\|\|", group):
                self.add("cancels-default-branch", "low", where,
                         f"`{wf['name']}` cancels in-progress runs and its group `{group}` is shared by "
                         "default-branch pushes, so main runs can cancel each other before saving caches.",
                         "Use `cancel-in-progress: ${{ github.event_name == 'pull_request' }}` or a per-SHA group.")
        for event in ("pull_request", "pull_request_target"):
            filters = wf["event_filters"].get(event, {})
            if any(k in filters for k in ("paths", "paths-ignore")):
                self.add("workflow-path-filter", "medium", where,
                         f"`{wf['name']}` filters `{event}` by paths. If any of its checks is required, PRs that "
                         "skip the workflow stay Pending.",
                         "Move change detection to a job-level condition with an aggregate gate (parallel.md §8).")
        if "push" in events and "pull_request" in events and not wf["event_filters"].get("push", {}).get("branches") \
                and not wf["event_filters"].get("push", {}).get("branches-ignore") \
                and not wf["event_filters"].get("push", {}).get("tags"):
            self.add("push-and-pr", "medium", where,
                     f"`{wf['name']}` runs on push to every branch and on pull_request, so PR commits run twice.",
                     "Limit push to the default and release branches (organize.md §4).")
        if pr and wf["jobs_per_run"] > 20:
            self.add("jobs-over-concurrency", "medium", where,
                     f"`{wf['name']}` expands to {wf['jobs_per_run']} jobs per run; a Free account runs 20 at once.",
                     "Merge small jobs or reduce shards; watch queue_p95 (parallel.md §3).")

    def job_findings(self, wf, job, where, seeded_kinds):
        name = f"`{job['id']}`"
        for label in job["runs_on"]:
            if "${{" not in label and not STANDARD_RUNNER.match(label):
                self.add("non-standard-runner", "info", where,
                         f"Job {name} runs on `{label}`, which is not a standard GitHub-hosted label.",
                         "Keep as is; ci-tuning does not add paid or self-hosted runners.")
        quality = [c for c in job["commands"] if set(c["categories"]) & QUALITY]
        if job["continue_on_error"] is True and quality:
            self.add("gate-continue-on-error", "high", where,
                     f"Job {name} runs quality checks with continue-on-error, so failures do not block.")
        for command in quality:
            if command["continue_on_error"] is True:
                self.add("gate-continue-on-error", "high", command["location"],
                         f"Step `{command['cmd']}` has continue-on-error.")
            for weak in command["weaken"]:
                self.add("gate-weakened", "high", command["location"], f"`{command['cmd']}` uses `{weak}`.",
                         "Failures or empty test selections pass silently.")
        categories = {c for command in quality for c in command["categories"]} & (QUALITY - {"security"})
        if len(categories) >= 2:
            self.add("mixed-job", "info", where,
                     f"Job {name} runs {', '.join(sorted(categories))} in sequence.",
                     "If it is on the critical path, split it (parallel.md §2).")
        if job["needs"] and not job["downloads_artifacts"] and not job["reads_needs"] and not job["uses"]:
            self.add("needs-without-data", "low", where,
                     f"Job {name} waits for {', '.join(job['needs'])} but reads no outputs or artifacts.",
                     "Drop the dependency unless the ordering is intended (organize.md §5).")
        for item in job["source_installs"]:
            via = f" (via `{item['via']}`)" if item["via"] else ""
            self.add("source-install", "medium", item["location"],
                     f"Job {name} compiles `{item['cmd']}` from source on every run{via}.",
                     "Install a prebuilt binary: the tool's own action, taiki-e/install-action, cargo-binstall "
                     "or a pinned release download (accelerate/env.md §2).")
        off_linux = {kind: n for kind, n in job["runner_os"].items() if kind in ("macOS", "Windows")}
        if off_linux:
            step_if = {s["location"]: s["if"] or "" for s in job["steps"]}
            checks = sorted({check for c in job["commands"] for check in c.get("os_agnostic", [])
                             if not LINUX_GUARD.search(step_if.get(c["location"], ""))})
            if checks:
                listed = ", ".join(f"`{c}`" for c in checks)
                runners = " and ".join(f"{off_linux[kind]} {kind}" for kind in ("macOS", "Windows") if kind in off_linux)
                self.add("os-agnostic-off-linux", "medium", where,
                         f"Job {name} runs {listed} on {runners} runner(s); these results do not depend on the OS.",
                         "Run them once on Ubuntu and keep macOS/Windows for platform tests and builds; a Free "
                         "account runs 5 macOS jobs at once (organize.md §3).")
        installs = any("install" in c["categories"] for c in job["commands"])
        if installs and not job["caches"]:
            self.add("install-without-cache", "medium", where,
                     f"Job {name} installs dependencies with no cache configured.", "See accelerate/cache.md.")
        for cache in job["caches"]:
            if not wf["seeds_default_cache"] and cache["kind"] not in seeded_kinds and cache["mode"] != "save":
                self.add("pr-only-cache", "high", cache["location"],
                         f"Cache `{cache['kind']}` in job {name} is only written by runs that cannot seed the "
                         "default branch; PR caches are scoped to refs/pull/N/merge, so new PRs start cold.",
                         "Write the same cache from a push to the default branch (accelerate/cache.md §2).")
            if cache["kind"].startswith("actions/cache:"):
                paths = [p.strip() for p in cache["path"].split(" ") if p.strip()]
                if any(WORKSPACE_PATH.match(p) for p in paths):
                    self.add("cache-workspace", "high", cache["location"],
                             f"Cache path `{cache['path']}` covers the whole workspace.",
                             "Cache dependency and tool directories only.")
                if "node_modules" in cache["path"] and cache["restore_keys"]:
                    self.add("node-modules-restore-keys", "medium", cache["location"],
                             "node_modules is restored by prefix (restore-keys), which can leave stale packages.",
                             "Use an exact key and skip install only on an exact hit.")
                if VOLATILE_KEY.search(cache["key"]) and not cache["restore_keys"]:
                    self.add("volatile-cache-key", "medium", cache["location"],
                             f"Cache key `{cache['key']}` changes every run and has no restore-keys, so it never hits.")
        for step in job["steps"]:
            with_ = step["with"] or {}
            if (step["uses"] or "").lower().startswith("actions/checkout") \
                    and str(with_.get("fetch-depth", "1")) == "0" and not with_.get("filter"):
                self.add("full-clone", "medium", step["location"],
                         f"Job {name} clones full history with blobs (fetch-depth: 0).",
                         "Add `filter: blob:none`, or fetch history separately (accelerate/checkout.md).")


# ---------- output ----------

def job_levels(wf):
    jobs = {job["id"]: job for job in wf["jobs"]}
    levels = {}

    def level(job_id, seen=()):
        if job_id in levels:
            return levels[job_id]
        if job_id in seen or job_id not in jobs:
            return 0
        deps = [d for d in jobs[job_id]["needs"] if d in jobs]
        levels[job_id] = 1 + max((level(d, seen + (job_id,)) for d in deps), default=-1)
        return levels[job_id]

    for job_id in jobs:
        level(job_id)
    return levels


def markdown(audit: Audit) -> str:
    wfs = audit.workflows
    counts = Counter(f["severity"] for f in audit.findings)
    out = ["# Workflow audit", "",
           f"Root: `{audit.root}` · default branch: `{audit.default_branch}` · workflows: {len(wfs)} · "
           f"jobs: {sum(len(w['jobs']) for w in wfs)} · findings: "
           + (", ".join(f"{counts[s]} {s}" for s in ("high", "medium", "low", "info") if counts[s]) or "none"), ""]
    if audit.errors:
        out += ["Parse errors:", *[f"- {e}" for e in audit.errors], ""]
    if not wfs:
        out += ["No workflows found under `.github/workflows/`.", ""]
        return "\n".join(out)
    out += ["## Workflows", "", "| File | Name | Events | Jobs/run | Concurrency | Seeds default-branch cache |",
            "| --- | --- | --- | --- | --- | --- |"]
    for wf in wfs:
        conc = wf["concurrency"]
        if isinstance(conc, dict):
            conc = f"`{conc.get('group')}` cancel={render_value(conc.get('cancel-in-progress', False))}"
        out.append(f"| `{wf['file']}` | {wf['name']} | {', '.join(wf['effective_events'])} | {wf['jobs_per_run']} "
                   f"| {conc or '—'} | {'yes' if wf['seeds_default_cache'] else 'no'} |")
    out += ["", "## Job levels", ""]
    for wf in wfs:
        levels = job_levels(wf)
        out.append(f"**{wf['name']}** (`{wf['file']}`)")
        by_level = defaultdict(list)
        for job in wf["jobs"]:
            size = job["matrix_size"]
            label = job["id"] + (f" ×{size}" if size and size > 1 else " ×?" if job["matrix_dynamic"] else "")
            if job["needs"]:
                label += f" ← {', '.join(job['needs'])}"
            by_level[levels.get(job["id"], 0)].append(label)
        for lvl in sorted(by_level):
            out.append(f"- L{lvl}: {'; '.join(by_level[lvl])}")
        out.append("")
    out += ["## Quality commands", "", "| Category | Tool | Job | Events | Command | Flags |",
            "| --- | --- | --- | --- | --- | --- |"]
    for wf in wfs:
        for job in wf["jobs"]:
            for c in job["commands"]:
                if set(c["categories"]) & (QUALITY | {"install"}):
                    cmd = c["cmd"].replace("|", "\\|")
                    out.append(f"| {', '.join(c['categories'])} | {', '.join(c['tools'])} | `{wf['file']}#{job['id']}` "
                               f"| {', '.join(wf['effective_events'])} | `{cmd[:90]}` | {', '.join(c['flags']) or '—'} |")
    out += ["", "## Findings", ""]
    order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    for f in sorted(audit.findings, key=lambda f: (order[f["severity"]], f["id"], f["location"])):
        hint = f" → {f['hint']}" if f["hint"] else ""
        out.append(f"- **{f['severity']}** `{f['id']}` `{f['location']}` — {f['message']}{hint}")
    if not audit.findings:
        out.append("None.")
    return "\n".join(out) + "\n"


def detect_default_branch(root: Path) -> str:
    try:
        ref = subprocess.run(["git", "-C", str(root), "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
                             capture_output=True, text=True, check=True).stdout.strip()
        return ref.split("/", 1)[1] if "/" in ref else "main"
    except (OSError, subprocess.CalledProcessError):
        return "main"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", nargs="?", default=".", type=Path, help="project root (default: .)")
    parser.add_argument("--json", type=Path, help="write the inventory and findings as JSON")
    parser.add_argument("--default-branch", help="default branch name (default: origin/HEAD or main)")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    audit = Audit(root, args.default_branch or detect_default_branch(root)).run()
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        data = {"root": str(root), "default_branch": audit.default_branch,
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "workflows": audit.workflows, "findings": audit.findings, "errors": audit.errors}
        args.json.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    sys.stdout.write(markdown(audit))
    return 1 if audit.errors else 0


if __name__ == "__main__":
    sys.exit(main())
