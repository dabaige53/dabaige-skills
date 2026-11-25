#!/usr/bin/env python3
"""Rank test functions by cleanup value with TypeSafe judgments and code-side decisions.

    classify.py [paths ...] [--root DIR] [--dry-run] [--json FILE] [--limit N] [--jobs N] [--model NAME]

TypeSafe answers one atomic yes/no question per judgment about each test; the decision table below turns
those answers plus scan.py signals into DELETE, MERGE, REWRITE, INVESTIGATE, or KEEP. Test source is sent
to api.typesafe.ai with TYPESAFE_API_KEY unless --dry-run is set. The script never edits files.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan  # noqa: E402

API_URL = "https://api.typesafe.ai/v1/systemone"
SOURCE_CHARS = 12_000
YES, NO = 0.7, 0.3
ORDER = {"DELETE": 0, "MERGE": 1, "REWRITE": 2, "INVESTIGATE": 3, "ERROR": 4, "KEEP": 5}


def noul(instructions, true, false):
    return {"type": "noul", "instructions": instructions, "criteria": {"true": true, "false": false}}


QUESTIONS = {
    "echoes_setup": noul(
        "Is every expected value in `test_source` a value the test itself put into a stub, mock, or setup?",
        "The test stubs a dependency to return 0.9 and then asserts the result is 0.9.",
        "The expected value is a result the code under test has to compute, such as 90 for converting 100 at rate 0.9."),
    "recomputes_expected": noul(
        "Does `test_source` compute its expected value by repeating the logic of the code under test?",
        "The test calls the same helper or repeats the same formula to build the expected value.",
        "The expected value is a literal or comes from an independent source."),
    "checks_outcome": noul(
        "Does `test_source` assert a specific return value, stored state, raised error, or emitted output?",
        "An assertion compares a result, saved record, error type, or rendered output with a specific expected value.",
        "Assertions only check that something is not empty, not null, truthy, or that a mock was called."),
    "only_mock_calls": noul(
        "Do all assertions in `test_source` only check that mocked methods were called?",
        "Assertions are limited to called, called_once, called_with, or toHaveBeenCalled style checks on mocks.",
        "At least one assertion checks a result or state of the code under test."),
    "passes_on_wrong_value": noul(
        "Would the assertions in `test_source` still pass if the code under test returned a wrong but non-empty value?",
        "Assertions such as `is not None`, `len(x) > 0`, or `toBeTruthy()` accept wrong results.",
        "The assertions compare against exact expected values that a wrong result would fail."),
    "dependency_only": noul(
        "Does `test_source` only exercise a third-party library, framework, or the language itself?",
        "The test sorts with the standard library, saves with an uncustomized ORM, or round-trips a plain getter and setter.",
        "The test runs project code that adds its own logic, configuration, or adaptation."),
    "private_detail": noul(
        "Does `test_source` assert on private helpers, internal call order, or internal data structures?",
        "The test checks that internal helpers ran in a certain order or inspects a private field.",
        "The test only observes public results, state, or side effects."),
    "timing_dependent": noul(
        "Does `test_source` depend on sleeps, the wall clock, unseeded randomness, or network access?",
        "The test sleeps, reads the current time, uses random values without a seed, or calls a real network service.",
        "The test is deterministic and isolated."),
    "protected_risk": noul(
        "Is the behavior tested in `test_source` about security, money, data integrity, migrations, concurrency, "
        "or a public API contract?",
        "The test covers authorization, billing, data loss, schema migration, retries, idempotency, or a published format.",
        "The test covers ordinary internal behavior."),
}
DECIDING = ("echoes_setup", "recomputes_expected", "checks_outcome", "only_mock_calls", "passes_on_wrong_value",
            "dependency_only", "protected_risk")


# ---------- collect ----------

def py_tests(path, text):
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    found = []
    for func, _ in scan.py_test_functions(tree):
        start = min([d.lineno for d in func.decorator_list] + [func.lineno])
        found.append((func.name, start, func.end_lineno or func.lineno))
    return found


def js_tests(text, lines):
    found = []
    for m in scan.JS_TEST.finditer(text):
        kind, mod = m.group("kind"), m.group("mod") or ""
        if kind.endswith("describe") or mod == ".todo":
            continue
        close = scan.closing_bracket(text, m.end() - 1)
        title = scan.TEST_TITLE.match(text, m.end(), close)
        name = title.group(0).strip(" ,\n\t")[1:-1] if title else kind
        found.append((name, lines.at(m.start()), lines.at(close)))
    return found


def go_tests(text, lines):
    found = []
    for m in scan.GO_TEST.finditer(text):
        close = scan.closing_bracket(text, m.end() - 1)
        found.append((m.group(1), lines.at(m.start()), lines.at(close)))
    return found


def collect(paths, root):
    """Test units with their source and the scan.py signals that fall inside them."""
    rep = scan.Report("test", None)
    files = scan.scan_test(paths, root, rep)
    hits = {}
    for signal, items in rep.items.items():
        for shown, line, _ in items:
            hits.setdefault(shown, []).append((line, signal))
    for signal, groups in rep.groups.items():
        for _, members in groups:
            for shown, line in members:
                hits.setdefault(shown, []).append((line, signal))
    units, skipped = [], 0
    for path in files:
        suffix = path.suffix.lower()
        if scan.test_kind(scan.rel(root, path)) != "code" or suffix not in scan.CODE_EXTS:
            continue
        text = scan.read(path)
        if text is None:
            continue
        lines = scan.Lines(text)
        if suffix == ".py":
            found = py_tests(path, text)
        elif suffix in scan.JS_EXTS:
            found = js_tests(text, lines)
        elif suffix == ".go":
            found = go_tests(text, lines)
        else:
            skipped += 1
            continue
        shown = scan.show(path)
        for name, start, end in found:
            source = "\n".join(lines.rows[start - 1:end])
            units.append({
                "path": shown, "line": start, "name": name,
                "signals": sorted({s for n, s in hits.get(shown, []) if start <= n <= end}),
                "source": source if len(source) <= SOURCE_CHARS else source[:SOURCE_CHARS] + "\n… (truncated)",
            })
    return units, skipped


# ---------- ask ----------

def payload(unit, model):
    state = {"file": unit["path"], "test_name": unit["name"], "test_source": unit["source"]}
    if unit["signals"]:
        state["static_signals"] = unit["signals"]
    return {"model": model, "state": state, "questions": QUESTIONS}


def ask(body, key, retries=4):
    data = json.dumps(body).encode()
    for attempt in range(retries + 1):
        request = urllib.request.Request(API_URL, data=data, method="POST", headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)["answers"]
        except urllib.error.HTTPError as error:
            if error.code != 429 or attempt == retries:
                raise RuntimeError(f"HTTP {error.code}: {error.read().decode(errors='replace')[:200]}") from error
            time.sleep(float(error.headers.get("retry-after") or 2 ** attempt))
    raise RuntimeError("unreachable")


# ---------- decide ----------

def decide(p, signals):
    """Truth table: (action, strength, evidence). `p` maps question name to probability of yes."""
    yes = lambda q: p[q] >= YES  # noqa: E731
    no = lambda q: p[q] <= NO  # noqa: E731
    static = set(signals)
    if yes("protected_risk"):
        if static & {"no-assertion", "skipped"} or yes("echoes_setup") or yes("passes_on_wrong_value"):
            return "INVESTIGATE", p["protected_risk"], "protected risk with a weak or missing check"
        return "KEEP", 0, ""
    if "skipped" in static:
        return "DELETE", 0.9, "skipped or focused test; restore it only if the behavior still matters"
    if "no-assertion" in static and no("checks_outcome"):
        return "DELETE", 0.95, "no assertion and no checked outcome"
    if yes("dependency_only"):
        return "DELETE", p["dependency_only"], "only exercises a library, framework, or language feature"
    if (yes("echoes_setup") or yes("recomputes_expected")) and not yes("checks_outcome"):
        return "DELETE", max(p["echoes_setup"], p["recomputes_expected"]), "tautological oracle"
    if "duplicate-body" in static:
        return "MERGE", 0.8, "same body as another test"
    if yes("only_mock_calls") and no("checks_outcome"):
        return "REWRITE", p["only_mock_calls"], "asserts only mock calls; assert the resulting state"
    if yes("passes_on_wrong_value"):
        return "REWRITE", p["passes_on_wrong_value"], "assertion accepts wrong values"
    if yes("echoes_setup") or yes("recomputes_expected"):
        return "REWRITE", max(p["echoes_setup"], p["recomputes_expected"]), "expected value mirrors setup or logic"
    if yes("private_detail"):
        return "REWRITE", p["private_detail"], "coupled to implementation details"
    if yes("timing_dependent") or "sleep" in static:
        return "REWRITE", max(p["timing_dependent"], 0.7 if "sleep" in static else 0), "timing or environment dependent"
    if "large-parametrize" in static:
        return "MERGE", 0.6, "large parameter matrix; keep representative partitions"
    unsettled = [q for q in DECIDING if NO < p[q] < YES]
    if unsettled:
        return "INVESTIGATE", 0.5, "unsettled: " + ", ".join(unsettled)
    return "KEEP", 0, ""


def classify(unit, model, key):
    body = payload(unit, model)
    try:
        answers = ask(body, key)
        probs = {q: answers[q]["noul"] for q in QUESTIONS}
    except (RuntimeError, OSError, KeyError, ValueError) as error:
        return {**unit, "action": "ERROR", "strength": 0, "evidence": str(error), "answers": None, "payload": body}
    action, strength, evidence = decide(probs, unit["signals"])
    return {**unit, "action": action, "strength": round(strength, 3), "evidence": evidence,
            "answers": probs, "payload": body}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rank tests by cleanup value with TypeSafe. Never edits files.")
    parser.add_argument("paths", nargs="*", default=["."], help="files or directories (default: .)")
    parser.add_argument("--root", help="where references are counted and paths resolve (default: repository root)")
    parser.add_argument("--dry-run", action="store_true", help="list tests and print one request; send nothing")
    parser.add_argument("--json", metavar="FILE", help="write every result with its answers and exact payload")
    parser.add_argument("--limit", type=int, default=0, metavar="N", help="classify at most N tests (default: all)")
    parser.add_argument("--jobs", type=int, default=4, metavar="N", help="parallel requests (default: 4)")
    parser.add_argument("--model", default="jev-latest", help="TypeSafe model (default: jev-latest)")
    parser.add_argument("--all", action="store_true", help="also print KEEP rows")
    args = parser.parse_args(argv)
    paths = [Path(p).expanduser() for p in args.paths]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        parser.error("not found: " + ", ".join(missing))
    root = Path(args.root).expanduser() if args.root else scan.git_root(paths[0])
    units, skipped = collect(paths, root)
    if args.limit:
        units = units[:args.limit]
    note = f"; {skipped} files in unsupported languages skipped" if skipped else ""
    if args.dry_run or not units:
        print(f"{len(units)} tests would be sent to {API_URL}{note}")
        for unit in units:
            print(f"  {unit['path']}:{unit['line']}  {unit['name']}  {' '.join(unit['signals'])}")
        if units:
            print("\nfirst request:\n" + json.dumps(payload(units[0], args.model), ensure_ascii=False, indent=2))
        return 0
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        parser.error("TYPESAFE_API_KEY is not set; use --dry-run to preview without sending")
    with ThreadPoolExecutor(max(args.jobs, 1)) as pool:
        results = list(pool.map(lambda u: classify(u, args.model, key), units))
    results.sort(key=lambda r: (ORDER[r["action"]], -r["strength"], r["path"], r["line"]))
    if args.json:
        Path(args.json).write_text(json.dumps(results, ensure_ascii=False, indent=2))
    counts = {a: sum(r["action"] == a for r in results) for a in ORDER}
    print(f"{len(results)} tests: " + ", ".join(f"{n} {a}" for a, n in counts.items() if n) + note)
    print("\nAction | Location | Evidence")
    for r in results:
        if r["action"] != "KEEP" or args.all:
            print(f"{r['action']} | {r['path']}:{r['line']} {r['name']} | {r['evidence']}"
                  + (f" ({r['strength']:.2f})" if r["strength"] else ""))
    return 1 if counts["ERROR"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
