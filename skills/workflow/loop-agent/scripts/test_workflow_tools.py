#!/usr/bin/env python3
"""Offline regression checks; all fixtures are created in temporary directories."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import workflow_tools as w


class WorkflowToolsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "cfg").mkdir()
        (self.root / "project").mkdir()
        self.project = self.root / "project"
        (self.project / "fetch.py").write_text("print('fixture only')\n")
        (self.project / "prompt.md").write_text("Summarize the provided evidence.\n")
        self.path = self.root / "cfg" / "flow.json"
        self.config = {
            "version": 1, "id": "daily", "goal": "Summarize new records",
            "completion": ["A validated summary exists"],
            "paths": {"project_root": "../project", "logs": [], "state": None, "artifacts": None, "scripts": None},
            "runtime": {"required_commands": [], "required_env": []},
            "limits": {"workflow_timeout_seconds": 300, "max_attempts": 2, "max_consecutive_failures": 3, "max_parallel": 1, "token_budget": None},
            "controls": {"timeout": "runner timeout setting", "retry": "runner retries", "overlap": "scheduler skip", "idempotency": "input hash", "circuit_breaker": "pause after 3 failures"},
            "related_workflows": [],
            "steps": [self.step("fetch", []), self.step("analyze", ["fetch"], "ai")],
        }
        self.save()

    def step(self, name, needs, kind="script"):
        result = {"id": name, "title": name, "kind": kind, "needs": needs,
                  "inputs": [], "outputs": ["result"], "success_criteria": ["output validates"],
                  "timeout_seconds": 60, "max_attempts": 1, "side_effects": False}
        if kind == "script":
            result.update(command=[sys.executable, "fetch.py"], script_file="fetch.py")
        else:
            result.update(prompt_file="prompt.md", token_budget=1000)
        return result

    def save(self):
        self.path.write_text(json.dumps(self.config))

    def invoke(self, command, *extra):
        output = io.StringIO()
        with patch("sys.stdout", output):
            code = w.cli([command, "--config", str(self.path), *extra])
        return code, json.loads(output.getvalue())

    def lint(self):
        return w.lint_config(self.config, self.project)

    def event(self, step, status, run="run-a", **extra):
        return {"timestamp": "2026-11-24T10:00:00+08:00", "workflow_id": "daily", "run_id": run, "step_id": step, "status": status, "attempt": 1, **extra}

    def events(self, records, name="events.jsonl"):
        path = self.project / name
        path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
        return str(path)

    # @wu-test type=behavior | scope=validate | protects=validation creates paths or ignores the configured root
    def test_valid_dag_custom_project_root_and_no_created_paths(self):
        before = sorted(str(path) for path in self.root.rglob("*"))
        code, result = self.invoke("lint")
        self.assertEqual(code, 0)
        self.assertEqual(result["planned_route"]["stages"], [["fetch"], ["analyze"]])
        self.assertEqual(result["planned_route"]["successors"]["fetch"], ["analyze"])
        self.assertEqual(result["project_root"], str(self.project))
        self.assertEqual(before, sorted(str(path) for path in self.root.rglob("*")))
        self.assertFalse(result["enforcement_verified"])

    # @wu-test type=boundary | scope=validate | protects=invalid dependency graphs pass validation
    def test_cycles_unknown_dependencies_and_duplicate_ids(self):
        self.config["steps"][0]["needs"] = ["analyze"]
        self.assertIn("CYCLE", [item["code"] for item in self.lint()["errors"]])
        self.config["steps"][0]["needs"] = ["missing"]
        self.assertIn("DEPENDENCY", [item["code"] for item in self.lint()["errors"]])
        self.config["steps"][1]["id"] = "fetch"
        self.assertIn("DUPLICATE", [item["code"] for item in self.lint()["errors"]])

    # @wu-test type=boundary | scope=validate | protects=invalid counts or unsafe side-effect retries are accepted
    def test_boolean_not_integer_and_side_effect_retry(self):
        self.config["limits"]["workflow_timeout_seconds"] = True
        self.config["steps"][0]["max_attempts"] = 2
        self.config["steps"][0]["side_effects"] = True
        codes = [item["code"] for item in self.lint()["errors"]]
        self.assertIn("BOUND", codes)
        self.assertIn("UNSAFE_RETRY", codes)

    # @wu-test type=boundary | scope=validate | protects=invalid reference and command shapes reach execution
    def test_references_and_command_arrays(self):
        self.config["steps"][0]["script_file"] = "absent.py"
        self.config["steps"][0]["command"] = "echo untrusted-command"
        codes = [item["code"] for item in self.lint()["errors"]]
        self.assertIn("MISSING_FILE", codes)
        self.assertIn("COMMAND", codes)

    # @wu-test type=boundary | scope=validate | protects=malformed configuration produces an unhandled traceback
    def test_malformed_config_clean_error_no_traceback(self):
        self.path.write_text('{"id": invalid}')
        code, result = self.invoke("lint")
        self.assertEqual(code, 2)
        self.assertIn("Invalid JSON", result["error"])

    # @wu-test type=boundary | scope=validate | protects=duplicate keys silently override configuration
    def test_duplicate_json_keys_rejected(self):
        self.path.write_text('{"id":"a","id":"b"}')
        code, result = self.invoke("lint")
        self.assertEqual(code, 2)
        self.assertIn("Duplicate", result["error"])

    # @wu-test type=boundary | scope=validate | protects=remote URIs are handled as local paths
    def test_uri_not_treated_as_local_path(self):
        self.config["paths"]["state"] = "s3://bucket/state.json"
        self.save()
        code, result = self.invoke("lint")
        self.assertEqual(code, 1)
        self.assertTrue(any(item["code"] == "PATH" for item in result["errors"]))

    # @wu-test type=boundary | scope=preflight | protects=preflight leaks environment values or runs configured commands
    def test_preflight_env_presence_only_and_no_config_command_execution(self):
        self.config["runtime"]["required_env"] = ["LOOP_TEST_CREDENTIAL"]
        self.config["runtime"]["required_commands"] = [sys.executable]
        self.config["steps"][0]["command"] = ["touch", str(self.project / "must-not-exist")]
        self.save()
        with patch.dict(os.environ, {"LOOP_TEST_CREDENTIAL": "private-value-must-not-print"}):
            code, result = self.invoke("preflight")
        self.assertEqual(code, 0)
        self.assertEqual(result["required_env_present"], {"LOOP_TEST_CREDENTIAL": True})
        self.assertNotIn("private-value-must-not-print", json.dumps(result))
        self.assertFalse((self.project / "must-not-exist").exists())
        self.assertEqual(result["capabilities"]["network_access"], "not_tested")
        self.assertFalse(result["enforcement_verified"])

    # @wu-test type=behavior | scope=preflight | protects=missing required dependencies are reported as ready
    def test_preflight_missing_required_dependencies(self):
        self.config["runtime"]["required_commands"] = ["loop-agent-definitely-absent-command"]
        self.save()
        code, result = self.invoke("preflight")
        self.assertEqual(code, 1)
        self.assertEqual(result["missing"], ["command:loop-agent-definitely-absent-command"])

    # @wu-test type=boundary | scope=collect | protects=evidence ignores path overrides or exceeds the global budget
    def test_collect_uses_overrides_and_global_budget(self):
        (self.project / "one.log").write_text("old\n" * 100 + "tail line\n")
        (self.project / "two.log").write_text("second\n")
        code, result = self.invoke("collect", "--log", "one.log", "--log", "two.log", "--max-bytes", "40", "--max-lines", "2")
        self.assertEqual(code, 0)
        self.assertEqual(result["bytes_charged"], 40)
        self.assertTrue(result["files"][0]["truncated"])
        self.assertLessEqual(len(result["files"][0]["excerpt"].splitlines()), 2)
        self.assertEqual(result["files"][1]["skipped"], "global_byte_budget")

    # @wu-test type=boundary | scope=collect | protects=collected evidence exposes credentials
    def test_collect_redacts_tokens_passwords_url_and_private_keys(self):
        secret_log = 'password=supersecret\napi_key: "anothersecret"\nAuthorization: Bearer abcd1234xyz\nhttps://u:pass@example.org?q=hello&access_token=xyz123\ntoken=secret123\nsession_token=session-secret\nAuthorization: Basic dXNlcjpwYXNz\n-----BEGIN PRIVATE KEY-----\nabcxyz\n-----END PRIVATE KEY-----\n'
        (self.project / "secrets.log").write_text(secret_log)
        code, result = self.invoke("collect", "--log", "secrets.log")
        self.assertEqual(code, 0)
        excerpt = result["files"][0]["excerpt"]
        for secret in ("supersecret", "anothersecret", "abcd1234xyz", "u:pass", "xyz123", "secret123", "session-secret", "dXNlcjpwYXNz", "abcxyz"):
            self.assertNotIn(secret, excerpt)
        self.assertIn("REDACTED", excerpt)

    # @wu-test type=boundary | scope=collect | protects=missing files pass silently or FIFO reads block collection
    def test_collect_refuses_missing_files_and_fifo(self):
        code, result = self.invoke("collect", "--log", "missing.log")
        self.assertEqual(code, 1)
        self.assertTrue(result["errors"])
        if hasattr(os, "mkfifo"):
            os.mkfifo(self.project / "fifo")
            code, result = self.invoke("collect", "--log", "fifo")
            self.assertEqual(code, 1)
            self.assertIn("not a regular file", result["errors"][0]["error"])

    # @wu-test type=behavior | scope=collect | protects=collection invents evidence when no sources are provided
    def test_collect_without_sources_returns_empty_evidence(self):
        code, result = self.invoke("collect")
        self.assertEqual(code, 0)
        self.assertTrue(result["no_sources_configured"])
        self.assertEqual(result["files"], [])

    # @wu-test type=boundary | scope=collect | protects=file output creates undeclared directories or duplicates data on stdout
    def test_explicit_output_requires_parent_and_leaves_stdout_empty(self):
        target = self.root / "absent" / "result.json"
        code, result = self.invoke("lint", "--output", str(target))
        self.assertEqual(code, 2)
        self.assertFalse(target.parent.exists())
        stdout = io.StringIO()
        target = self.root / "report.json"
        with patch("sys.stdout", stdout):
            code = w.cli(["lint", "--config", str(self.path), "--output", str(target)])
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), "")
        self.assertTrue(json.loads(target.read_text())["ok"])

    # @wu-test type=behavior | scope=report | protects=reports misidentify the route or double-count attempts
    def test_report_preserves_actual_route_and_deduplicates_attempt_metrics(self):
        records = [self.event("fetch", "running", tokens=1), self.event("fetch", "failed", tokens=10, event_id="a"), self.event("fetch", "failed", tokens=10, event_id="a"), self.event("fetch", "succeeded", attempt=2, tokens=20, event_id="b"), self.event("analyze", "succeeded", tokens=30, event_id="c")]
        source = self.events(records)
        code, result = self.invoke("report", "--events", source)
        self.assertEqual(code, 0)
        self.assertEqual([item["status"] for item in result["actual_route"]], ["running", "failed", "succeeded", "succeeded"])
        self.assertEqual(result["metrics"]["tokens"], 60)
        self.assertIsNone(result["metrics"]["tool_calls"])
        self.assertFalse(result["completion_verified"])
        self.assertEqual(result["execution_status"], "all_steps_reported_succeeded")

    # @wu-test type=boundary | scope=report | protects=events from different runs are combined without selection
    def test_report_multi_run_requires_selection(self):
        source = self.events([self.event("fetch", "succeeded"), self.event("fetch", "succeeded", run="run-b")])
        code, result = self.invoke("report", "--events", source)
        self.assertEqual(code, 2)
        self.assertIn("--run-id", result["error"])
        code, result = self.invoke("report", "--events", source, "--run-id", "run-a")
        self.assertEqual(code, 0)
        self.assertEqual(len(result["actual_route"]), 1)
        self.assertEqual(result["execution_status"], "partial")

    # @wu-test type=behavior | scope=report | protects=unreliable evidence is reported as success
    def test_report_incomplete_invalid_or_conflicting_evidence_not_success(self):
        source = self.events([self.event("fetch", "succeeded", event_id="x"), self.event("fetch", "failed", event_id="x"), self.event("analyze", "succeeded"), self.event("fetch", "succeeded", workflow_id="other")])
        code, result = self.invoke("report", "--events", source)
        self.assertEqual(code, 1)
        self.assertTrue(result["incomplete_evidence"])
        self.assertEqual(result["execution_status"], "incomplete_evidence")
        self.assertEqual(result["metrics"]["tokens"], None)

    # @wu-test type=behavior | scope=report | protects=missing evidence is reported as completion
    def test_report_no_evidence_is_unknown_not_complete(self):
        code, result = self.invoke("report")
        self.assertEqual(code, 0)
        self.assertEqual(result["execution_status"], "unknown")
        self.assertEqual(result["actual_route"], [])
        self.assertFalse(result["completion_verified"])

    # @wu-test type=boundary | scope=report | protects=event input grows beyond the configured limit
    def test_report_bound_event_input(self):
        source = self.events([self.event("fetch", "succeeded"), self.event("analyze", "succeeded")])
        with patch.object(w, "MAX_EVENT_BYTES", 180):
            code, result = self.invoke("report", "--events", source)
        self.assertEqual(code, 1)
        self.assertTrue(result["incomplete_evidence"])
        self.assertLessEqual(result["bytes_read"], 180)

    # @wu-test type=boundary | scope=report | protects=blocked reasons expose credentials
    def test_report_redacts_blocked_reason(self):
        source = self.events([self.event("fetch", "blocked", agent_id="agent-a", reason="request password=secret-value")])
        code, result = self.invoke("report", "--events", source)
        self.assertEqual(code, 0)
        self.assertEqual(result["execution_status"], "blocked")
        self.assertEqual(result["actual_route"][0]["agent_id"], "agent-a")
        self.assertNotIn("secret-value", json.dumps(result))

    # @wu-test type=behavior | scope=collect | protects=configuration errors discard useful diagnostic evidence
    def test_collect_survives_configuration_failure_for_diagnosis(self):
        (self.project / "fetch.py").unlink()
        (self.project / "failure.log").write_text("missing fetch.py\n")
        code, result = self.invoke("collect", "--log", "failure.log")
        self.assertEqual(code, 0)
        self.assertTrue(result["configuration_issues"])
        self.assertIn("missing fetch.py", result["files"][0]["excerpt"])

    # @wu-test type=boundary | scope=report | protects=invalid events erase valid evidence
    def test_malformed_event_types_preserve_other_evidence(self):
        source = self.events([self.event("fetch", "succeeded"), self.event("analyze", []), self.event("analyze", "succeeded")])
        code, result = self.invoke("report", "--events", source)
        self.assertEqual(code, 1)
        self.assertEqual(len(result["actual_route"]), 2)
        self.assertEqual(result["execution_status"], "incomplete_evidence")

    # @wu-test type=behavior | scope=report | protects=skipped steps appear as successful work
    def test_skipped_step_is_not_reported_succeeded(self):
        source = self.events([self.event("fetch", "succeeded"), self.event("analyze", "skipped", reason="no new input")])
        code, result = self.invoke("report", "--events", source)
        self.assertEqual(code, 0)
        self.assertEqual(result["execution_status"], "finished_with_skips")
        self.assertFalse(result["completion_verified"])

    # @wu-test type=boundary | scope=report | protects=broken references or graphs prevent a diagnostic report
    def test_report_survives_missing_reference_and_bad_graph(self):
        (self.project / "fetch.py").unlink()
        self.config["steps"][0]["needs"] = ["analyze"]
        self.save()
        source = self.events([self.event("fetch", "failed", reason="missing executable")])
        code, result = self.invoke("report", "--events", source)
        self.assertEqual(code, 0)
        self.assertTrue(result["configuration_issues"])
        self.assertIsNone(result["planned_route"])
        self.assertEqual(result["execution_status"], "failed")

    # @wu-test type=boundary | scope=workflow_tools | protects=writing output destroys configuration or evidence
    def test_output_cannot_overwrite_config_or_evidence(self):
        source = self.events([self.event("fetch", "failed")])
        original = Path(source).read_bytes()
        code, result = self.invoke("report", "--events", source, "--output", source)
        self.assertEqual(code, 2)
        self.assertIn("overwrite", result["error"])
        self.assertEqual(Path(source).read_bytes(), original)
        config_before = self.path.read_bytes()
        code, _ = self.invoke("lint", "--output", str(self.path))
        self.assertEqual(code, 2)
        self.assertEqual(self.path.read_bytes(), config_before)
        alias = self.root / "alias.jsonl"
        os.link(source, alias)
        code, _ = self.invoke("report", "--events", source, "--output", str(alias))
        self.assertEqual(code, 2)

    # @wu-test type=boundary | scope=report | protects=an unknown run inherits evidence from a different run
    def test_unknown_run_id_has_no_evidence(self):
        source = self.events([self.event("fetch", "succeeded")])
        code, result = self.invoke("report", "--events", source, "--run-id", "missing-run")
        self.assertEqual(code, 0)
        self.assertEqual(result["execution_status"], "unknown")
        self.assertEqual(result["actual_route"], [])
        self.assertIsNone(result["metrics"]["tokens"])

    # @wu-test type=boundary | scope=validate | protects=unexpected field types cause an unhandled error
    def test_unhashable_config_fields_clean_error(self):
        self.config["steps"][0]["kind"] = []
        self.save()
        code, result = self.invoke("lint")
        self.assertEqual(code, 1)
        self.assertTrue(any(item["code"] == "KIND" for item in result["errors"]))

    # @wu-test type=boundary | scope=lint | protects=connector steps lack a tool reference
    def test_tool_step_is_supported_and_requires_reference(self):
        step = self.config["steps"][0]
        step.update(kind="tool", tool_ref="connector.read_records")
        step.pop("command")
        self.assertTrue(self.lint()["ok"])
        step.pop("tool_ref")
        self.assertIn("TOOL_REF", [error["code"] for error in self.lint()["errors"]])

    # @wu-test type=boundary | scope=load_config | protects=duplicate YAML keys silently override workflow settings
    def test_yaml_duplicate_keys_rejected(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("optional PyYAML not installed")
        path = self.root / "duplicate.yaml"
        path.write_text("id: first\nid: second\n")
        with self.assertRaisesRegex(w.ToolError, "Duplicate"):
            w.load_config(str(path))

    # @wu-test type=behavior | scope=audit | protects=recurring failures, stale steps or exceeded budgets go unreported
    def test_audit_recurring_failures_and_limits(self):
        self.config["limits"]["token_budget"] = 50
        self.save()
        records = [self.event("fetch", "failed", reason_code="AUTH_REQUIRED", tokens=30, attempt=2),
                   self.event("fetch", "failed", reason_code="AUTH_REQUIRED", tokens=80, attempt=3, run="run-b"),
                   self.event("analyze", "running", run="run-c")]
        code, result = self.invoke("audit", "--events", self.events(records), "--stale-seconds", "60", "--as-of", "2026-11-24T10:10:00+08:00")
        self.assertEqual(code, 0)
        self.assertEqual(result["included_runs"], 3)
        codes = {finding["code"] for finding in result["findings"]}
        self.assertTrue({"REPEATED_FAILURE_SIGNATURE", "OBSERVED_TOKEN_BUDGET_EXCEEDED", "OBSERVED_ATTEMPT_LIMIT_EXCEEDED", "NO_RECENT_STEP_EVENT"} <= codes)
        self.assertIsNone(next(run for run in result["runs"] if run["run_id"] == "run-c")["usage"]["tokens"]["observed_sum"])

    # @wu-test type=behavior | scope=audit | protects=limited or missing evidence is reported as complete
    def test_audit_window_mixed_revision_and_unknown_evidence(self):
        records = [self.event("fetch", "running", workflow_revision="v1"),
                   self.event("fetch", "succeeded", workflow_revision="v2", timestamp="2026-11-24T10:05:00+08:00"),
                   self.event("fetch", "failed", run="old", timestamp="2026-11-23T10:00:00+08:00")]
        code, result = self.invoke("audit", "--events", self.events(records), "--max-runs", "1")
        self.assertEqual(code, 0)
        self.assertTrue(result["incomplete_evidence"])
        self.assertEqual(result["runs"][0]["run_id"], "run-a")
        self.assertIn("MIXED_REVISIONS", [finding["code"] for finding in result["findings"]])
        code, result = self.invoke("audit")
        self.assertEqual(code, 0)
        self.assertTrue(result["incomplete_evidence"])
        self.assertEqual(result["observed_runs"], 0)

    # @wu-test type=boundary | scope=audit | protects=corrupt events hide valid evidence or invalid audit bounds pass
    def test_audit_partial_corrupt_evidence_and_bounds(self):
        source = self.events([self.event("fetch", "failed", reason_code="bad code"), self.event("fetch", "succeeded")])
        code, result = self.invoke("audit", "--events", source)
        self.assertEqual(code, 1)
        self.assertTrue(result["incomplete_evidence"])
        self.assertEqual(result["included_runs"], 1)
        self.assertEqual(self.invoke("audit", "--max-runs", "101")[0], 2)
        self.assertEqual(self.invoke("audit", "--as-of", "2026-11-24T10:00:00")[0], 2)

    # @wu-test type=integration | scope=workflow_tools CLI | protects=the command fails when launched as a subprocess
    def test_cli_subprocess_actually_runs(self):
        process = subprocess.run([sys.executable, str(Path(w.__file__)), "lint", "--config", str(self.path)], capture_output=True, text=True, timeout=10)
        self.assertEqual(process.returncode, 0)
        self.assertTrue(json.loads(process.stdout)["ok"])
        self.assertEqual(process.stderr, "")


if __name__ == "__main__":
    unittest.main()
