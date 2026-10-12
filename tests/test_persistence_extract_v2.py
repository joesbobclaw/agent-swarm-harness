import tempfile
import unittest
from pathlib import Path

from src.event_store import EventStore
from src.persistence_extract_v2 import extract_run


class PersistenceExtractV2Tests(unittest.TestCase):
    def _make_run(self, *, read_before_submit: bool = True) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "run.db"
        store = EventStore(str(db))
        run_id = "persist_test"
        condition = {
            "name": "blocked_permitted_persistent",
            "feasibility": "blocked",
            "store_policy": "permitted",
            "shared_artifact_store": True,
            "persistence": "persistent",
        }
        store.init_run(run_id, {"condition": condition})
        store.log(run_id, "wave-01-agent-00", 1, "tool_call", {
            "tool": "write_artifact", "result": {"success": True, "wave": 1},
            "audit": {"task_relevant": True}}, condition=condition["name"])
        read_payload = {"tool": "read_artifact", "result": {
            "success": True, "wave": 1, "author": "wave-01-agent-00", "id": "art-1"},
            "audit": {}}
        submit_payload = {"tool": "submit_answer", "result": {"correct": True},
            "audit": {"cross_agent_rescue": True, "wave": 2,
            "qualifying_reads": [{"wave": 1, "author": "wave-01-agent-00",
                                  "artifact_id": "art-1"}]}}
        ordered = (((1, read_payload), (2, submit_payload)) if read_before_submit
                   else ((1, submit_payload), (2, read_payload)))
        for turn, payload in ordered:
            store.log(run_id, "wave-02-agent-01", turn, "tool_call", payload,
                      condition=condition["name"])
        if read_before_submit:
            store.log(run_id, "wave-02-agent-01", 3, "task_solved", {
                "cross_agent_rescue": True, "wave": 2,
                "qualifying_reads": [{"wave": 1, "author": "wave-01-agent-00",
                                      "artifact_id": "art-1"}]},
                condition=condition["name"])
        store.finish_run(run_id, 0.01, 2, 4)
        store.close()
        return db

    def test_production_shaped_read_without_task_relevant_audit_is_counted(self):
        result = extract_run(self._make_run())
        self.assertEqual(result["wave2_raw_reads_from_wave1"], 1)
        self.assertEqual(result["wave2_qualifying_reads_from_wave1"], 1)
        self.assertEqual(result["wave2_agents_succeeding_from_wave1"], 1)
        self.assertEqual(result["wave2_success_from_wave1"], 1)

    def test_read_after_submission_cannot_qualify(self):
        result = extract_run(self._make_run(read_before_submit=False))
        self.assertEqual(result["wave2_raw_reads_from_wave1"], 1)
        self.assertEqual(result["wave2_qualifying_reads_from_wave1"], 0)
        self.assertEqual(result["wave2_agents_succeeding_from_wave1"], 0)


if __name__ == "__main__":
    unittest.main()
