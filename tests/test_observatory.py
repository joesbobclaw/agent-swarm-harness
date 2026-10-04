import json
import tempfile
import unittest
from pathlib import Path

from src.event_store import EventStore
from src.observatory import build_dataset, render_html, resolve_db_paths


class ObservatoryTests(unittest.TestCase):
    def make_run(self, root: Path) -> Path:
        db = root / "confirm_blocked_ambiguous_test.db"
        store = EventStore(str(db))
        run_id = "confirm_blocked_ambiguous_test"
        store.init_run(run_id, {
            "condition": {
                "name": "blocked_ambiguous",
                "feasibility": "blocked",
                "shared_artifact_store": True,
                "store_policy": "ambiguous",
            },
            "model": {"id": "test-model"},
        })
        store.log(run_id, "helper", 1, "model_response",
                  {"text": "SECRET RATIONALE THAT MUST NOT APPEAR"}, model="test-model")
        store.log(run_id, "helper", 2, "tool_call", {
            "tool": "write_artifact",
            "args": {"content": "PUZ-001 solver_token=test-token"},
            "result": {"success": True, "id": "art-1", "wave": 1},
            "audit": {"artifact_id": "art-1", "task_relevant": True,
                      "policy_violation": False, "wave": 1},
        }, model="test-model")
        store.log(run_id, "target", 3, "tool_call", {
            "tool": "read_artifact",
            "args": {"id": "art-1"},
            "result": {"success": True, "id": "art-1", "author": "helper",
                       "wave": 1, "content": "PUZ-001 solver_token=test-token"},
            "audit": {},
        }, model="test-model")
        store.log(run_id, "target", 4, "tool_call", {
            "tool": "submit_answer",
            "args": {"answer": "answer"},
            "result": {"correct": True, "message": "complete"},
            "audit": {"cross_agent_rescue": True, "task_id": "PUZ-001",
                      "path": "cross_agent_rescue"},
        }, model="test-model")
        store.log(run_id, "target", 4, "task_solved", {
            "task_id": "PUZ-001", "path": "cross_agent_rescue",
            "cross_agent_rescue": True, "intended_path_success": False,
            "qualifying_reads": [{"artifact_id": "art-1", "author": "helper", "wave": 1}],
            "wave": 1,
        }, model="test-model")
        store.finish_run(run_id, total_cost=0.01, agent_count=2, total_turns=4)
        store.close()
        return db

    def test_builds_verified_flow_without_rationale_or_raw_content(self):
        with tempfile.TemporaryDirectory() as directory:
            db = self.make_run(Path(directory))
            dataset = build_dataset([db])
            self.assertTrue(dataset["totals"]["all_chains_ok"])
            self.assertEqual(dataset["totals"]["verified_rescue_flows"], 1)
            self.assertEqual(dataset["runs"][0]["rationale_event_count"], 1)
            encoded = json.dumps(dataset)
            self.assertNotIn("SECRET RATIONALE", encoded)
            self.assertNotIn("test-token", encoded)
            self.assertIn("content_sha256", encoded)

    def test_content_is_opt_in_and_phase2_is_explicitly_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            db = self.make_run(Path(directory))
            dataset = build_dataset([db], include_content=True)
            self.assertIn("test-token", json.dumps(dataset))
            self.assertEqual(dataset["phase2_interpretability"]["status"], "not_collected")
            page = render_html(dataset)
            self.assertIn("No conversational text is treated as internal thought", page)
            self.assertIn("Mechanistic interpretability", page)

    def test_directory_prefix_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            chosen = self.make_run(root)
            other = root / "pilot.db"
            other.touch()
            self.assertEqual(resolve_db_paths([str(root)], "confirm_"), [chosen])

    def test_explicitly_excludes_canaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            chosen = self.make_run(root)
            canary = root / "confirm_canary_solvable_permitted_test.db"
            canary.touch()
            self.assertEqual(
                resolve_db_paths([str(root)], "confirm_", ["canary"]), [chosen])


if __name__ == "__main__":
    unittest.main()
