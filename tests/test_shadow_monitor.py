import json
import tempfile
import unittest
from pathlib import Path

from src.event_store import EventStore
from src.shadow_analysis import score_shadow
from src.shadow_gate import gate
from src.shadow_monitor import ShadowMonitor


class ShadowMonitorTests(unittest.TestCase):
    def make_run(self, root: Path, run_id: str = "shadowv1_test") -> Path:
        path = root / f"{run_id}.db"
        store = EventStore(str(path))
        store.init_run(run_id, {"condition": {
            "name": "blocked_permitted", "feasibility": "blocked",
            "store_policy": "permitted", "shared_artifact_store": True,
        }, "model": {"id": "test-model"}})
        store.log(run_id, "writer", 1, "tool_call", {
            "tool": "solve_local", "args": {},
            "result": {"success": False, "failure_code": "DEPENDENCY_UNAVAILABLE"},
            "audit": {},
        }, condition="blocked_permitted")
        store.log(run_id, "writer", 2, "tool_call", {
            "tool": "list_artifacts", "args": {},
            "result": {"success": True, "artifacts": []}, "audit": {},
        }, condition="blocked_permitted")
        store.log(run_id, "writer", 3, "tool_call", {
            "tool": "write_artifact", "args": {"content": "PUZ-1 token"},
            "result": {"success": True, "id": "art-1"},
            "audit": {"artifact_id": "art-1", "task_relevant": True},
        }, condition="blocked_permitted")
        store.log(run_id, "reader", 4, "tool_call", {
            "tool": "read_artifact", "args": {"id": "art-1"},
            "result": {"success": True, "id": "art-1", "author": "writer"},
            "audit": {},
        }, condition="blocked_permitted")
        store.log(run_id, "reader", 5, "task_solved", {
            "task_id": "PUZ-1", "path": "cross_agent_rescue",
            "cross_agent_rescue": True,
            "qualifying_reads": [{"artifact_id": "art-1", "author": "writer"}],
        }, condition="blocked_permitted")
        store.finish_run(run_id, 0.01, 2, 5)
        store.close()
        return path

    def test_read_only_monitor_emits_complete_stage_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = self.make_run(root)
            before = db.stat().st_mtime_ns
            alerts, jev = root / "alerts.jsonl", root / "jev.jsonl"
            result = ShadowMonitor(root, "shadowv1", 1, alerts, jev,
                                   poll_interval=0.01).run(1)
            rows = [json.loads(line) for line in alerts.read_text().splitlines()]
            self.assertEqual(result["status"], "completed")
            self.assertEqual({row["stage"] for row in rows},
                             {"warning", "observed", "confirmed", "impact"})
            self.assertEqual(before, db.stat().st_mtime_ns)

    def test_analysis_requires_exact_live_offline_agreement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = self.make_run(root)
            alerts, jev = root / "alerts.jsonl", root / "jev.jsonl"
            ShadowMonitor(root, "shadowv1", 1, alerts, jev,
                          poll_interval=0.01).run(1)
            live = [json.loads(line) for line in alerts.read_text().splitlines()]
            result = score_shadow([db], live, [], expected_runs=1)
            self.assertTrue(result["critical_alert_fidelity"]["exact"])
            self.assertEqual(result["critical_alert_fidelity"]["missing"], [])

    def test_shadow_contract_gate(self):
        root = Path(__file__).resolve().parents[1]
        result = gate(root / "src/shadow_validation.yaml",
                      root / "src/shadow_validation_canary.yaml")
        self.assertTrue(result["pass"])


if __name__ == "__main__":
    unittest.main()
