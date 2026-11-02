#!/usr/bin/env python3
"""Compare ci-tuning snapshots taken before and after a change.

    compare.py coverage BEFORE.json AFTER.json [--accept REGEX ...] [--required NAME ...]
                        [--required-from OWNER/REPO:BRANCH]
    compare.py timing   BEFORE.json AFTER.json [--max-regression 0.10]
    compare.py tests    --before PATH ... --after PATH ... [--strip-prefix PREFIX ...]

coverage reads workflow_audit.py --json output, timing reads run_stats.py runs
--json output, and tests reads JUnit XML files, directories or globs.
Prints Markdown and exits 1 on a blocking difference:

  coverage  a check category no longer runs on an event; a category:tool check
            or one of its strict flags disappears without --accept; a new
            continue-on-error, `|| true`, --passWithNoTests or `set +e`; a
            required check that the new workflows no longer produce
  timing    commit wall P50 worse by more than --max-regression, or a higher
            share of flaky runs (failed first, passed on a rerun); a higher
            first-attempt failure rate is only a warning, since PR runs also
            fail on genuinely broken code
  tests     a test missing, newly skipped or newly failing after the change

--accept takes a regex matched against `category:tool` or
`category:tool:flag`, for replacements already proven equivalent.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

QUALITY = {"lint", "format", "typecheck", "test", "build", "security", "install"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dur(seconds):
    if seconds is None:
        return "—"
    seconds = int(round(seconds))
    return f"{seconds}s" if seconds < 60 else f"{seconds // 60}m{seconds % 60:02d}s"


# ---------- coverage ----------

def inventory(path):
    data = load(path)
    inv = {"checks": defaultdict(set), "categories": defaultdict(set), "flags": defaultdict(set),
           "weaken": Counter(), "continue_on_error": Counter(), "names": set(), "dynamic": set(),
           "path_filtered": set()}
    for wf in data.get("workflows", []):
        events = set(wf.get("effective_events") or wf.get("events") or [])
        has_quality = False
        for job in wf.get("jobs", []):
            for name in job.get("check_names", []):
                if name.endswith(" (*)"):
                    inv["dynamic"].add(name[:-4])
                else:
                    inv["names"].add(name)
            for command in job.get("commands", []):
                checks = [c for c in command.get("checks", []) if c.split(":", 1)[0] in QUALITY]
                if not checks:
                    continue
                has_quality = True
                for check in checks:
                    inv["checks"][check] |= events
                    inv["categories"][check.split(":", 1)[0]] |= events
                    inv["flags"][check] |= set(command.get("flags", []))
                # Weakening is counted per category so that a tool swap does not hide or invent it.
                for category in {c.split(":", 1)[0] for c in checks}:
                    for marker in command.get("weaken", []):
                        inv["weaken"][(category, marker)] += 1
                    if command.get("continue_on_error") is True or job.get("continue_on_error") is True:
                        inv["continue_on_error"][category] += 1
        pr_filters = (wf.get("event_filters") or {}).get("pull_request", {})
        if has_quality and ("paths" in pr_filters or "paths-ignore" in pr_filters):
            inv["path_filtered"].add(wf["file"])
    return inv


def gh(path):
    proc = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github+json", path],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "failed")
    return json.loads(proc.stdout or "null")


def required_from(spec):
    repo, _, branch = spec.rpartition(":")
    if not repo or not branch:
        sys.exit("--required-from expects OWNER/REPO:BRANCH")
    names, notes = set(), []
    try:
        for rule in gh(f"repos/{repo}/rules/branches/{branch}") or []:
            if rule.get("type") == "required_status_checks":
                for check in (rule.get("parameters") or {}).get("required_status_checks", []):
                    names.add(check.get("context"))
    except RuntimeError as exc:
        notes.append(f"rulesets unreadable: {exc}")
    try:
        protection = gh(f"repos/{repo}/branches/{branch}/protection/required_status_checks")
        names |= set(protection.get("contexts") or [])
        names |= {c.get("context") for c in protection.get("checks") or []}
    except RuntimeError as exc:
        notes.append(f"classic branch protection unreadable: {exc}")
    return {n for n in names if n}, notes


def cmd_coverage(args):
    before, after = inventory(args.before), inventory(args.after)
    accept = [re.compile(p) for p in args.accept]

    def accepted(text):
        return any(rx.search(text) for rx in accept)

    blocking, warnings, notes = [], [], []
    for cat, events in sorted(before["categories"].items()):
        lost = events - after["categories"].get(cat, set())
        if lost:
            blocking.append(f"Category `{cat}` no longer runs on: {', '.join(sorted(lost))}.")
    for check, events in sorted(before["checks"].items()):
        lost = events - after["checks"].get(check, set())
        if not lost:
            continue
        message = f"`{check}` no longer runs on: {', '.join(sorted(lost))}"
        if before["flags"][check]:
            message += f" (its strict flags: {', '.join(sorted(before['flags'][check]))})"
        if accepted(check):
            notes.append(message + " — accepted.")
        else:
            blocking.append(message + ". Pass --accept if it was replaced by a proven equivalent.")
    for check, flags in sorted(before["flags"].items()):
        if check not in after["checks"]:
            continue
        for flag in sorted(flags - after["flags"].get(check, set())):
            text = f"`{check}` lost strict flag `{flag}`"
            if accepted(f"{check}:{flag}"):
                notes.append(text + " — accepted.")
            else:
                blocking.append(text + ".")
    for (category, marker), count in sorted(after["weaken"].items()):
        old = before["weaken"].get((category, marker), 0)
        if count > old:
            blocking.append(f"`{category}` commands using `{marker}`: {old} → {count}.")
    for category, count in sorted(after["continue_on_error"].items()):
        old = before["continue_on_error"].get(category, 0)
        if count > old:
            blocking.append(f"`{category}` commands under continue-on-error: {old} → {count}.")
    for wf in sorted(after["path_filtered"] - before["path_filtered"]):
        warnings.append(f"`{wf}` now filters pull_request by paths; required checks in it stay Pending when skipped.")
    for check in sorted(set(after["checks"]) - set(before["checks"])):
        notes.append(f"New check `{check}` on: {', '.join(sorted(after['checks'][check]))}.")

    required = set(args.required)
    if args.required_from:
        names, api_notes = required_from(args.required_from)
        required |= names
        notes += api_notes

    def produced(name):
        return name in after["names"] or any(name == p or name.startswith(p + " (") for p in after["dynamic"])

    for name in sorted(required):
        if not produced(name):
            blocking.append(f"Required check `{name}` is not produced by the new workflows.")
    removed = sorted(name for name in before["names"] - after["names"] if not produced(name))
    if removed:
        warnings.append("Check names no longer produced: " + ", ".join(f"`{n}`" for n in removed)
                        + ". Confirm none of them is required.")
    if after["dynamic"]:
        notes.append("Dynamic matrices are compared by job name prefix only: "
                     + ", ".join(f"`{p}`" for p in sorted(after["dynamic"])) + ".")
    if not required:
        notes.append("No required checks were given; pass --required or --required-from.")

    out = ["# Coverage comparison", "",
           f"Checks before: {len(before['checks'])} · after: {len(after['checks'])} · "
           f"required checked: {len(required)}", ""]
    for title, items in (("Blocking", blocking), ("Warnings", warnings), ("Notes", notes)):
        out += [f"## {title}", ""] + ([f"- {i}" for i in items] or ["None."]) + [""]
    out.append("Result: " + ("FAIL" if blocking else "PASS"))
    sys.stdout.write("\n".join(out) + "\n")
    return 1 if blocking else 0


# ---------- timing ----------

def first_attempt_failure(data):
    runs = data.get("runs", [])
    return (sum(r.get("first_attempt_failed", False) for r in runs) / len(runs)) if runs else None, len(runs)


def flaky_runs(data):
    runs = data.get("runs", [])
    flaky = [r for r in runs if r.get("flaky_jobs")]
    jobs = sorted({f"{r.get('workflow')} / {job}" for r in flaky for job in r["flaky_jobs"]})
    return (len(flaky) / len(runs)) if runs else None, len(flaky), jobs


def ratio(before, after):
    if not before or after is None:
        return "—"
    return f"{before / after:.2f}x" if after else "∞"


def cmd_timing(args):
    before, after = load(args.before), load(args.after)
    b, a = before["summary"], after["summary"]
    blocking, warnings = [], []
    bc, ac = b["commits"], a["commits"]
    out = ["# Timing comparison", "",
           "| Metric | Before | After | Speed-up |", "| --- | --- | --- | --- |",
           f"| Commit wall P50 (n={bc['n']} → {ac['n']}) | {dur(bc['p50'])} | {dur(ac['p50'])} | {ratio(bc['p50'], ac['p50'])} |",
           f"| Commit wall P95 | {dur(bc['p95'])} | {dur(ac['p95'])} | {ratio(bc['p95'], ac['p95'])} |"]
    bf, bn = first_attempt_failure(before)
    af, an = first_attempt_failure(after)
    if bf is not None and af is not None:
        out.append(f"| First-attempt failure rate (runs {bn} → {an}) | {bf:.0%} | {af:.0%} | — |")
    bk, bk_n, _ = flaky_runs(before)
    ak, ak_n, ak_jobs = flaky_runs(after)
    if bk is not None and ak is not None:
        out.append(f"| Flaky runs (failed, then passed on rerun) | {bk_n} ({bk:.0%}) | {ak_n} ({ak:.0%}) | — |")
    out += ["", "## Workflows", "", "| Workflow | Runs | Wall P50 | Wall P95 | Rerun rate |", "| --- | --- | --- | --- | --- |"]
    for name in sorted(set(b["workflows"]) | set(a["workflows"])):
        x, y = b["workflows"].get(name, {}), a["workflows"].get(name, {})
        out.append(f"| {name} | {x.get('runs', 0)} → {y.get('runs', 0)} | {dur(x.get('wall_p50'))} → {dur(y.get('wall_p50'))} "
                   f"| {dur(x.get('wall_p95'))} → {dur(y.get('wall_p95'))} | "
                   f"{x.get('rerun_rate', 0):.0%} → {y.get('rerun_rate', 0):.0%} |")
    out += ["", "## Jobs", "", "| Job | Queue P50 | Setup P50 | Work P50 | Total P50 | Total P95 | On chain |",
            "| --- | --- | --- | --- | --- | --- | --- |"]
    keys = sorted(set(b["jobs"]) | set(a["jobs"]),
                  key=lambda k: -max((b["jobs"].get(k) or {}).get("total_p50") or 0,
                                     (a["jobs"].get(k) or {}).get("total_p50") or 0))
    for key in keys[:args.top]:
        x, y = b["jobs"].get(key, {}), a["jobs"].get(key, {})

        def pair(metric):
            return f"{dur(x.get(metric))} → {dur(y.get(metric))}"

        out.append(f"| {key} | {pair('queue_p50')} | {pair('setup_p50')} | {pair('work_p50')} | {pair('total_p50')} "
                   f"| {pair('total_p95')} | {x.get('on_chain_share', 0):.0%} → {y.get('on_chain_share', 0):.0%} |")
    out += ["", "## Critical chains", "", "Before:"]
    out += [f"- {c['workflow']}: {c['chain']} ({c['runs']} runs, P50 {dur(c['wall_p50'])})" for c in b.get("chains", [])[:3]]
    out += ["", "After:"]
    out += [f"- {c['workflow']}: {c['chain']} ({c['runs']} runs, P50 {dur(c['wall_p50'])})" for c in a.get("chains", [])[:3]]

    enough = bc["n"] >= 5 and ac["n"] >= 5
    if not enough:
        warnings.append("Fewer than 5 commits on one side; treat the comparison as a trend only.")
    if enough and bc["p50"] and ac["p50"] and ac["p50"] > bc["p50"] * (1 + args.max_regression):
        blocking.append(f"Commit wall P50 regressed from {dur(bc['p50'])} to {dur(ac['p50'])}.")
    if bk is not None and ak is not None and ak_n and ak > bk:
        blocking.append(f"Flaky runs rose from {bk:.0%} to {ak:.0%} ({', '.join(ak_jobs)}). Reproduce with reruns "
                        "of one commit before accepting the change.")
    if bf is not None and af is not None and bn >= 5 and an >= 5 and af - bf > 0.05:
        warnings.append(f"First-attempt failure rate rose from {bf:.0%} to {af:.0%}. PR runs also fail on broken "
                        "code; rerun one commit at least 3 times to rule out new flakiness.")
    if before.get("filters", {}).get("event") != after.get("filters", {}).get("event"):
        warnings.append("The two snapshots use different event filters.")
    out += [""]
    for title, items in (("Blocking", blocking), ("Warnings", warnings)):
        out += [f"## {title}", ""] + ([f"- {i}" for i in items] or ["None."]) + [""]
    out.append("Result: " + ("FAIL" if blocking else "PASS"))
    sys.stdout.write("\n".join(out) + "\n")
    return 1 if blocking else 0


# ---------- tests ----------

def junit_cases(paths, strip):
    files = []
    for raw in paths:
        for match in glob.glob(raw, recursive=True) or [raw]:
            path = Path(match)
            files += sorted(path.rglob("*.xml")) if path.is_dir() else ([path] if path.is_file() else [])
    counts, status = Counter(), {}
    rank = {"passed": 0, "skipped": 1, "failed": 2}
    for path in files:
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            sys.exit(f"{path}: {exc}")
        parents = {child: parent for parent in root.iter() for child in parent}
        for case in root.iter("testcase"):
            suite = parents.get(case)
            while suite is not None and suite.tag != "testsuite":
                suite = parents.get(suite)
            owner = case.get("file") or case.get("classname") or (suite.get("name") if suite is not None else "")
            for prefix in strip:
                if owner.startswith(prefix):
                    owner = owner[len(prefix):]
            owner = re.sub(r"^(?:\./)+", "", owner)
            test_id = f"{owner}::{case.get('name')}"
            if case.find("failure") is not None or case.find("error") is not None:
                state = "failed"
            elif case.find("skipped") is not None:
                state = "skipped"
            else:
                state = "passed"
            counts[test_id] += 1
            if rank[state] >= rank.get(status.get(test_id, "passed"), 0):
                status[test_id] = state
    return counts, status, len(files)


def cmd_tests(args):
    bc, bs, bfiles = junit_cases(args.before, args.strip_prefix)
    ac, as_, afiles = junit_cases(args.after, args.strip_prefix)
    if not bc or not ac:
        sys.exit(f"No test cases found (before: {bfiles} files, after: {afiles} files).")
    missing = sorted(set(bc) - set(ac))
    skipped = sorted(t for t in ac if as_[t] == "skipped" and bs.get(t, "skipped") != "skipped")
    failing = sorted(t for t in ac if as_[t] == "failed" and bs.get(t) != "failed")
    duplicated = sorted(t for t in ac if ac[t] > bc.get(t, 1))
    added = sorted(set(ac) - set(bc))

    def tally(status):
        c = Counter(status.values())
        return f"{len(status)} tests: {c['passed']} passed, {c['failed']} failed, {c['skipped']} skipped"

    out = ["# Test set comparison", "", f"Before ({bfiles} files): {tally(bs)}", f"After ({afiles} files): {tally(as_)}", ""]
    for title, items, block in (("Missing after the change", missing, True), ("Newly skipped", skipped, True),
                                ("Newly failing", failing, True), ("Run more often than before", duplicated, False),
                                ("New tests", added, False)):
        out += [f"## {title} ({len(items)})", ""]
        out += [f"- `{t}`" for t in items[:50]] + ([f"- … {len(items) - 50} more"] if len(items) > 50 else [])
        out += ["None.", ""] if not items else [""]
    blocking = bool(missing or skipped or failing)
    out.append("Result: " + ("FAIL" if blocking else "PASS"))
    sys.stdout.write("\n".join(out) + "\n")
    return 1 if blocking else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    cov = sub.add_parser("coverage", help="checks, events, strict flags and required checks")
    cov.add_argument("before")
    cov.add_argument("after")
    cov.add_argument("--accept", action="append", default=[], help="regex for accepted removals")
    cov.add_argument("--required", action="append", default=[], help="required check name (repeatable)")
    cov.add_argument("--required-from", help="read required checks from OWNER/REPO:BRANCH via gh")
    tim = sub.add_parser("timing", help="run_stats.py summaries")
    tim.add_argument("before")
    tim.add_argument("after")
    tim.add_argument("--max-regression", type=float, default=0.10, help="allowed P50 regression (default: 0.10)")
    tim.add_argument("--top", type=int, default=15, help="jobs to list (default: 15)")
    tst = sub.add_parser("tests", help="JUnit test sets")
    tst.add_argument("--before", nargs="+", required=True)
    tst.add_argument("--after", nargs="+", required=True)
    tst.add_argument("--strip-prefix", action="append", default=[], help="prefix removed from test file paths")
    args = parser.parse_args(argv)
    return {"coverage": cmd_coverage, "timing": cmd_timing, "tests": cmd_tests}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
