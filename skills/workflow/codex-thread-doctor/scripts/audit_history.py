#!/usr/bin/env python3
"""Audit Codex task history in bulk without starting Codex or changing live state."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any


STATE_COLUMNS = {"id", "rollout_path", "created_at", "updated_at", "source", "title", "archived", "history_mode"}
TURN_COLUMNS = {"thread_id", "turn_id", "rollout_ordinal", "status", "rollout_byte_offset", "rollout_end_byte_offset"}
ITEM_COLUMNS = {"thread_id", "turn_id", "item_id"}
PROJECTION_COLUMNS = {"thread_id", "next_rollout_byte_offset", "next_rollout_ordinal"}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def ro_connect(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        fail(f"database does not exist: {path}")
    try:
        db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
            fail(f"SQLite quick_check failed: {path}")
        return db
    except sqlite3.Error as exc:
        fail(f"cannot inspect {path}: {exc}")


def require_schema(db: sqlite3.Connection, tables: dict[str, set[str]], path: Path) -> None:
    known = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table, required in tables.items():
        if table not in known:
            fail(f"unsupported schema in {path}: missing table {table}")
        columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        missing = required - columns
        if missing:
            fail(f"unsupported schema in {path}: {table} lacks {','.join(sorted(missing))}")


def is_subagent_source(source: str) -> bool:
    try:
        value = json.loads(source)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(value, dict) and "subagent" in value


def load_snapshot(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read API snapshot {path}: {exc}")
    if not isinstance(value, list):
        fail("API snapshot must be a JSON list")
    result: dict[str, dict[str, Any]] = {}
    for entry in value:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            fail("each API snapshot entry must contain a string id")
        if entry["id"] in result:
            fail(f"duplicate API snapshot id: {entry['id']}")
        if not isinstance(entry.get("turns", []), list) or not isinstance(entry.get("page", {}), dict):
            fail(f"invalid API snapshot entry: {entry['id']}")
        result[entry["id"]] = entry
    return result


def has_text_message(payload: object) -> bool:
    if not isinstance(payload, dict) or payload.get("type") != "message":
        return False
    if payload.get("role") not in {"user", "assistant"}:
        return False
    content = payload.get("content")
    if not isinstance(content, list):
        return False
    return any(isinstance(part, dict) and isinstance(part.get("text"), str) and part["text"].strip() for part in content)


def parse_raw(path: Path) -> dict[str, Any]:
    textual_turns: set[str] = set()
    task_started = Counter()
    malformed = 0
    active_turn: str | None = None
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    malformed += 1
                    continue
                payload = event.get("payload") if isinstance(event, dict) else None
                if not isinstance(payload, dict):
                    continue
                if event.get("type") == "event_msg" and payload.get("type") == "task_started" and isinstance(payload.get("turn_id"), str):
                    active_turn = payload["turn_id"]
                    task_started[active_turn] += 1
                elif event.get("type") == "response_item" and active_turn and has_text_message(payload):
                    textual_turns.add(active_turn)
    except OSError as exc:
        return {"read_error": str(exc), "textual_turn_ids": [], "task_started_counts": {}, "malformed_lines": malformed}
    return {
        "read_error": None,
        "textual_turn_ids": sorted(textual_turns),
        "task_started_counts": dict(sorted(task_started.items())),
        "malformed_lines": malformed,
    }


def api_complete(entry: dict[str, Any]) -> bool:
    page = entry.get("page", {})
    return entry.get("error") is None and page.get("hasMore") is False and not page.get("nextCursor")


def main() -> None:
    default_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thread-id", action="append", default=[], help="exact task ID; repeatable")
    parser.add_argument("--include-archived", action="store_true", help="allow archived tasks in the selected scope")
    parser.add_argument("--include-subagents", action="store_true", help="allow JSON subagent tasks in the selected scope")
    parser.add_argument("--codex-home", type=Path, default=default_home)
    parser.add_argument("--api-snapshot", type=Path)
    parser.add_argument("--output", type=Path, help="write JSON report here instead of stdout")
    args = parser.parse_args()

    home = args.codex_home.expanduser().resolve()
    state_path = home / "state_5.sqlite"
    history_path = home / "thread_history_1.sqlite"
    snapshot = load_snapshot(args.api_snapshot)
    explicit = set(args.thread_id)

    state = ro_connect(state_path)
    history = ro_connect(history_path)
    try:
        require_schema(state, {"threads": STATE_COLUMNS}, state_path)
        require_schema(history, {
            "thread_turns": TURN_COLUMNS,
            "thread_items": ITEM_COLUMNS,
            "thread_history_projection_state": PROJECTION_COLUMNS,
        }, history_path)
        rows = state.execute(
            "SELECT id,rollout_path,created_at,updated_at,source,title,archived,history_mode FROM threads"
        ).fetchall()
        metadata = {row[0]: row for row in rows}
        missing_explicit = sorted(explicit - metadata.keys())
        requested_ids = (explicit & metadata.keys()) if explicit else set(metadata)
        archived_excluded = {row[0] for row in rows if row[0] in requested_ids and row[6] != 0 and not args.include_archived}
        subagents_excluded = {row[0] for row in rows if row[0] in requested_ids and is_subagent_source(row[4]) and not args.include_subagents}
        selected_ids = requested_ids - archived_excluded - subagents_excluded

        projection = {
            row[0]: {"next_rollout_byte_offset": row[1], "next_rollout_ordinal": row[2]}
            for row in history.execute("SELECT thread_id,next_rollout_byte_offset,next_rollout_ordinal FROM thread_history_projection_state")
        }
        db_turns: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        for row in history.execute("SELECT thread_id,turn_id,status,rollout_ordinal,rollout_byte_offset,rollout_end_byte_offset FROM thread_turns"):
            db_turns[row[0]][row[1]] = {"status": row[2], "rollout_ordinal": row[3], "rollout_byte_offset": row[4], "rollout_end_byte_offset": row[5]}
        item_counts: dict[str, Counter[str]] = defaultdict(Counter)
        for thread_id, turn_id, count in history.execute("SELECT thread_id,turn_id,COUNT(*) FROM thread_items GROUP BY thread_id,turn_id"):
            item_counts[thread_id][turn_id] = count
    finally:
        state.close()
        history.close()

    classifications: dict[str, list[dict[str, Any]]] = {
        "missing_source_file_path": [],
        "projection_mismatch_risk": [],
        "api_read_error": [],
        "raw_text_turn_not_returned": [],
        "api_empty_turn_db_items_needs_full_items_confirmation": [],
    }
    details: list[dict[str, Any]] = []
    for thread_id in sorted(selected_ids):
        row = metadata[thread_id]
        rollout = Path(row[1]).expanduser()
        exists = rollout.is_file()
        size = rollout.stat().st_size if exists else None
        proj = projection.get(thread_id)
        paginated = row[7] == "paginated"
        offset_risk = paginated and exists and (proj is None or proj["next_rollout_byte_offset"] != size)
        if not exists:
            classifications["missing_source_file_path"].append({"id": thread_id, "path": str(rollout)})
        if offset_risk:
            classifications["projection_mismatch_risk"].append({
                "id": thread_id, "path": str(rollout), "file_size": size,
                "next_rollout_byte_offset": proj["next_rollout_byte_offset"] if proj else None,
                "reason": "missing projection state" if proj is None else "projection offset differs from file size",
            })
        api = snapshot.get(thread_id)
        if api is not None and api.get("error") is not None:
            classifications["api_read_error"].append({"id": thread_id, "error": api["error"]})
        parse_needed = exists and (thread_id in explicit or api is not None or offset_risk)
        raw = parse_raw(rollout) if parse_needed else None
        if api is not None:
            api_turns = {turn.get("id"): turn for turn in api.get("turns", []) if isinstance(turn, dict) and isinstance(turn.get("id"), str)}
            if api_complete(api) and raw and raw["read_error"] is None:
                missing = sorted(set(raw["textual_turn_ids"]) - api_turns.keys())
                if missing:
                    classifications["raw_text_turn_not_returned"].append({"id": thread_id, "turn_ids": missing})
            for turn_id, turn in api_turns.items():
                if turn.get("items") == 0 and item_counts[thread_id][turn_id] > 0:
                    classifications["api_empty_turn_db_items_needs_full_items_confirmation"].append({
                        "id": thread_id, "turn_id": turn_id, "db_items": item_counts[thread_id][turn_id]
                    })
        details.append({
            "id": thread_id, "title": row[5], "archived": bool(row[6]), "source": row[4], "history_mode": row[7],
            "created_at": row[2], "updated_at": row[3], "rollout_path": str(rollout),
            "rollout_exists": exists, "rollout_size": size, "projection": proj,
            "db_turns": len(db_turns[thread_id]), "db_items": sum(item_counts[thread_id].values()),
            "api_covered": api is not None, "api_complete": api_complete(api) if api else False,
            "raw": raw,
        })

    api_out_of_scope = sorted(set(snapshot) - selected_ids)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "codex_home": str(home), "state_db": str(state_path), "history_db": str(history_path),
            "default": "unarchived threads whose source is not JSON with a subagent key",
            "selected_count": len(selected_ids), "explicit_thread_ids": sorted(explicit),
            "include_archived": args.include_archived, "include_subagents": args.include_subagents,
        },
        "coverage": {
            "metadata_threads": len(metadata), "selected_threads": len(selected_ids),
            "rollout_files_parsed": sum(item["raw"] is not None for item in details),
            "api_snapshot_threads": len(snapshot), "selected_threads_with_api": sum(item["api_covered"] for item in details),
            "selected_threads_without_api": sorted(item["id"] for item in details if not item["api_covered"]),
            "api_snapshot_ids_outside_scope": api_out_of_scope,
        },
        "explicit_exclusions": {
            "archived_without_include_flag": sorted(archived_excluded),
            "json_subagents_without_include_flag": sorted(subagents_excluded),
            "explicit_ids_not_in_metadata": missing_explicit,
        },
        "classification_notes": {
            "missing_source_file_path": "The metadata path is not a readable file; this alone does not prove data loss.",
            "projection_mismatch_risk": "A paginated task lacks projection state or its projection offset differs from the current file size; this is risk evidence, not proof of missing history.",
            "api_read_error": "The supplied snapshot recorded an API read error.",
            "raw_text_turn_not_returned": "A complete, error-free supplied snapshot omitted a raw turn containing user or assistant text; fork inheritance, projection state, and API hydration still require diagnosis.",
            "api_empty_turn_db_items_needs_full_items_confirmation": "The snapshot returned an empty turn while projection items exist; confirm with a fresh itemsView:full read before diagnosing loss.",
        },
        "classified_candidates": classifications,
        "threads": details,
    }
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output, encoding="utf-8")
        except OSError as exc:
            fail(f"cannot write report {args.output}: {exc}")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
