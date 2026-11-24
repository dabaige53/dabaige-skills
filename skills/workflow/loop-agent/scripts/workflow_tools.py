#!/usr/bin/env python3
"""Read-only workflow checks and bounded evidence extraction. No task execution."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import sys
import tempfile

MAX_CONFIG_BYTES = 1024 * 1024
MAX_EVENT_BYTES = 1024 * 1024
MAX_FILES = 32
STATUSES = {"pending", "running", "succeeded", "failed", "blocked", "skipped", "cancelled", "timed_out"}
TERMINAL = STATUSES - {"pending", "running"}
SECRET_KEY = r"(?:password|passwd|secret|client_secret|api[_-]?key|access[_-]?token|refresh[_-]?token|session[_-]?token|token|authorization|credential)"


class ToolError(Exception):
    pass


def issue(code, field, message):
    return {"code": code, "field": field, "message": message}


def regular_file(path):
    try:
        return stat.S_ISREG(path.stat().st_mode)
    except OSError:
        return False


def path_from(value, base):
    if not isinstance(value, str) or not value.strip():
        raise ToolError("Expected a non-empty filesystem path.")
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value) and not re.match(r"^[A-Za-z]:[/\\]", value):
        raise ToolError("URI storage needs a project adapter; provide a local exported file path.")
    if "\x00" in value:
        raise ToolError("Path contains a null byte.")
    path = Path(value).expanduser()
    return (path if path.is_absolute() else base / path).resolve()


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ToolError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def load_config(filename, root_override=None):
    config_path = path_from(filename, Path.cwd())
    if not regular_file(config_path):
        raise ToolError("Configuration must be an existing regular file.")
    if config_path.stat().st_size > MAX_CONFIG_BYTES:
        raise ToolError("Configuration exceeds 1 MiB; use a smaller workflow definition.")
    content = config_path.read_text(encoding="utf-8")
    if config_path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:
            raise ToolError("YAML requires an already-installed PyYAML; use JSON or the project's parser.") from exc
        try:
            class UniqueLoader(yaml.SafeLoader):
                pass
            def unique_mapping(loader, node):
                loader.flatten_mapping(node)
                return no_duplicates(loader.construct_pairs(node))
            UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)
            config = yaml.load(content, Loader=UniqueLoader)
        except yaml.YAMLError as exc:
            raise ToolError("Invalid YAML configuration.") from exc
    else:
        try:
            config = json.loads(content, object_pairs_hook=no_duplicates)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise ToolError("Invalid JSON configuration.") from exc
    if not isinstance(config, dict):
        raise ToolError("Configuration root must be an object.")
    paths = config.get("paths", {})
    if not isinstance(paths, dict):
        raise ToolError("paths must be an object.")
    root = path_from(root_override, Path.cwd()) if root_override is not None else path_from(paths.get("project_root", "."), config_path.parent)
    return config, config_path, root


def nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def string_list(value, nonempty=False):
    return isinstance(value, list) and (not nonempty or bool(value)) and all(nonempty_string(item) for item in value)


def positive_int(value):
    return type(value) is int and value > 0


def graph(steps):
    ids = [step["id"] for step in steps]
    predecessors = {step["id"]: list(step["needs"]) for step in steps}
    successors = {name: [] for name in ids}
    remaining = {}
    for name in ids:
        remaining[name] = len(predecessors[name])
        for dep in predecessors[name]:
            successors[dep].append(name)
    stages = []
    ready = [name for name in ids if remaining[name] == 0]
    visited = []
    while ready:
        stages.append(ready)
        visited.extend(ready)
        next_ready = set()
        for name in ready:
            for child in successors[name]:
                remaining[child] -= 1
                if remaining[child] == 0:
                    next_ready.add(child)
        ready = [name for name in ids if name in next_ready]
    return {"stages": stages, "predecessors": predecessors, "successors": successors, "cycle_or_blocked": [name for name in ids if name not in visited]}


def lint_config(config, root):
    errors, warnings = [], []
    def error(code, field, message):
        errors.append(issue(code, field, message))
    def warning(code, field, message):
        warnings.append(issue(code, field, message))
    if type(config.get("version")) is not int or config.get("version") != 1:
        error("VERSION", "version", "Set version to integer 1.")
    for field in ("id", "goal"):
        if not nonempty_string(config.get(field)):
            error("REQUIRED", field, "Provide a non-empty string.")
    if not string_list(config.get("completion"), nonempty=True):
        error("COMPLETION", "completion", "Provide at least one verifiable completion criterion.")
    paths = config.get("paths", {})
    logs = paths.get("logs", [])
    if not string_list(logs):
        error("TYPE", "paths.logs", "Expected an array of file paths.")
    elif len(logs) > MAX_FILES:
        error("FILE_LIMIT", "paths.logs", "At most 32 log files per invocation.")
    path_items = [("paths." + key, value) for key, value in paths.items() if key in {"state", "artifacts", "scripts"} and value is not None]
    if string_list(logs):
        path_items += [(f"paths.logs[{i}]", value) for i, value in enumerate(logs)]
    for field, value in path_items:
        try:
            path_from(value, root)
        except (ToolError, OSError, ValueError) as exc:
            error("PATH", field, str(exc))
    runtime = config.get("runtime", {})
    if not isinstance(runtime, dict):
        error("TYPE", "runtime", "Expected an object.")
        runtime = {}
    for field in ("required_commands", "required_env"):
        if not string_list(runtime.get(field, [])):
            error("TYPE", "runtime." + field, "Expected an array of names.")
    if string_list(runtime.get("required_env", [])):
        for name in runtime.get("required_env", []):
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                error("ENV_NAME", "runtime.required_env", "Environment entries must be variable names, never values.")
    limits = config.get("limits", {})
    if not isinstance(limits, dict):
        error("TYPE", "limits", "Expected an object.")
        limits = {}
    for field in ("workflow_timeout_seconds", "max_attempts", "max_consecutive_failures", "max_parallel"):
        if not positive_int(limits.get(field)):
            error("BOUND", "limits." + field, "Provide an explicit positive integer bound.")
    if limits.get("token_budget") is not None and not positive_int(limits["token_budget"]):
        error("BOUND", "limits.token_budget", "Use a positive integer or null when unavailable.")
    controls = config.get("controls", {})
    if not isinstance(controls, dict):
        error("TYPE", "controls", "Expected an object of enforcement descriptions.")
        controls = {}
    for field in ("timeout", "retry", "overlap", "idempotency", "circuit_breaker"):
        if not nonempty_string(controls.get(field)):
            warning("CONTROL_UNKNOWN", "controls." + field, "Record the real enforcing component or mark unsupported.")
    warning("DECLARATION_ONLY", "controls", "Configuration declarations do not prove timeout, retry, lock, or budget enforcement.")
    relations = config.get("related_workflows", [])
    if not isinstance(relations, list):
        error("TYPE", "related_workflows", "Expected an array.")
    else:
        for index, relation in enumerate(relations):
            field = f"related_workflows[{index}]"
            if not isinstance(relation, dict) or not nonempty_string(relation.get("id")) or not nonempty_string(relation.get("relation")) or relation.get("relation") not in {"upstream", "downstream", "related"} or not nonempty_string(relation.get("contract")):
                error("RELATION", field, "Provide id, relation (upstream/downstream/related), and a concrete contract.")
    steps = config.get("steps")
    if not isinstance(steps, list) or not steps:
        error("STEPS", "steps", "Provide a non-empty array of steps.")
        steps = []
    if len(steps) > 1000:
        error("STEP_LIMIT", "steps", "Split workflows larger than 1000 steps.")
        steps = steps[:1000]
    ids = []
    graph_ok = True
    for index, step in enumerate(steps):
        field = f"steps[{index}]"
        if not isinstance(step, dict):
            error("TYPE", field, "Expected an object.")
            graph_ok = False
            continue
        name = step.get("id")
        if not nonempty_string(name):
            error("STEP_ID", field + ".id", "Provide a non-empty unique step ID.")
            graph_ok = False
        elif name in ids:
            error("DUPLICATE", field + ".id", "Step IDs must be unique.")
            graph_ok = False
        else:
            ids.append(name)
        kind = step.get("kind")
        if not nonempty_string(kind) or kind not in {"script", "tool", "ai", "human"}:
            error("KIND", field + ".kind", "Choose script, tool, ai, or human.")
        if not nonempty_string(step.get("title")):
            error("REQUIRED", field + ".title", "Provide a short step title.")
        for key in ("needs", "inputs", "outputs", "success_criteria"):
            if not string_list(step.get(key), nonempty=(key == "success_criteria")):
                error("TYPE", field + "." + key, "Expected an array of strings" + (" with at least one criterion." if key == "success_criteria" else "."))
                if key == "needs":
                    graph_ok = False
        if string_list(step.get("needs")) and len(set(step["needs"])) != len(step["needs"]):
            error("DUPLICATE_DEPENDENCY", field + ".needs", "Dependency IDs must be unique.")
            graph_ok = False
        for key in ("timeout_seconds", "max_attempts"):
            if not positive_int(step.get(key)):
                error("BOUND", field + "." + key, "Provide an explicit positive integer bound.")
        if positive_int(step.get("max_attempts")) and positive_int(limits.get("max_attempts")) and step["max_attempts"] > limits["max_attempts"]:
            error("ATTEMPT_LIMIT", field + ".max_attempts", "Step attempts exceed the workflow limit.")
        if positive_int(step.get("timeout_seconds")) and positive_int(limits.get("workflow_timeout_seconds")) and step["timeout_seconds"] > limits["workflow_timeout_seconds"]:
            error("TIME_LIMIT", field + ".timeout_seconds", "Step timeout exceeds the workflow timeout.")
        if type(step.get("side_effects")) is not bool:
            error("TYPE", field + ".side_effects", "Specify true or false explicitly.")
        if step.get("side_effects") is True and positive_int(step.get("max_attempts")) and step["max_attempts"] > 1 and not nonempty_string(step.get("idempotency_key")):
            error("UNSAFE_RETRY", field + ".idempotency_key", "Retrying a side effect needs a concrete idempotency key and enforced deduplication.")
        if "when" in step and not nonempty_string(step["when"]):
            error("TYPE", field + ".when", "Conditions are non-empty declarative strings; this tool does not evaluate them.")
        if kind == "script" and not string_list(step.get("command"), nonempty=True):
            error("COMMAND", field + ".command", "Provide an argv array; shell command strings are not accepted.")
        if kind == "tool" and not nonempty_string(step.get("tool_ref")):
            error("TOOL_REF", field + ".tool_ref", "Identify the target executor tool or connector action.")
        if kind == "ai":
            if not nonempty_string(step.get("prompt_file")):
                error("PROMPT", field + ".prompt_file", "Provide the reusable AI prompt file.")
            if step.get("token_budget") is None:
                warning("TOKEN_UNKNOWN", field + ".token_budget", "AI token budget is unknown; do not invent measured usage.")
            elif not positive_int(step["token_budget"]):
                error("BOUND", field + ".token_budget", "Use a positive integer or null.")
        for key in ("script_file", "prompt_file"):
            if key in step:
                try:
                    reference = path_from(step[key], root)
                    if not regular_file(reference):
                        error("MISSING_FILE", field + "." + key, "Referenced file is missing or is not a regular file.")
                except (ToolError, OSError, ValueError) as exc:
                    error("PATH", field + "." + key, str(exc))
    if graph_ok:
        for index, step in enumerate(steps):
            for dep in step["needs"]:
                if dep == step["id"] or dep not in ids:
                    error("DEPENDENCY", f"steps[{index}].needs", "Dependency is self-referential or does not exist: " + dep)
                    graph_ok = False
    route = graph(steps) if graph_ok and steps else None
    if route and route["cycle_or_blocked"]:
        error("CYCLE", "steps", "Dependency cycle prevents a complete topological route.")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "planned_route": route, "enforcement_verified": False}


def preflight(config, root):
    runtime = config.get("runtime", {})
    commands = {name: shutil.which(name) for name in runtime.get("required_commands", [])}
    env = {name: bool(os.environ.get(name)) for name in runtime.get("required_env", [])}
    files = []
    for step in config.get("steps", []):
        for field in ("script_file", "prompt_file"):
            if field in step:
                path = path_from(step[field], root)
                files.append({"step_id": step["id"], "field": field, "path": str(path), "regular_file": regular_file(path), "readable": os.access(path, os.R_OK)})
    destinations = []
    for key in ("state", "artifacts", "scripts"):
        value = config.get("paths", {}).get(key)
        if value is not None:
            path = path_from(value, root)
            destinations.append({"field": "paths." + key, "path": str(path), "exists": path.exists(), "parent_exists": path.parent.is_dir(), "parent_writable_by_access_check": os.access(path.parent, os.W_OK), "write_attempted": False})
    missing = ["command:" + name for name, value in commands.items() if value is None] + ["environment:" + name for name, value in env.items() if not value]
    if not root.is_dir() or not os.access(root, os.R_OK):
        missing.append("project_root")
    missing.extend("reference:" + item["step_id"] for item in files if not item["regular_file"] or not item["readable"])
    missing.extend(item["field"] + ":parent" for item in destinations if not item["parent_exists"] or not item["parent_writable_by_access_check"])
    return {"ok": not missing, "project_root": str(root), "project_root_exists": root.is_dir(), "project_root_readable": os.access(root, os.R_OK), "system": platform.system(), "python": platform.python_version(), "required_commands": commands, "required_env_present": env, "references": files, "destinations": destinations, "missing": missing, "capabilities": {"scheduler_execution": "not_tested", "network_access": "not_tested", "authentication": "not_tested", "connector_access": "not_tested", "runtime_write": "not_tested"}, "enforcement_verified": False, "scope": "Local static requirements only; scheduler and connector readiness are unverified."}


def redact(text):
    replacements = 0
    def apply(pattern, replacement, flags=0):
        nonlocal text, replacements
        text, count = re.subn(pattern, replacement, text, flags=flags)
        replacements += count
    apply(r"-----BEGIN [^-\r\n]*PRIVATE KEY-----.*?(?:-----END [^-\r\n]*PRIVATE KEY-----|\Z)", "[REDACTED PRIVATE KEY]", re.S)
    # Also remove a tail fragment whose BEGIN line was outside the byte window.
    apply(r"\A.*?-----END [^-\r\n]*PRIVATE KEY-----", "[REDACTED PRIVATE KEY FRAGMENT]", re.S)
    apply(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+", r"\1 [REDACTED]")
    apply(r"(?i)(https?://)[^/\s:@]+:[^/@\s]+@", r"\1[REDACTED]@")
    apply(r"(?i)([?&](?:" + SECRET_KEY + r"|key|signature|sig)=)[^&#\s]+", r"\1[REDACTED]")
    apply(r"(?i)([\"']?" + SECRET_KEY + r"[\"']?\s*[:=]\s*)(\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;&]+)", r"\1[REDACTED]")
    apply(r"\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,})\b", "[REDACTED TOKEN]")
    return text, replacements


def read_tail(path, max_bytes):
    if not regular_file(path):
        raise ToolError("Missing file or not a regular file (directories, FIFOs and devices are refused).")
    # O_NONBLOCK prevents a file replaced with a FIFO between stat and open from blocking.
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ToolError("Not a regular file.")
        start = max(0, info.st_size - max_bytes)
        stream.seek(start)
        data = stream.read(max_bytes)
    # Drop the first fragment rather than show a possibly split credential assignment.
    if start and b"\n" in data:
        data = data.split(b"\n", 1)[1]
    elif start:
        data = b""
    return data, info, start > 0


def collect(config, root, overrides, max_bytes, max_lines):
    values = overrides if overrides is not None else config.get("paths", {}).get("logs", [])
    if not string_list(values):
        raise ToolError("Log paths must be an array of file paths.")
    if len(values) > MAX_FILES:
        raise ToolError("At most 32 log files per invocation.")
    remaining, results, errors = max_bytes, [], []
    for value in values:
        path = path_from(value, root)
        if remaining <= 0:
            results.append({"path": str(path), "skipped": "global_byte_budget", "truncated": True})
            continue
        try:
            data, info, truncated = read_tail(path, remaining)
            # Charge the full possible I/O, including dropped first-line fragments.
            charged = min(info.st_size, remaining)
            remaining -= charged
            cleaned, redactions = redact(data.decode("utf-8", errors="replace"))
            lines = cleaned.splitlines()
            line_truncated = len(lines) > max_lines
            excerpt = "\n".join(lines[-max_lines:])
            results.append({"path": str(path), "size_bytes": info.st_size, "read_budget_bytes": charged, "mtime_utc": datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(), "excerpt": excerpt, "truncated": truncated or line_truncated, "redactions": redactions})
        except (ToolError, OSError, ValueError) as exc:
            errors.append({"path": str(path), "error": str(exc)})
    return {"ok": not errors, "files": results, "errors": errors, "bytes_budget": max_bytes, "bytes_charged": max_bytes - remaining, "max_lines_per_file": max_lines, "evidence_only": True, "redaction": "best_effort; inspect before sharing", "untrusted_content": True, "no_sources_configured": not values}


def valid_timestamp(value):
    if not nonempty_string(value):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.utcoffset() is not None
    except ValueError:
        return False


def read_events(config, root, event_files):
    if len(event_files) > MAX_FILES:
        raise ToolError("At most 32 event files per invocation.")
    errors, records = [], []
    used_bytes, incomplete = 0, False
    known_steps = {step["id"] for step in config["steps"]}
    seen_events = {}
    for value in event_files:
        path = path_from(value, root)
        try:
            if not regular_file(path):
                raise ToolError("Event source must be a regular file.")
            remaining = MAX_EVENT_BYTES - used_bytes
            if remaining <= 0:
                incomplete = True
                errors.append(issue("TRUNCATED", str(path), "Global event byte budget exhausted."))
                continue
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
            with os.fdopen(descriptor, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ToolError("Event source must be a regular file.")
                raw = stream.read(remaining + 1)
            truncated = len(raw) > remaining
            used_bytes += min(len(raw), remaining)
            if truncated:
                incomplete = True
                errors.append(issue("TRUNCATED", str(path), "Event source exceeds the remaining byte budget."))
                raw = raw[:remaining]
                raw = raw.rsplit(b"\n", 1)[0] if b"\n" in raw else b""
            for line_number, raw_line in enumerate(raw.splitlines(), 1):
                if not raw_line.strip():
                    continue
                field = str(path) + ":" + str(line_number)
                try:
                    event = json.loads(raw_line, object_pairs_hook=no_duplicates)
                except (ValueError, RecursionError, ToolError):
                    errors.append(issue("INVALID_EVENT", field, "Invalid JSON event."))
                    incomplete = True
                    continue
                if not isinstance(event, dict):
                    errors.append(issue("INVALID_EVENT", field, "Event must be an object."))
                    incomplete = True
                    continue
                valid = event.get("workflow_id") == config["id"] and nonempty_string(event.get("run_id")) and nonempty_string(event.get("step_id")) and event.get("step_id") in known_steps and nonempty_string(event.get("status")) and event.get("status") in STATUSES and positive_int(event.get("attempt")) and valid_timestamp(event.get("timestamp"))
                if not valid:
                    errors.append(issue("INVALID_EVENT", field, "Require matching workflow_id, known step_id, run_id, valid status, positive attempt and timezone-aware timestamp."))
                    incomplete = True
                    continue
                bad_metric = any(event.get(key) is not None and (type(event[key]) not in (int, float) or event[key] < 0 or event[key] != event[key] or event[key] == float("inf")) for key in ("duration_seconds", "tokens", "tool_calls"))
                if bad_metric or any(event.get(key) is not None and type(event[key]) is not int for key in ("tokens", "tool_calls")):
                    errors.append(issue("INVALID_METRIC", field, "Metrics must be nonnegative finite numbers; tokens and tool_calls must be integers."))
                    incomplete = True
                    continue
                for key in ("event_id", "agent_id", "reason", "reason_code", "workflow_revision"):
                    if event.get(key) is not None and not nonempty_string(event[key]):
                        errors.append(issue("INVALID_EVENT", field, key + " must be a non-empty string or null."))
                        incomplete = True
                        valid = False
                if event.get("reason_code") is not None and (not isinstance(event["reason_code"], str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", event["reason_code"])):
                    errors.append(issue("INVALID_EVENT", field, "reason_code must be a stable uppercase machine code."))
                    incomplete = True
                    valid = False
                if not valid:
                    continue
                event_id = event.get("event_id")
                if event_id:
                    event_key = (event["workflow_id"], event["run_id"], event_id)
                    if event_key in seen_events:
                        if seen_events[event_key] != event:
                            errors.append(issue("DUPLICATE_EVENT", field, "Conflicting payloads share an event_id."))
                            incomplete = True
                        continue
                    seen_events[event_key] = event
                records.append(event)
        except (ToolError, OSError, ValueError) as exc:
            errors.append(issue("EVENT_SOURCE", str(path), str(exc)))
            incomplete = True
    return records, errors, incomplete, used_bytes


def report(config, root, event_files, selected_run, lint):
    records, errors, incomplete, used_bytes = read_events(config, root, event_files)
    known_steps = {step["id"] for step in config["steps"]}
    run_ids = list(dict.fromkeys(event["run_id"] for event in records))
    if selected_run is None and len(run_ids) > 1:
        raise ToolError("Multiple runs found; select exactly one with --run-id. Available runs: " + ", ".join(run_ids))
    run_id = selected_run if selected_run is not None else (run_ids[0] if run_ids else None)
    selected = [event for event in records if event["run_id"] == run_id]
    latest, attempts = {}, {}
    actual_route = []
    for event in selected:
        latest[event["step_id"]] = event
        attempts[(event["step_id"], event["attempt"])] = event
        item = {key: event[key] for key in ("timestamp", "step_id", "status", "attempt", "agent_id", "reason", "reason_code", "workflow_revision") if key in event and event[key] is not None}
        if "reason" in item:
            item["reason"], _ = redact(item["reason"])
        actual_route.append(item)
    metrics = {}
    terminal_attempts = [event for event in attempts.values() if event["status"] in TERMINAL]
    for key in ("duration_seconds", "tokens", "tool_calls"):
        values = [event[key] for event in terminal_attempts if event.get(key) is not None]
        metrics[key] = sum(values) if values else None
        metrics[key + "_coverage"] = {"measured_terminal_attempts": len(values), "terminal_attempts": len(terminal_attempts)}
    if not selected:
        status = "unknown"
    elif incomplete:
        status = "incomplete_evidence"
    elif any(event["status"] == "blocked" for event in latest.values()):
        status = "blocked"
    elif any(event["status"] in {"failed", "cancelled", "timed_out"} for event in latest.values()):
        status = "failed"
    elif len(latest) == len(known_steps) and all(event["status"] in {"succeeded", "skipped"} for event in latest.values()):
        status = "all_steps_reported_succeeded" if all(event["status"] == "succeeded" for event in latest.values()) else "finished_with_skips"
    elif any(event["status"] == "running" for event in latest.values()):
        status = "running_or_stale"
    else:
        status = "partial"
    return {"ok": not errors, "workflow_id": config["id"], "run_id": run_id, "available_runs": run_ids, "planned_route": lint["planned_route"], "related_workflows": config.get("related_workflows", []), "actual_route": actual_route, "ordering": "input file order and line order; not a cross-source causal proof", "execution_status": status, "missing_steps": [step["id"] for step in config["steps"] if step["id"] not in latest], "metrics": metrics, "metric_semantics": "Latest terminal-attempt snapshots; sums cover only observed attempts. Duration sum is not wall time.", "completion_verified": False, "completion_note": "Step events do not independently verify business completion criteria or external side effects.", "incomplete_evidence": incomplete, "errors": errors, "bytes_read": used_bytes}


def audit(config, root, event_files, max_runs=20, stale_seconds=None, as_of=None):
    """Bounded, observational multi-run diagnostics; never runs or repairs tasks."""
    if not 1 <= max_runs <= 100:
        raise ToolError("Use --max-runs 1..100.")
    if stale_seconds is not None and stale_seconds <= 0:
        raise ToolError("Use a positive --stale-seconds.")
    if as_of is not None and not valid_timestamp(as_of):
        raise ToolError("--as-of must be a timezone-aware timestamp.")
    def ts(value):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    now = ts(as_of) if as_of else datetime.now(timezone.utc)
    records, errors, incomplete, used = read_events(config, root, event_files)
    groups = {}
    for event in records:
        groups.setdefault(event["run_id"], []).append(event)
    # Sort by latest observed timestamp, not assumed scheduler order.
    ordered = sorted(groups, key=lambda run: max(ts(e["timestamp"]) for e in groups[run]), reverse=True)
    limits = config.get("limits", {})
    limits = limits if isinstance(limits, dict) else {}
    steps = {s["id"]: s for s in config["steps"]}
    findings, summaries, recurrence = [], [], {}
    def flag(code, run, **fields):
        findings.append({"code": code, "run_id": run, **fields})
    for run in ordered[:max_runs]:
        events = sorted(groups[run], key=lambda e: ts(e["timestamp"]))
        attempts, latest = {}, {}
        for e in events:
            attempts[(e["step_id"], e["attempt"])] = e
            latest[e["step_id"]] = e
        revisions = sorted({e["workflow_revision"] for e in events if e.get("workflow_revision")})
        missing = sorted(set(steps) - set(latest))
        terminal = [e for e in attempts.values() if e["status"] in TERMINAL]
        usage = {}
        for key in ("tokens", "tool_calls", "duration_seconds"):
            values = [e[key] for e in terminal if e.get(key) is not None]
            usage[key] = {"observed_sum": sum(values) if values else None, "measured_attempts": len(values), "observed_terminal_attempts": len(terminal)}
        span = (ts(events[-1]["timestamp"]) - ts(events[0]["timestamp"])).total_seconds()
        state = "failed_or_blocked" if any(e["status"] in {"failed", "blocked", "timed_out", "cancelled"} for e in latest.values()) else "all_steps_terminal" if not missing and all(e["status"] in TERMINAL for e in latest.values()) else "partial_or_running"
        summaries.append({"run_id": run, "state_from_events": state, "last_observed_at": events[-1]["timestamp"], "observed_span_seconds": span, "missing_steps": missing, "workflow_revisions": revisions, "usage": usage})
        if len(revisions) > 1:
            flag("MIXED_REVISIONS", run, revisions=revisions)
        bound = limits.get("token_budget")
        if positive_int(bound) and usage["tokens"]["observed_sum"] is not None and usage["tokens"]["observed_sum"] > bound:
            flag("OBSERVED_TOKEN_BUDGET_EXCEEDED", run, observed=usage["tokens"]["observed_sum"], configured=bound)
        bound = limits.get("workflow_timeout_seconds")
        if positive_int(bound) and span > bound:
            flag("OBSERVED_SPAN_EXCEEDS_CONFIGURED_TIMEOUT", run, observed=span, configured=bound)
        for step, e in latest.items():
            if e["status"] in {"failed", "blocked", "timed_out"} and e.get("reason_code"):
                recurrence.setdefault((step, e["reason_code"]), []).append(run)
            if e["status"] == "running" and stale_seconds is not None:
                age = (now - ts(e["timestamp"])).total_seconds()
                if age > stale_seconds:
                    flag("NO_RECENT_STEP_EVENT", run, step_id=step, seconds_since_event=age, threshold=stale_seconds)
            bound = steps[step].get("max_attempts")
            if positive_int(bound) and max(a for st, a in attempts if st == step) > bound:
                flag("OBSERVED_ATTEMPT_LIMIT_EXCEEDED", run, step_id=step, configured=bound)
    for (step, reason), runs in recurrence.items():
        if len(runs) > 1:
            findings.append({"code": "REPEATED_FAILURE_SIGNATURE", "step_id": step, "reason_code": reason, "observed_run_ids": runs, "count": len(runs)})
    return {"ok": not errors, "workflow_id": config["id"], "observed_runs": len(groups), "included_runs": len(summaries), "runs": summaries, "findings": findings, "incomplete_evidence": incomplete or not records or len(groups) > max_runs, "errors": errors, "bytes_read": used, "scope": "Observed events only; current config bounds may differ from historical revisions. Repeated signatures are not proven consecutive failures or root causes. Silence is not proof of a hang. Missing events/metrics remain unknown; no enforcement or business completion verified."}


def protect_output(args, config, config_path, root):
    if args.output is None:
        return
    output = path_from(args.output, Path.cwd())
    protected = [config_path]
    paths = config.get("paths", {})
    raw_paths = []
    if isinstance(paths.get("logs"), list):
        raw_paths.extend(paths["logs"])
    if paths.get("state") is not None:
        raw_paths.append(paths["state"])
    raw_paths.extend(getattr(args, "log", None) or [])
    raw_paths.extend(getattr(args, "events", None) or [])
    for step in config.get("steps", []) if isinstance(config.get("steps"), list) else []:
        if isinstance(step, dict):
            raw_paths.extend(step[key] for key in ("script_file", "prompt_file") if key in step)
    for value in raw_paths:
        try:
            protected.append(path_from(value, root))
        except (ToolError, OSError, ValueError):
            pass  # The validator reports malformed declared paths separately.
    for path in protected:
        same_file = output == path
        if not same_file and output.exists() and path.exists():
            same_file = os.path.samefile(output, path)
        if same_file:
            raise ToolError("Output would overwrite configuration or source evidence; choose a distinct output file.")


def report_structure_valid(config):
    steps = config.get("steps")
    if not nonempty_string(config.get("id")) or not isinstance(steps, list) or not steps:
        return False
    if not all(isinstance(step, dict) and nonempty_string(step.get("id")) for step in steps):
        return False
    return len({step["id"] for step in steps}) == len(steps)


def write_result(result, output):
    rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if output is None:
        sys.stdout.write(rendered)
        return
    path = path_from(output, Path.cwd())
    if not path.parent.is_dir():
        raise ToolError("Output parent does not exist; choose an existing directory.")
    descriptor, temporary = tempfile.mkstemp(prefix=".loop-agent-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(rendered)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def cli(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("lint", "preflight", "collect", "report", "audit"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--config", required=True)
        subparser.add_argument("--project-root")
        subparser.add_argument("--output", help="Explicit JSON output file; parent must already exist.")
        if command == "collect":
            subparser.add_argument("--log", action="append", help="Override paths.logs; repeat for each file.")
            subparser.add_argument("--max-bytes", type=int, default=65536, help="Global read budget, maximum 1 MiB.")
            subparser.add_argument("--max-lines", type=int, default=100, help="Maximum excerpt lines per file, maximum 1000.")
        if command in {"report", "audit"}:
            subparser.add_argument("--events", action="append", default=[], help="JSONL evidence file; repeat as needed.")
        if command == "report":
            subparser.add_argument("--run-id")
        if command == "audit":
            subparser.add_argument("--max-runs", type=int, default=20)
            subparser.add_argument("--stale-seconds", type=int)
            subparser.add_argument("--as-of", help="Timezone-aware observation timestamp; defaults to current UTC.")
    args = parser.parse_args(argv)
    try:
        config, config_path, root = load_config(args.config, args.project_root)
        lint = lint_config(config, root)
        protect_output(args, config, config_path, root)
        if args.command == "lint":
            result = lint
        elif args.command == "collect":
            if not 0 < args.max_bytes <= MAX_EVENT_BYTES or not 0 < args.max_lines <= 1000:
                raise ToolError("Use --max-bytes 1..1048576 and --max-lines 1..1000.")
            result = collect(config, root, args.log, args.max_bytes, args.max_lines)
            result["configuration_issues"] = lint["errors"]
        elif args.command == "audit" and report_structure_valid(config):
            result = audit(config, root, args.events, args.max_runs, args.stale_seconds, args.as_of)
            result["configuration_issues"] = lint["errors"]
        elif args.command == "report" and report_structure_valid(config):
            if lint["planned_route"] and lint["planned_route"]["cycle_or_blocked"]:
                lint["planned_route"] = None
            result = report(config, root, args.events, args.run_id, lint)
            result["configuration_issues"] = lint["errors"]
        elif args.command in {"report", "audit"} or not lint["ok"]:
            result = {"ok": False, "error": "Fix configuration lint errors before continuing.", "lint": lint}
        else:
            result = preflight(config, root)
        result = {"command": args.command, "config": str(config_path), "project_root": str(root), **result}
        write_result(result, args.output)
        return 0 if result["ok"] else 1
    except (ToolError, OSError, ValueError, TypeError, RecursionError) as exc:
        # Do not dump input documents, environment values or Python tracebacks.
        sys.stdout.write(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False) + "\n")
        return 2


if __name__ == "__main__":
    sys.exit(cli())
