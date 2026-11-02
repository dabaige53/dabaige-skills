#!/usr/bin/env python3
"""Find archived Codex tasks leaked into active hydration or sidebar membership."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import select
import sqlite3
import subprocess
import sys
import time


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def db_archived_state(path: Path) -> tuple[set[str], set[str]]:
    uri = path.resolve().as_uri() + "?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as db:
            check = db.execute("PRAGMA quick_check").fetchone()
            if check != ("ok",):
                fail(f"SQLite quick_check failed: {check!r}")
            columns = {row[1] for row in db.execute("PRAGMA table_info(threads)")}
            if not {"id", "archived"}.issubset(columns):
                fail("threads table lacks id/archived columns")
            archived = {row[0] for row in db.execute("SELECT id FROM threads WHERE archived = 1")}
            delegation = {
                row[0]
                for row in db.execute(
                    """SELECT id FROM threads
                    WHERE archived = 1
                      AND thread_source IN ('user', 'agent_created_thread')
                      AND (title LIKE '<codex_delegation>%'
                           OR first_user_message LIKE '<codex_delegation>%'
                           OR preview LIKE '<codex_delegation>%')"""
                )
            }
            return archived, delegation
    except sqlite3.Error as exc:
        fail(f"Cannot inspect {path}: {exc}")


def sidebar_sources(path: Path) -> dict[str, set[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"Cannot read {path}: {exc}")
    membership: set[str] = set()

    def add(values: object, label: str) -> None:
        if not isinstance(values, list):
            fail(f"Expected {label} to be a list")
        membership.update(value for value in values if isinstance(value, str))

    add(data.get("pinned-thread-ids", []), "pinned-thread-ids")
    add(data.get("projectless-thread-ids", []), "projectless-thread-ids")
    orders = data.get("sidebar-project-thread-orders", {})
    if not isinstance(orders, dict):
        fail("Expected sidebar-project-thread-orders to be an object")
    for project_id, entry in orders.items():
        if not isinstance(entry, dict):
            fail(f"Expected sidebar order for {project_id} to be an object")
        add(entry.get("threadIds", []), f"sidebar order {project_id}")
    atoms = data.get("electron-persisted-atom-state", {})
    if not isinstance(atoms, dict):
        fail("Expected electron-persisted-atom-state to be an object")
    add(atoms.get("app-server-pinned-thread-order-v1", []), "app-server pinned order")
    visibility = data.get("electron-remote-hosted-pip-task-visibility-state", {})
    if not isinstance(visibility, dict):
        fail("Expected electron-remote-hosted-pip-task-visibility-state to be an object")
    remote_shown = {thread_id for thread_id, value in visibility.items() if value == "shown"}
    migrated = data.get("app-server-migrated-pinned-thread-ids-by-host", {})
    if not isinstance(migrated, dict):
        fail("Expected app-server-migrated-pinned-thread-ids-by-host to be an object")
    migrated_pinned: set[str] = set()
    for host, values in migrated.items():
        if not isinstance(values, list):
            fail(f"Expected migrated pinned IDs for {host} to be a list")
        migrated_pinned.update(value for value in values if isinstance(value, str))
    return {"membership": membership, "remote_shown": remote_shown, "migrated_pinned": migrated_pinned}


def session_index_ids(path: Path) -> tuple[set[str], int, int]:
    ids: list[str] = []
    malformed = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        fail(f"Cannot read {path}: {exc}")
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(value, dict) and isinstance(value.get("id"), str):
            ids.append(value["id"])
    return set(ids), malformed, len(ids) - len(set(ids))


class AppServer:
    def __init__(self, codex_home: Path) -> None:
        env = os.environ.copy()
        env["CODEX_HOME"] = str(codex_home)
        self.proc = subprocess.Popen(
            ["codex", "app-server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            text=True,
            bufsize=1,
            env=env,
        )
        self.next_id = 1
        self.request("initialize", {"clientInfo": {"name": "thread-doctor-audit", "version": "1.0.0"}})

    def request(self, method: str, params: dict) -> dict:
        request_id = self.next_id
        self.next_id += 1
        assert self.proc.stdin is not None and self.proc.stdout is not None
        self.proc.stdin.write(json.dumps({"id": request_id, "method": method, "params": params}, separators=(",", ":")) + "\n")
        self.proc.stdin.flush()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            ready, _, _ = select.select([self.proc.stdout], [], [], 0.5)
            if not ready:
                continue
            line = self.proc.stdout.readline()
            if not line:
                break
            message = json.loads(line)
            if message.get("id") == request_id:
                if "error" in message:
                    fail(f"{method} failed: {message['error']}")
                return message["result"]
        fail(f"Timed out waiting for {method}")

    def list_ids(self, *, archived: bool, state_db_only: bool) -> set[str]:
        result: set[str] = set()
        cursor = None
        while True:
            response = self.request("thread/list", {"archived": archived, "cursor": cursor, "limit": 500, "sortKey": "updated_at", "sortDirection": "desc", "useStateDbOnly": state_db_only})
            result.update(item["id"] for item in response["data"])
            cursor = response.get("nextCursor")
            if cursor is None:
                return result

    def close(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def main() -> None:
    default_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, default=default_home)
    parser.add_argument("--thread-id", action="append", default=[], help="exact task ID observed as a sidebar ghost; repeatable")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--counts-only", action="store_true")
    args = parser.parse_args()
    codex_home = args.codex_home.expanduser().resolve()
    archived, delegation = db_archived_state(codex_home / "state_5.sqlite")
    explicit = set(args.thread_id)
    sidebar = sidebar_sources(codex_home / ".codex-global-state.json")
    legacy_index, index_malformed, index_duplicates = session_index_ids(codex_home / "session_index.jsonl")
    server = AppServer(codex_home)
    try:
        active_hydrated = server.list_ids(archived=False, state_db_only=False)
        active_state = server.list_ids(archived=False, state_db_only=True)
        archived_state = server.list_ids(archived=True, state_db_only=True)
    finally:
        server.close()
    report = {
        "db_archived": len(archived),
        "active_hydrated": len(active_hydrated),
        "active_state_db": len(active_state),
        "archived_state_db": len(archived_state),
        "hydration_conflicts": sorted(active_hydrated & archived),
        "state_db_conflicts": sorted(active_state & archived),
        "sidebar_conflicts": sorted(archived & sidebar["membership"]),
        "remote_shown_conflicts": sorted(archived & sidebar["remote_shown"]),
        "migrated_pinned_conflicts": sorted(archived & sidebar["migrated_pinned"]),
        "legacy_index_archived": sorted(archived & legacy_index),
        "archived_delegation_risks": sorted(delegation),
        "legacy_index_malformed": index_malformed,
        "legacy_index_duplicates": index_duplicates,
        "explicit_archived": sorted(explicit & archived),
        "explicit_active": sorted(explicit - archived),
        "state_active_missing_after_hydration": sorted(active_state - active_hydrated),
        "hydrated_active_missing_from_state": sorted(active_hydrated - active_state),
    }
    report["confirmed_candidates"] = sorted(set().union(report["hydration_conflicts"], report["state_db_conflicts"], report["sidebar_conflicts"], report["remote_shown_conflicts"], report["migrated_pinned_conflicts"], report["explicit_archived"]))
    report["legacy_index_risk_candidates"] = report["legacy_index_archived"]
    report["candidates"] = sorted(set(report["confirmed_candidates"]) | set(report["legacy_index_risk_candidates"]) | set(report["archived_delegation_risks"]))
    if args.counts_only:
        for key in (
            "db_archived", "active_hydrated", "active_state_db", "archived_state_db",
            "hydration_conflicts", "state_db_conflicts", "sidebar_conflicts",
            "remote_shown_conflicts", "migrated_pinned_conflicts",
            "legacy_index_archived", "confirmed_candidates", "legacy_index_risk_candidates",
            "archived_delegation_risks", "candidates", "legacy_index_malformed", "legacy_index_duplicates",
        ):
            value = report[key]
            print(f"{key}: {len(value) if isinstance(value, list) else value}")
        return
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    for key in ("db_archived", "active_hydrated", "active_state_db", "archived_state_db"):
        print(f"{key}: {report[key]}")
    print(f"candidates: {len(report['candidates'])}")
    for thread_id in report["candidates"]:
        print(thread_id)
    print(f"state_active_missing_after_hydration: {len(report['state_active_missing_after_hydration'])}")
    for thread_id in report["state_active_missing_after_hydration"]:
        print(thread_id)
    print(f"hydrated_active_missing_from_state: {len(report['hydrated_active_missing_from_state'])}")
    for thread_id in report["hydrated_active_missing_from_state"]:
        print(thread_id)


if __name__ == "__main__":
    main()
