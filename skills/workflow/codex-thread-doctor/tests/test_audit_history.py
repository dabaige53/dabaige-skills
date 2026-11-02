from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "audit_history.py"


def make_databases(home: Path, *, valid: bool = True) -> None:
    with sqlite3.connect(home / "state_5.sqlite") as db:
        if valid:
            db.execute("CREATE TABLE threads(id TEXT PRIMARY KEY, rollout_path TEXT, created_at INTEGER, updated_at INTEGER, source TEXT, title TEXT, archived INTEGER, history_mode TEXT)")
        else:
            db.execute("CREATE TABLE threads(id TEXT PRIMARY KEY)")
    with sqlite3.connect(home / "thread_history_1.sqlite") as db:
        db.execute("CREATE TABLE thread_turns(thread_id TEXT,turn_id TEXT,rollout_ordinal INTEGER,status TEXT,rollout_byte_offset INTEGER,rollout_end_byte_offset INTEGER)")
        db.execute("CREATE TABLE thread_items(thread_id TEXT,turn_id TEXT,item_id TEXT)")
        db.execute("CREATE TABLE thread_history_projection_state(thread_id TEXT,next_rollout_byte_offset INTEGER,next_rollout_ordinal INTEGER)")


def raw_events(*events: dict) -> str:
    return "".join(json.dumps(event) + "\n" for event in events)


def started(turn_id: str) -> dict:
    return {"type": "event_msg", "payload": {"type": "task_started", "turn_id": turn_id}}


def message(text: str = "hello") -> dict:
    return {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}}


class AuditHistoryTest(unittest.TestCase):
    def run_audit(self, home: Path, snapshot: list | None = None, *extra: str) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, str(SCRIPT), "--codex-home", str(home), *extra]
        if snapshot is not None:
            path = home / "snapshot.json"
            path.write_text(json.dumps(snapshot))
            command += ["--api-snapshot", str(path)]
        return subprocess.run(command, text=True, capture_output=True)

    def add_thread(self, home: Path, thread_id: str, source: str = "vscode", archived: int = 0, raw: str | None = None) -> Path:
        path = home / f"{thread_id}.jsonl"
        if raw is not None:
            path.write_text(raw)
        with sqlite3.connect(home / "state_5.sqlite") as db:
            db.execute("INSERT INTO threads VALUES(?,?,?,?,?,?,?,?)", (thread_id, str(path), 10, 20, source, thread_id, archived, "paginated"))
        return path

    def test_scope_real_missing_and_interrupted_empty_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp); make_databases(home)
            self.add_thread(home, "active", raw=raw_events(started("empty")))
            self.add_thread(home, "archived", archived=1, raw=raw_events(started("lost"), message()))
            self.add_thread(home, "sub", source=json.dumps({"subagent": "worker"}), raw=raw_events(started("lost"), message()))
            self.add_thread(home, "missing")
            snapshot = [{"id": "active", "page": {"hasMore": False, "nextCursor": None}, "turns": [], "error": None}]
            result = self.run_audit(home, snapshot)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual([x["id"] for x in report["classified_candidates"]["missing_source_file_path"]], ["missing"])
            self.assertEqual(report["classified_candidates"]["raw_text_turn_not_returned"], [])
            self.assertIn("archived", report["explicit_exclusions"]["archived_without_include_flag"])
            self.assertIn("sub", report["explicit_exclusions"]["json_subagents_without_include_flag"])
            explicit = json.loads(self.run_audit(home, snapshot, "--thread-id", "archived", "--thread-id", "sub").stdout)
            self.assertEqual(explicit["scope"]["selected_count"], 0)
            self.assertIn("archived", explicit["explicit_exclusions"]["archived_without_include_flag"])
            self.assertIn("sub", explicit["explicit_exclusions"]["json_subagents_without_include_flag"])
            included = json.loads(self.run_audit(home, snapshot, "--thread-id", "archived", "--thread-id", "sub", "--include-archived", "--include-subagents").stdout)
            self.assertEqual(included["scope"]["selected_count"], 2)

    def test_complete_snapshot_finds_missing_and_aggregates_duplicate_started(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp); make_databases(home)
            self.add_thread(home, "t", raw=raw_events(started("turn"), message(), started("turn"), message("again")))
            snapshot = [{"id": "t", "page": {"hasMore": False, "nextCursor": None}, "turns": [], "error": None}]
            result = self.run_audit(home, snapshot)
            report = json.loads(result.stdout)
            self.assertEqual(report["classified_candidates"]["raw_text_turn_not_returned"][0]["turn_ids"], ["turn"])
            self.assertEqual(report["threads"][0]["raw"]["task_started_counts"], {"turn": 2})

    def test_partial_or_error_snapshot_does_not_claim_missing(self) -> None:
        for entry in [
            {"id": "t", "page": {"hasMore": True, "nextCursor": "next"}, "turns": [], "error": None},
            {"id": "t", "page": {"hasMore": False, "nextCursor": None}, "turns": [], "error": "read failed"},
        ]:
            with self.subTest(entry=entry), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp); make_databases(home)
                self.add_thread(home, "t", raw=raw_events(started("turn"), message()))
                report = json.loads(self.run_audit(home, [entry]).stdout)
                self.assertEqual(report["classified_candidates"]["raw_text_turn_not_returned"], [])

    def test_api_empty_turn_with_db_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp); make_databases(home)
            self.add_thread(home, "t", raw=raw_events(started("turn")))
            with sqlite3.connect(home / "thread_history_1.sqlite") as db:
                db.execute("INSERT INTO thread_items VALUES('t','turn','item')")
            snapshot = [{"id": "t", "page": {"hasMore": False, "nextCursor": None}, "turns": [{"id": "turn", "status": "completed", "items": 0}], "error": None}]
            report = json.loads(self.run_audit(home, snapshot).stdout)
            candidates = report["classified_candidates"]["api_empty_turn_db_items_needs_full_items_confirmation"]
            self.assertEqual(candidates[0]["db_items"], 1)
            self.assertIn("itemsView:full", report["classification_notes"]["api_empty_turn_db_items_needs_full_items_confirmation"])

    def test_projection_lag_without_snapshot_is_risk_and_parses_raw(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp); make_databases(home)
            path = self.add_thread(home, "t", raw=raw_events(started("turn"), message()))
            with sqlite3.connect(home / "thread_history_1.sqlite") as db:
                db.execute("INSERT INTO thread_history_projection_state VALUES('t',?,1)", (path.stat().st_size - 1,))
            report = json.loads(self.run_audit(home).stdout)
            self.assertEqual(report["classified_candidates"]["projection_mismatch_risk"][0]["id"], "t")
            self.assertEqual(report["classified_candidates"]["raw_text_turn_not_returned"], [])
            self.assertIsNotNone(report["threads"][0]["raw"])

    def test_legacy_without_projection_is_not_a_risk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp); make_databases(home)
            self.add_thread(home, "legacy", raw=raw_events(started("turn"), message()))
            with sqlite3.connect(home / "state_5.sqlite") as db:
                db.execute("UPDATE threads SET history_mode='legacy' WHERE id='legacy'")
            report = json.loads(self.run_audit(home).stdout)
            self.assertEqual(report["classified_candidates"]["projection_mismatch_risk"], [])

    def test_unknown_schema_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp); make_databases(home, valid=False)
            result = self.run_audit(home)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsupported schema", result.stderr)


if __name__ == "__main__":
    unittest.main()
