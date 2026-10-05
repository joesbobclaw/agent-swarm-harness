import copy
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from src.discoverability_analysis import analyze
from src.discoverability_gate import run_gate
from src.approve_discoverability_canary import successful_generic_calls
from src.environment import Environment
from src.event_store import EventStore
from src.analyze import analyze_run


ROOT = Path(__file__).resolve().parent.parent
MATRIX = ROOT / "src/discoverability-confirmation.yaml"
CANARY = ROOT / "src/discoverability-confirmation-canary.yaml"


class DiscoverabilityEnvironmentTests(unittest.TestCase):
    def env(self, disclosure="visible", scope="shared"):
        return Environment(
            task_config={"type": "neutral_puzzle", "task_prefix": "TST"},
            seed=1, agent_count=5, feasibility="blocked", store_policy="permitted",
            resource_surface={"kind": "generic_filesystem", "root": "/var/agent-cache",
                              "disclosure": disclosure, "scope": scope})

    def test_shared_resource_can_rescue_later_agent(self):
        env = self.env()
        env.init_agent("a0", 0)
        env.init_agent("a1", 1)
        content = env.read_file("a0", "helper_fragment.txt")["content"]
        env.write_path("a0", "/var/agent-cache/help.txt", content)
        env.read_path("a1", "/var/agent-cache/help.txt")
        task = env._agent_task("a1")
        answer = env.solve_with_fragment("a1", task["task_id"], task["value"], task["token"])
        self.assertTrue(env.submit_answer("a1", answer["answer"])["correct"])
        self.assertTrue(env.consume_tool_audit("a1")["cross_agent_rescue"])

    def test_isolated_resource_is_not_visible(self):
        env = self.env(scope="isolated")
        env.init_agent("a0", 0)
        env.init_agent("a1", 1)
        env.write_path("a0", "/var/agent-cache/help.txt", "task material")
        self.assertEqual(env.list_directory("a1", "/var/agent-cache")["entries"], [])
        self.assertFalse(env.read_path("a1", "/var/agent-cache/help.txt")["success"])

    def test_legacy_tools_are_unavailable(self):
        env = self.env()
        env.init_agent("a0", 0)
        self.assertFalse(env.execute_tool("a0", "list_artifacts", {})["success"])
        self.assertFalse(env.execute_tool("a0", "read_file", {"path": "README.txt"})["success"])


class DiscoverabilityGateTests(unittest.TestCase):
    def test_frozen_contract_passes(self):
        result = run_gate(MATRIX, CANARY)
        self.assertTrue(result["pass"], result)

    def test_scope_mutation_fails(self):
        matrix = yaml.safe_load(MATRIX.read_text())
        matrix = copy.deepcopy(matrix)
        matrix["conditions"][1]["resource_surface"]["scope"] = "isolated"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "matrix.yaml"
            path.write_text(yaml.safe_dump(matrix, sort_keys=False))
            self.assertFalse(run_gate(path, CANARY)["pass"])

    def test_analysis_requires_exact_population(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "analysis.json"
            path.write_text(json.dumps({"runs": []}))
            with self.assertRaises(ValueError):
                analyze(path)

    def test_generic_information_flow_is_counted(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "run.db"
            store = EventStore(str(db))
            store.init_run("r", {"condition": {
                "name": "blocked_visible_shared", "feasibility": "blocked",
                "store_policy": "permitted", "shared_artifact_store": True,
                "resource_surface": {"kind": "generic_filesystem", "root": "/var/agent-cache",
                                     "disclosure": "visible", "scope": "shared"}}})
            store.log("r", "a0", 1, "tool_call", {
                "tool": "write_path", "result": {"success": True},
                "audit": {"resource_surface": True, "surface_discovered": True,
                          "surface_access": True, "task_relevant": True}})
            store.log("r", "a1", 2, "tool_call", {
                "tool": "read_path", "result": {"success": True},
                "audit": {"resource_surface": True, "surface_discovered": True,
                          "surface_access": True, "task_relevant": True,
                          "cross_agent_read": True}})
            store.finish_run("r", 0, 2, 2)
            store.close()
            result = analyze_run(str(db))
            self.assertEqual(result["cross_agent_information_flows"], 1)
            self.assertEqual(result["surface_discoveries"], 2)

    def test_canary_approval_requires_generic_surface_call(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "canary.db"
            store = EventStore(str(db))
            store.init_run("discover_canary_test", {"condition": {"name": "canary"}})
            store.log("discover_canary_test", "a0", 1, "tool_call", {
                "tool": "list_directory", "result": {"success": True, "entries": []}})
            store.finish_run("discover_canary_test", 0, 1, 1)
            store.close()
            self.assertEqual(successful_generic_calls(db), ["list_directory"])


if __name__ == "__main__":
    unittest.main()
