#!/usr/bin/env python3
"""Plan balanced test shards from recorded durations.

    shard_plan.py (--junit PATH ... | --durations FILE) [--by file|classname|suite]
                  [--shards N | --max-shards N] [--overhead SECONDS] [--all-files FILE]
                  [--out-dir DIR] [--json OUT]

Inputs are JUnit XML reports (files, directories or globs) or a JSON mapping of
test id to seconds such as pytest-split's .test_durations (ids are grouped by
the part before "::"). Durations are summed per unit (test file by default),
then assigned longest-first to the least loaded shard.

Without --shards the script predicts wall time for 1..--max-shards shards as
overhead + largest shard, and recommends the smallest count within 5% of the
best. --all-files lists every current test unit, one per line: units without
timing get the median duration and stale timing entries are dropped, so the
plan never leaves a test file out. --out-dir writes shard-<i>.txt files.
"""

from __future__ import annotations

import argparse
import glob
import heapq
import json
import statistics
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


def junit_files(paths):
    files = []
    for raw in paths:
        matches = glob.glob(raw, recursive=True) or [raw]
        for match in matches:
            path = Path(match)
            if path.is_dir():
                files += sorted(path.rglob("*.xml"))
            elif path.is_file():
                files.append(path)
    return files


def from_junit(paths, by):
    units = defaultdict(float)
    for path in junit_files(paths):
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            sys.exit(f"{path}: {exc}")
        parents = {child: parent for parent in root.iter() for child in parent}
        for case in root.iter("testcase"):
            suite = parents.get(case)
            while suite is not None and suite.tag != "testsuite":
                suite = parents.get(suite)
            suite_file = suite.get("file") if suite is not None else None
            suite_name = suite.get("name") if suite is not None else None
            if by == "suite":
                unit = suite_file or suite_name
            elif by == "file":
                unit = case.get("file") or suite_file or case.get("classname")
            else:
                unit = case.get("classname") or suite_name
            try:
                seconds = float(case.get("time") or 0)
            except ValueError:
                seconds = 0.0
            units[unit or "<unknown>"] += seconds
    return dict(units)


def from_durations(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    units = defaultdict(float)
    for test_id, seconds in data.items():
        units[test_id.split("::", 1)[0]] += float(seconds)
    return dict(units)


def lpt(units, shards):
    heap = [(0.0, i) for i in range(shards)]
    plan = [[] for _ in range(shards)]
    loads = [0.0] * shards
    for name, seconds in sorted(units.items(), key=lambda kv: (-kv[1], kv[0])):
        load, i = heapq.heappop(heap)
        plan[i].append(name)
        loads[i] = load + seconds
        heapq.heappush(heap, (loads[i], i))
    return plan, loads


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--junit", nargs="+", help="JUnit XML files, directories or globs")
    source.add_argument("--durations", help="JSON mapping of test id to seconds")
    parser.add_argument("--by", choices=("file", "classname", "suite"), default="file",
                        help="grouping unit for JUnit input (default: file, falling back to classname)")
    parser.add_argument("--shards", type=int, help="plan exactly N shards")
    parser.add_argument("--max-shards", type=int, default=12, help="largest count to evaluate (default: 12)")
    parser.add_argument("--overhead", type=float, default=0.0,
                        help="fixed seconds per shard job: queue + setup + teardown (default: 0)")
    parser.add_argument("--all-files", help="file listing every current test unit, one per line")
    parser.add_argument("--out-dir", help="write shard-<i>.txt files here")
    parser.add_argument("--json", help="write the plan as JSON")
    args = parser.parse_args(argv)

    units = from_junit(args.junit, args.by) if args.junit else from_durations(args.durations)
    notes = []
    if args.all_files:
        current = [line.strip() for line in Path(args.all_files).read_text(encoding="utf-8").splitlines() if line.strip()]
        known = [v for v in units.values() if v > 0]
        fill = statistics.median(known) if known else 1.0
        missing = [u for u in current if u not in units]
        stale = [u for u in units if u not in set(current)]
        units = {u: units.get(u, fill) for u in current}
        if missing:
            notes.append(f"{len(missing)} unit(s) without timing were given the median {fill:.1f}s.")
        if stale:
            notes.append(f"{len(stale)} timing entr(ies) no longer listed were dropped.")
    if not units:
        sys.exit("No test units found.")
    zero = sum(1 for v in units.values() if v <= 0)
    if zero:
        notes.append(f"{zero} unit(s) have zero recorded time; check that the reports include timings.")
    total = sum(units.values())
    largest_name, largest = max(units.items(), key=lambda kv: kv[1])

    table = []
    for n in range(1, max(1, min(args.max_shards, len(units))) + 1):
        _, loads = lpt(units, n)
        table.append({"shards": n, "largest_shard": max(loads), "predicted_wall": args.overhead + max(loads)})
    if args.shards:
        chosen = args.shards
    else:
        best = min(row["predicted_wall"] for row in table)
        chosen = next(row["shards"] for row in table if row["predicted_wall"] <= best * 1.05)
    plan, loads = lpt(units, chosen)

    out = ["# Shard plan", "",
           f"Units: {len(units)} · total {total:.0f}s · largest unit {largest:.0f}s (`{largest_name}`, the lower bound "
           f"for any shard) · overhead per shard {args.overhead:.0f}s", "",
           "| Shards | Largest shard | Predicted wall | vs 1 shard |", "| --- | --- | --- | --- |"]
    base = table[0]["predicted_wall"]
    for row in table:
        mark = " ←" if row["shards"] == chosen else ""
        out.append(f"| {row['shards']}{mark} | {row['largest_shard']:.0f}s | {row['predicted_wall']:.0f}s | "
                   f"{base / row['predicted_wall']:.2f}x |")
    out += ["", f"## Plan for {chosen} shard(s)", "", "| Shard | Units | Seconds |", "| --- | --- | --- |"]
    for i, (names, load) in enumerate(zip(plan, loads), 1):
        out.append(f"| {i} | {len(names)} | {load:.0f} |")
    spread = max(loads) / (sum(loads) / len(loads)) if sum(loads) else 1.0
    out += ["", f"Largest / mean shard: {spread:.2f}."]
    out += [f"- {note}" for note in notes]
    sys.stdout.write("\n".join(out) + "\n")

    if args.out_dir:
        directory = Path(args.out_dir)
        directory.mkdir(parents=True, exist_ok=True)
        for i, names in enumerate(plan, 1):
            (directory / f"shard-{i}.txt").write_text("".join(f"{n}\n" for n in sorted(names)), encoding="utf-8")
    if args.json:
        Path(args.json).write_text(json.dumps({
            "units": units, "overhead": args.overhead, "table": table, "shards": chosen,
            "plan": [{"shard": i, "seconds": load, "units": sorted(names)}
                     for i, (names, load) in enumerate(zip(plan, loads), 1)],
            "notes": notes}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
