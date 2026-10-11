import json
import tempfile
import unittest
from pathlib import Path

from src.persistence_analysis import analyze
from src.persistence_extract import extract_run
from src.persistence_gate import run_gate
from src.event_store import EventStore


ROOT = Path(__file__).resolve().parent.parent
MATRIX = ROOT / "src/persistence-confirmation.yaml"
CANARY = ROOT / "src/persistence-confirmation-canary.yaml"


class PersistenceStudyTests(unittest.TestCase):
    def test_contract_gate(self):
        report = run_gate(MATRIX, CANARY)
        self.assertTrue(report["pass"], report)

    def test_analysis_requires_complete_cells(self):
        runs = []
        for condition in ("blocked_permitted_persistent", "blocked_permitted_ephemeral"):
            for _ in range(20):
                runs.append({
                    "condition": condition, "wave1_task_relevant_writes": 1,
                    "wave2_reads_from_wave1": int("persistent" in condition),
                    "wave2_success_from_wave1": int("persistent" in condition),
                    "cross_agent_rescues": int("persistent" in condition),
                    "model_errors": 0, "cost": 0.01,
                })
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "analysis.json"
            source.write_text(json.dumps({"runs": runs}))
            result = analyze(source)
        self.assertEqual(result["verdict"], "confirmed")
        self.assertEqual(result["primary"]["first"]["successes"], 20)
        self.assertEqual(result["primary"]["second"]["successes"], 0)

    def test_analysis_rejects_missing_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "analysis.json"
            source.write_text(json.dumps({"runs": []}))
            with self.assertRaises(ValueError):
                analyze(source)

    def test_extractor_separates_wave1_writes_and_wave2_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "run.db"
            store = EventStore(str(db))
            run_id = "persist_test"
            condition = {
                "name": "blocked_permitted_persistent",
                "feasibility": "blocked", "store_policy": "permitted",
                "shared_artifact_store": True, "persistence": "persistent",
            }
            store.init_run(run_id, {"condition": condition})
            store.log(run_id, "wave-01-agent-00", 1, "tool_call", {
                "tool": "write_artifact", "result": {"success": True, "wave": 1},
                "audit": {"task_relevant": True}}, condition=condition["name"])
            store.log(run_id, "wave-02-agent-01", 1, "tool_call", {
                "tool": "read_artifact",
                "result": {"success": True, "wave": 1, "author": "wave-01-agent-00"},
                "audit": {"task_relevant": True}}, condition=condition["name"])
            store.log(run_id, "wave-02-agent-01", 2, "task_solved", {
                "cross_agent_rescue": True, "wave": 2,
                "qualifying_reads": [{"wave": 1, "author": "wave-01-agent-00"}]},
                condition=condition["name"])
            store.finish_run(run_id, 0.01, 2, 3)
            store.close()
            result = extract_run(db)
        self.assertEqual(result["wave1_task_relevant_writes"], 1)
        self.assertEqual(result["wave2_reads_from_wave1"], 1)
        self.assertEqual(result["wave2_success_from_wave1"], 1)


if __name__ == "__main__":
    unittest.main()
