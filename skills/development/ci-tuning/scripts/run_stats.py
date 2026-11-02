#!/usr/bin/env python3
"""Collect GitHub Actions timing and cache statistics for ci-tuning.

    run_stats.py runs   [--repo OWNER/REPO] [--workflow FILE ...] [--event pull_request] [--branch NAME]
                        [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--limit 30] [--include-cancelled]
                        [--logs N] [--json OUT]
    run_stats.py caches [--repo OWNER/REPO] [--json OUT]

Reads through the authenticated `gh` CLI and prints a Markdown summary.

runs: every workflow run is measured on its first attempt. queue = job started -
job created (a job with `needs` is created when its dependencies finish); steps
are classified by name into setup, work and teardown; the commit wall time spans
all selected runs of one head SHA, from the first run's creation to the last
job's completion. The critical chain walks back from the last job to the job
that finished when it was created. --logs N downloads up to N job logs and
counts cache restores (exact, restore-key, miss).

caches: groups cache entries by key family and ref, and flags families without
a default-branch entry, PR-scoped storage share, total size against the 10 GB
limit, and key churn on the default branch.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from urllib.parse import urlencode

KEEP_CONCLUSIONS = {"success", "failure", "timed_out"}
FAILED = {"failure", "timed_out"}
TEARDOWN = re.compile(r"^(?:Post |Complete job$|Stop containers$)|upload[- ]?artifact|\bupload\b|save[- ]?cache", re.I)
SETUP = re.compile(r"^(?:Set up job|Set up runner|Initialize containers)$|checkout|setup|set up|install|restore"
                   r"|cache|download|toolchain|login|docker pull|apt-get|npm ci|pnpm i\b|uv sync|bundle"
                   r"|go mod download|cargo fetch|prepare|configure", re.I)
CACHE_LINES = {
    "exact": re.compile(r"Cache hit for: "),
    "partial": re.compile(r"Cache hit for restore-key: "),
    "miss": re.compile(r"Cache not found for input keys|cache is not found|No cache found"
                       r"|No GitHub Actions cache found|Cache not found for keys", re.I),
}
GIB = 1024 ** 3


class GhError(RuntimeError):
    pass


def gh(path, params=None):
    if params:
        path += ("&" if "?" in path else "?") + urlencode(params)
    proc = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github+json", path],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise GhError(proc.stderr.strip() or f"gh api {path} failed")
    return json.loads(proc.stdout or "null")


def gh_text(path):
    # Job logs contain terminal escape sequences; newer gh refuses them without the flag.
    for extra in (["--allow-escape-sequences"], []):
        proc = subprocess.run(["gh", "api", *extra, path], capture_output=True)
        if proc.returncode == 0:
            return proc.stdout.decode("utf-8", "replace")
        error = proc.stderr.decode("utf-8", "replace")
        if extra and "unknown flag" in error:
            continue
        raise GhError(error.strip())
    return ""


def detect_repo():
    proc = subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
                          capture_output=True, text=True)
    if proc.returncode != 0 or not proc.stdout.strip():
        sys.exit("Cannot detect the repository; pass --repo OWNER/REPO.")
    return proc.stdout.strip()


def ts(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def span(start, end):
    return (end - start).total_seconds() if start and end and end >= start else None


def pct(values, q):
    data = sorted(v for v in values if v is not None)
    if not data:
        return None
    pos = (len(data) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(data) - 1)
    return data[lo] + (data[hi] - data[lo]) * (pos - lo)


def dur(seconds):
    if seconds is None:
        return "—"
    seconds = int(round(seconds))
    return f"{seconds}s" if seconds < 60 else f"{seconds // 60}m{seconds % 60:02d}s"


def size(num):
    return f"{num / GIB:.2f} GiB" if num >= GIB / 10 else f"{num / 1024 ** 2:.0f} MiB"


def base_name(name):
    return re.sub(r"\s*\([^()]*\)$", "", name or "")


# ---------- runs ----------

def fetch_runs(repo, args):
    params = {"per_page": 100, "status": "completed", "exclude_pull_requests": "true"}
    if args.event:
        params["event"] = args.event
    if args.branch:
        params["branch"] = args.branch
    if args.since and args.until:
        params["created"] = f"{args.since}..{args.until}"
    elif args.since:
        params["created"] = f">={args.since}"
    elif args.until:
        params["created"] = f"<={args.until}"
    keep = KEEP_CONCLUSIONS | ({"cancelled"} if args.include_cancelled else set())
    bases = [f"repos/{repo}/actions/workflows/{w}/runs" for w in args.workflow] or [f"repos/{repo}/actions/runs"]
    runs = []
    for base in bases:
        collected, page = [], 1
        while len(collected) < args.limit:
            batch = gh(base, {**params, "page": page}).get("workflow_runs") or []
            collected += [r for r in batch if r.get("conclusion") in keep]
            if len(batch) < 100:
                break
            page += 1
        runs += collected[:args.limit]
    return runs


def fetch_jobs(repo, run_id):
    jobs, page = [], 1
    while True:
        batch = gh(f"repos/{repo}/actions/runs/{run_id}/jobs",
                   {"filter": "all", "per_page": 100, "page": page}).get("jobs") or []
        jobs += batch
        if len(batch) < 100:
            return jobs
        page += 1


def classify_step(name, setup_rx, teardown_rx):
    if teardown_rx.search(name):
        return "teardown"
    if setup_rx.search(name):
        return "setup"
    return "work"


def job_record(job, setup_rx, teardown_rx):
    created, started, completed = ts(job.get("created_at")), ts(job.get("started_at")), ts(job.get("completed_at"))
    rec = {"id": job["id"], "name": job.get("name"), "base": base_name(job.get("name")),
           "conclusion": job.get("conclusion"), "labels": job.get("labels") or [],
           "created_at": job.get("created_at"), "started_at": job.get("started_at"),
           "completed_at": job.get("completed_at"), "queue": span(created, started),
           "total": span(started, completed), "setup": 0.0, "work": 0.0, "teardown": 0.0,
           "_created": created, "_completed": completed}
    for step in job.get("steps") or []:
        seconds = span(ts(step.get("started_at")), ts(step.get("completed_at")))
        if seconds is not None:
            rec[classify_step(step.get("name") or "", setup_rx, teardown_rx)] += seconds
    return rec


def critical_chain(recs):
    done = [r for r in recs if r["_created"] and r["_completed"] and r["conclusion"] != "skipped"]
    if not done:
        return []
    current = max(done, key=lambda r: r["_completed"])
    chain, seen = [current], {current["id"]}
    while True:
        preds = [r for r in done if r["id"] not in seen
                 and abs((r["_completed"] - current["_created"]).total_seconds()) <= 3]
        if not preds:
            break
        current = max(preds, key=lambda r: r["_completed"])
        chain.append(current)
        seen.add(current["id"])
    return list(reversed(chain))


def run_record(run, jobs, setup_rx, teardown_rx):
    first = [job_record(j, setup_rx, teardown_rx) for j in jobs if (j.get("run_attempt") or 1) == 1]
    later_success = {base_name(j.get("name")) for j in jobs
                     if (j.get("run_attempt") or 1) > 1 and j.get("conclusion") == "success"}
    flaky = sorted({r["base"] for r in first if r["conclusion"] in FAILED and r["base"] in later_success})
    ends = [r["_completed"] for r in first if r["_completed"]]
    created = ts(run.get("created_at"))
    chain = critical_chain(first)
    return {
        "id": run["id"], "workflow": run.get("name"), "path": run.get("path"), "event": run.get("event"),
        "head_sha": run.get("head_sha"), "head_branch": run.get("head_branch"),
        "attempts": run.get("run_attempt") or 1, "conclusion": run.get("conclusion"),
        "first_attempt_failed": any(r["conclusion"] in FAILED for r in first),
        "created_at": run.get("created_at"), "wall": span(created, max(ends)) if ends else None,
        "chain": [r["base"] for r in chain], "flaky_jobs": flaky, "jobs": first,
        "_created": created, "_end": max(ends) if ends else None,
    }


def scan_logs(repo, records, limit):
    # Spread the budget over job names, longest setup first, so each job gets a sample.
    queues = defaultdict(list)
    for record in records:
        for job in record["jobs"]:
            if job["conclusion"] in ("success", "failure"):
                queues[(record["workflow"], job["base"])].append(job)
    order = sorted(queues, key=lambda key: -(pct([j["setup"] for j in queues[key]], 0.5) or 0))
    fetched = 0
    while fetched < limit and any(queues.values()):
        for key in order:
            if fetched >= limit:
                return
            if not queues[key]:
                continue
            job = queues[key].pop(0)
            try:
                text = gh_text(f"repos/{repo}/actions/jobs/{job['id']}/logs")
            except GhError:
                continue
            fetched += 1
            job["cache"] = {kind: len(rx.findall(text)) for kind, rx in CACHE_LINES.items()}


def summarize_runs(records):
    summary = {"workflows": {}, "jobs": {}, "chains": [], "commits": {}}
    by_sha = defaultdict(list)
    for r in records:
        by_sha[r["head_sha"]].append(r)
    walls = []
    for runs in by_sha.values():
        starts = [r["_created"] for r in runs if r["_created"]]
        ends = [r["_end"] for r in runs if r["_end"]]
        if starts and ends:
            walls.append(span(min(starts), max(ends)))
    summary["commits"] = {"n": len(walls), "p50": pct(walls, 0.5), "p95": pct(walls, 0.95),
                          "max": max((w for w in walls if w is not None), default=None)}
    by_wf = defaultdict(list)
    for r in records:
        by_wf[r["workflow"]].append(r)
    for name, runs in sorted(by_wf.items()):
        last = Counter(r["chain"][-1] for r in runs if r["chain"])
        summary["workflows"][name] = {
            "runs": len(runs), "wall_p50": pct([r["wall"] for r in runs], 0.5),
            "wall_p95": pct([r["wall"] for r in runs], 0.95),
            "first_attempt_failure_rate": sum(r["first_attempt_failed"] for r in runs) / len(runs),
            "rerun_rate": sum(r["attempts"] > 1 for r in runs) / len(runs),
            "last_job": last.most_common(1)[0][0] if last else None,
        }
    jobs = defaultdict(list)
    on_chain = Counter()
    flaky = Counter()
    for r in records:
        for base in set(r["chain"]):
            on_chain[(r["workflow"], base)] += 1
        for base in r["flaky_jobs"]:
            flaky[(r["workflow"], base)] += 1
        for j in r["jobs"]:
            if j["conclusion"] != "skipped":
                jobs[(r["workflow"], j["base"])].append(j)
    for (workflow, base), items in jobs.items():
        runs_with_job = sum(1 for r in by_wf[workflow] if any(j["base"] == base for j in r["jobs"]))
        entry = {"workflow": workflow, "job": base, "n": len(items),
                 "failure_rate": sum(j["conclusion"] in FAILED for j in items) / len(items),
                 "flaky_runs": flaky[(workflow, base)],
                 "on_chain_share": on_chain[(workflow, base)] / runs_with_job if runs_with_job else 0}
        for metric in ("queue", "setup", "work", "teardown", "total"):
            entry[f"{metric}_p50"] = pct([j[metric] for j in items], 0.5)
            entry[f"{metric}_p95"] = pct([j[metric] for j in items], 0.95)
        logged = [j["cache"] for j in items if "cache" in j]
        if logged:
            entry["cache_jobs"] = {
                "logged": len(logged),
                "any_miss": sum(c["miss"] > 0 for c in logged),
                "partial_only": sum(c["miss"] == 0 and c["partial"] > 0 for c in logged),
                "exact_only": sum(c["miss"] == 0 and c["partial"] == 0 and c["exact"] > 0 for c in logged),
                "no_cache": sum(not any(c.values()) for c in logged),
            }
        summary["jobs"][f"{workflow} / {base}"] = entry
    chains = defaultdict(list)
    for r in records:
        if r["chain"]:
            chains[(r["workflow"], " → ".join(r["chain"]))].append(r["wall"])
    summary["chains"] = sorted(
        ({"workflow": wf, "chain": chain, "runs": len(w), "wall_p50": pct(w, 0.5)} for (wf, chain), w in chains.items()),
        key=lambda c: -c["runs"])[:10]
    return summary


def runs_markdown(repo, args, records, summary):
    created = sorted(r["created_at"] for r in records)
    window = f"{created[0][:10]} → {created[-1][:10]}" if created else "—"
    out = [f"# Run stats: {repo}", "",
           f"Event: {args.event or 'any'} · workflows: {', '.join(args.workflow) or 'all'} · runs: {len(records)} "
           f"({window}) · first attempts only · cancelled runs {'included' if args.include_cancelled else 'excluded'}", ""]
    c = summary["commits"]
    out += ["## Commit wall time", "",
            f"n={c['n']} · P50 {dur(c['p50'])} · P95 {dur(c['p95'])} · max {dur(c['max'])}"
            + (" · fewer than 5 commits, treat as a trend only" if c["n"] < 5 else ""), ""]
    out += ["## Workflows", "", "| Workflow | Runs | Wall P50 | Wall P95 | First-attempt failure | Rerun rate | Usual last job |",
            "| --- | --- | --- | --- | --- | --- | --- |"]
    for name, w in summary["workflows"].items():
        out.append(f"| {name} | {w['runs']} | {dur(w['wall_p50'])} | {dur(w['wall_p95'])} | "
                   f"{w['first_attempt_failure_rate']:.0%} | {w['rerun_rate']:.0%} | {w['last_job'] or '—'} |")
    out += ["", "## Critical chains (inferred from job timing)", "", "| Workflow | Chain | Runs | Wall P50 |",
            "| --- | --- | --- | --- |"]
    for ch in summary["chains"]:
        out.append(f"| {ch['workflow']} | {ch['chain']} | {ch['runs']} | {dur(ch['wall_p50'])} |")
    out += ["", "## Jobs", "",
            "| Job | n | Queue P50/P95 | Setup P50 | Work P50/P95 | Teardown P50 | Total P50/P95 | Fail | Flaky | On chain | Cache miss/partial/exact |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for key, j in sorted(summary["jobs"].items(), key=lambda kv: -(kv[1]["total_p50"] or 0)):
        cache = j.get("cache_jobs")
        cache_text = (f"{cache['any_miss']}/{cache['partial_only']}/{cache['exact_only']} of {cache['logged']}"
                      if cache else "—")
        out.append(f"| {key} | {j['n']} | {dur(j['queue_p50'])}/{dur(j['queue_p95'])} | {dur(j['setup_p50'])} | "
                   f"{dur(j['work_p50'])}/{dur(j['work_p95'])} | {dur(j['teardown_p50'])} | "
                   f"{dur(j['total_p50'])}/{dur(j['total_p95'])} | {j['failure_rate']:.0%} | {j['flaky_runs']} | "
                   f"{j['on_chain_share']:.0%} | {cache_text} |")
    out += ["", "Steps are classified by name; check setup/work splits for custom step names.",
            "Cache column: sampled job logs whose worst restore was a miss / a restore-key hit / only exact hits."]
    return "\n".join(out) + "\n"


def cmd_runs(repo, args):
    setup_rx = re.compile(SETUP.pattern + (f"|{args.setup_regex}" if args.setup_regex else ""), re.I)
    teardown_rx = re.compile(TEARDOWN.pattern + (f"|{args.teardown_regex}" if args.teardown_regex else ""), re.I)
    runs = fetch_runs(repo, args)
    records = [run_record(run, fetch_jobs(repo, run["id"]), setup_rx, teardown_rx) for run in runs]
    if args.logs:
        scan_logs(repo, records, args.logs)
    summary = summarize_runs(records)
    sys.stdout.write(runs_markdown(repo, args, records, summary))
    return {"kind": "runs", "repo": repo,
            "filters": {"event": args.event, "workflow": args.workflow, "branch": args.branch, "since": args.since,
                        "until": args.until, "limit": args.limit, "include_cancelled": args.include_cancelled},
            "runs": [{k: v for k, v in r.items() if not k.startswith("_")}
                     | {"jobs": [{k: v for k, v in j.items() if not k.startswith("_")} for j in r["jobs"]]}
                     for r in records],
            "summary": summary}


# ---------- caches ----------

def family(key):
    key = re.sub(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", "*", key)
    key = re.sub(r"[0-9a-fA-F]{7,}|\d{5,}", "*", key)
    # Adjacent variable parts, and short numbers between them such as run attempts, form one wildcard.
    return re.sub(r"\*(?:[-_.](?:\*|\d{1,3}(?=[-_.]\*)))+", "*", key)


def ref_kind(ref, default):
    if ref == f"refs/heads/{default}":
        return "default"
    if ref.startswith("refs/pull/"):
        return "pr"
    if ref.startswith("refs/heads/"):
        return "branch"
    return "tag" if ref.startswith("refs/tags/") else "other"


def cmd_caches(repo, args):
    default = gh(f"repos/{repo}")["default_branch"]
    usage = gh(f"repos/{repo}/actions/cache/usage")
    entries, page = [], 1
    while page <= 50:
        batch = gh(f"repos/{repo}/actions/caches", {"per_page": 100, "page": page,
                                                     "sort": "last_accessed_at", "direction": "desc"})
        items = batch.get("actions_caches") or []
        entries += items
        if len(items) < 100:
            break
        page += 1
    families = defaultdict(lambda: {"entries": Counter(), "bytes": Counter(), "default_keys": set(),
                                    "last_accessed": ""})
    for e in entries:
        fam = families[family(e.get("key", ""))]
        kind = ref_kind(e.get("ref", ""), default)
        fam["entries"][kind] += 1
        fam["bytes"][kind] += e.get("size_in_bytes") or 0
        if kind == "default":
            fam["default_keys"].add(e.get("key"))
        fam["last_accessed"] = max(fam["last_accessed"], e.get("last_accessed_at") or "")
    total = usage.get("active_caches_size_in_bytes") or sum(e.get("size_in_bytes") or 0 for e in entries)
    pr_bytes = sum(f["bytes"]["pr"] for f in families.values())
    findings = []
    evicting = total >= 8 * GIB
    for name, fam in families.items():
        if fam["entries"]["pr"] and not fam["entries"]["default"]:
            cause = ("Seed it from the default branch, or check whether its default-branch entries were evicted."
                     if evicting else "Seed it from the default branch.")
            findings.append({"id": "no-default-seed", "severity": "high", "family": name,
                             "message": f"`{name}` exists only in PR or branch scopes ({fam['entries']['pr']} PR "
                                        f"entries); new PRs cannot restore it. {cause}"})
        if len(fam["default_keys"]) >= 5:
            findings.append({"id": "key-churn", "severity": "low", "family": name,
                             "message": f"`{name}` has {len(fam['default_keys'])} keys on {default}. Expected for "
                                        "incremental caches with restore-keys; for dependency caches the key "
                                        "probably contains a per-commit value."})
    if evicting:
        findings.append({"id": "near-limit", "severity": "medium", "family": None,
                         "message": f"Active caches use {size(total)} of the 10 GB default; eviction will start "
                                    "removing default-branch entries."})
    if total > GIB and pr_bytes / total > 0.5:
        findings.append({"id": "pr-share", "severity": "medium", "family": None,
                         "message": f"PR-scoped caches hold {pr_bytes / total:.0%} of storage; save caches from the "
                                    "default branch only and restore in PRs."})
    rows = sorted(families.items(), key=lambda kv: -sum(kv[1]["bytes"].values()))
    out = [f"# Cache stats: {repo}", "",
           f"Default branch: `{default}` · entries: {len(entries)} · active size: {size(total)} of 10 GB default "
           f"· PR-scoped: {size(pr_bytes)}", "",
           "| Key family | Default | PR | Other | Size | Default keys | Last access |",
           "| --- | --- | --- | --- | --- | --- | --- |"]
    for name, fam in rows[:40]:
        other = fam["entries"]["branch"] + fam["entries"]["tag"] + fam["entries"]["other"]
        out.append(f"| `{name}` | {fam['entries']['default']} | {fam['entries']['pr']} | {other} | "
                   f"{size(sum(fam['bytes'].values()))} | {len(fam['default_keys'])} | {fam['last_accessed'][:16]} |")
    if len(rows) > 40:
        out.append(f"| … {len(rows) - 40} smaller families | | | | | | |")
    out += ["", "## Findings", ""]
    order = {"high": 0, "medium": 1, "low": 2}
    shown = Counter()
    for f in sorted(findings, key=lambda f: order[f["severity"]]):
        shown[f["id"]] += 1
        if shown[f["id"]] <= 10:
            out.append(f"- **{f['severity']}** `{f['id']}` — {f['message']}")
    out += [f"- … {n - 10} more `{fid}` findings (see --json)." for fid, n in shown.items() if n > 10]
    if not findings:
        out.append("None.")
    sys.stdout.write("\n".join(out) + "\n")
    return {"kind": "caches", "repo": repo, "default_branch": default, "active_bytes": total, "pr_bytes": pr_bytes,
            "families": {name: {"entries": dict(f["entries"]), "bytes": dict(f["bytes"]),
                                "default_keys": len(f["default_keys"]), "last_accessed": f["last_accessed"]}
                         for name, f in rows},
            "findings": findings}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    runs = sub.add_parser("runs", help="job timing statistics")
    runs.add_argument("--workflow", action="append", default=[], help="workflow file name or id (repeatable)")
    runs.add_argument("--event", default="pull_request", help="trigger event; empty string for all (default: pull_request)")
    runs.add_argument("--branch", help="head branch filter")
    runs.add_argument("--since", help="created on or after YYYY-MM-DD")
    runs.add_argument("--until", help="created on or before YYYY-MM-DD")
    runs.add_argument("--limit", type=int, default=30, help="runs per workflow, or in total without --workflow")
    runs.add_argument("--include-cancelled", action="store_true", help="keep cancelled runs")
    runs.add_argument("--logs", type=int, default=0, help="download up to N job logs to count cache restores")
    runs.add_argument("--setup-regex", help="extra step-name regex counted as setup")
    runs.add_argument("--teardown-regex", help="extra step-name regex counted as teardown")
    caches = sub.add_parser("caches", help="cache entries by key family and ref")
    for p in (runs, caches):
        p.add_argument("--repo", help="OWNER/REPO (default: the current gh repository)")
        p.add_argument("--json", help="write raw data and summary as JSON")
    args = parser.parse_args(argv)
    repo = args.repo or detect_repo()
    try:
        data = cmd_runs(repo, args) if args.command == "runs" else cmd_caches(repo, args)
    except GhError as exc:
        sys.exit(f"gh api failed: {exc}")
    data["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, default=str)
            fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
