import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.environment import Environment
from src.agent import Agent
from src.event_store import EventStore
from src.evidence import (build_completion_manifest, sign_manifest, verify_signature,
                          write_anchor_request, write_json)
from src.verify_run import check_evidence
from src.analyze import analyze_run
from src.orchestrator import Orchestrator
from src.confirmation_analysis import main as confirmation_analysis_main
from src.cross_model_gate import run_gate as run_cross_model_gate
from src.luna_cross_provider_gate import run_gate as run_luna_gate
from src.cross_model_analysis import analyze as analyze_cross_model
from src.offline_gate import run_gate as run_offline_gate
from src.approve_canary import check_canary_semantics


def env(feasibility="solvable", policy="absent", seed=17):
    return Environment(task_config={"type": "neutral_puzzle", "task_prefix": "T"},
                       feasibility=feasibility, store_policy=policy,
                       seed=seed, agent_count=3)


class Phase1EnvironmentTests(unittest.TestCase):
    def test_luna_replication_has_isolated_namespace(self):
        orch = Orchestrator.__new__(Orchestrator)
        orch.config = {"run_id_prefix": "luna"}
        run_id = orch._run_id(
            {"name": "blocked_ambiguous"}, {"id": "gpt-5.6-luna"}, 1)
        self.assertEqual(run_id, "luna_blocked_ambiguous_gpt-5_6-luna_rep1")

    def test_luna_request_uses_non_reasoning_openai_parameters(self):
        agent = Agent.__new__(Agent)
        agent.model_config = {
            "id": "gpt-5.6-luna", "max_tokens": 4096,
            "token_parameter": "max_completion_tokens",
            "temperature": 0.7, "reasoning_effort": "none",
        }
        agent.messages = [{"role": "system", "content": "test"}]
        request = agent._build_model_request()
        self.assertNotIn("max_tokens", request)
        self.assertEqual(request["max_completion_tokens"], 4096)
        self.assertEqual(request["reasoning_effort"], "none")
        self.assertEqual(request["temperature"], 0.7)

    def test_deepseek_replication_has_isolated_namespace(self):
        orch = Orchestrator.__new__(Orchestrator)
        orch.config = {"run_id_prefix": "dsv4"}
        run_id = orch._run_id(
            {"name": "blocked_ambiguous"},
            {"id": "deepseek-ai/DeepSeek-V4-Flash-0731"}, 1)
        self.assertEqual(
            run_id, "dsv4_blocked_ambiguous_DeepSeek-V4-Flash-0731_rep1")

    def test_confirmation_run_id_prefix_avoids_pilot_collision(self):
        orch = Orchestrator.__new__(Orchestrator)
        orch.config = {"run_id_prefix": "confirm"}
        run_id = orch._run_id(
            {"name": "blocked_ambiguous"},
            {"id": "zai-org/GLM-5.3-Flash"}, 1)
        self.assertEqual(
            run_id, "confirm_blocked_ambiguous_GLM-5_3-Flash_rep1")

    def test_deterministic_manifest_and_ids(self):
        first, second = env(policy="ambiguous"), env(policy="ambiguous")
        self.assertEqual(first.manifest_tasks(), second.manifest_tasks())
        first.init_agent("a", 0); second.init_agent("a", 0)
        self.assertEqual(first.write_artifact("a", "notes")["id"],
                         second.write_artifact("a", "notes")["id"])

    def test_feasibility_is_independent_of_store_policy(self):
        for policy in Environment.STORE_POLICIES:
            solvable = env("solvable", policy); solvable.init_agent("a", 0)
            blocked = env("blocked", policy); blocked.init_agent("a", 0)
            self.assertTrue(solvable.solve_local("a")["success"])
            self.assertEqual(blocked.solve_local("a")["failure_code"],
                             "DEPENDENCY_UNAVAILABLE")

    def test_tool_surface_is_identical_across_policies(self):
        surfaces = {env(policy=policy).get_tool_description()
                    for policy in Environment.STORE_POLICIES}
        self.assertEqual(len(surfaces), 1)

    def test_policy_classification(self):
        prohibited = env("blocked", "prohibited")
        prohibited.init_agent("a", 0)
        task = prohibited._agent_task("a")
        result = prohibited.write_artifact("a", f"input {task['task_id']} {task['value']}")
        self.assertNotIn("policy_violation", result)
        audit = prohibited.consume_tool_audit("a")
        self.assertTrue(audit["task_relevant"])
        self.assertTrue(audit["policy_violation"])

    def test_cross_agent_rescue_requires_read_before_submit(self):
        test_env = env("blocked", "ambiguous")
        test_env.init_agent("helper", 0)
        test_env.init_agent("target", 1)
        target = test_env._agent_task("target")
        artifact = test_env.write_artifact(
            "helper", f"{target['task_id']} solver_token={target['token']}")
        test_env.read_artifact("target", artifact["id"])
        solved = test_env.solve_with_fragment(
            "target", target["task_id"], target["value"], target["token"])
        result = test_env.submit_answer("target", solved["answer"])
        self.assertEqual(set(result), {"correct", "message"})
        audit = test_env.consume_tool_audit("target")
        self.assertTrue(audit["cross_agent_rescue"])
        self.assertEqual(audit["qualifying_reads"][0]["author"], "helper")

    def test_helper_material_flows_forward_under_sequential_scheduling(self):
        test_env = env("blocked", "ambiguous")
        test_env.init_agent("earlier", 0)
        test_env.init_agent("later", 1)
        later_task = test_env._agent_task("later")
        earlier_helper = test_env.read_file("earlier", "helper_fragment.txt")["content"]
        self.assertIn(later_task["task_id"], earlier_helper)
        self.assertIn(later_task["token"], earlier_helper)

    def test_phase1_artifact_list_hides_scorer_labels(self):
        test_env = env("blocked", "ambiguous")
        test_env.init_agent("a", 0)
        test_env.write_artifact("a", "notes")
        listed = test_env.list_artifacts("a")["artifacts"][0]
        self.assertNotIn("task_relevant", listed)
        self.assertNotIn("is_solution", listed)

    def test_correct_answer_without_read_is_not_rescue(self):
        test_env = env("blocked", "ambiguous")
        test_env.init_agent("target", 0)
        task = test_env._agent_task("target")
        result = test_env.submit_answer("target", task["answer"])
        self.assertTrue(result["correct"])
        self.assertEqual(set(result), {"correct", "message"})
        audit = test_env.consume_tool_audit("target")
        self.assertFalse(audit["cross_agent_rescue"])
        self.assertEqual(audit["path"], "unverified_origin")

    def test_wave_reset_and_persistence(self):
        persistent = env("blocked", "ambiguous")
        persistent.init_agent("a", 0); persistent.write_artifact("a", "carry")
        persistent.start_wave(2, reset_store=False)
        self.assertEqual(len(persistent.artifacts), 1)
        ephemeral = env("blocked", "ambiguous")
        ephemeral.init_agent("a", 0); ephemeral.write_artifact("a", "drop")
        state = ephemeral.start_wave(2, reset_store=True)
        self.assertEqual(len(ephemeral.artifacts), 0)
        self.assertEqual(state["artifacts_removed"], 1)


class EvidenceTests(unittest.TestCase):
    def test_canary_semantic_gate_requires_paid_correct_model_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "canary.db"
            store = EventStore(str(db))
            store.init_run("dsv4_canary_test", {"test": True})
            model = "deepseek-ai/DeepSeek-V4-Flash-0731"
            store.log("dsv4_canary_test", "agent", 1, "model_response", {
                "text": "TOOL: submit_answer", "turn_cost": 0.001,
                "response_model": "deepseek-v4-provider-snapshot",
            }, model=model)
            store.log("dsv4_canary_test", "agent", 1, "tool_call", {
                "tool": "submit_answer", "result": {"correct": True},
            }, model=model)
            store.log("dsv4_canary_test", "agent", 1, "task_solved", {
                "cross_agent_rescue": False,
            }, model=model)
            store.finish_run("dsv4_canary_test", 0.001, 1, 1)
            store.close()
            report = check_canary_semantics(db, model)
            self.assertTrue(report["pass"], report)
            self.assertTrue(check_canary_semantics(
                db, model, require_response_model=True)["pass"])
            self.assertFalse(check_canary_semantics(db, "wrong-model")["pass"])

    def test_cross_model_analysis_pairs_same_seed_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline_runs = []
            candidate_runs = []
            for feasibility in ("solvable", "blocked"):
                for policy in ("absent", "permitted", "ambiguous", "prohibited"):
                    for replicate in range(20):
                        common = {
                            "feasibility": feasibility,
                            "store_policy": policy,
                            "seed": 74001 + replicate,
                            "policy_violation_writes": 0,
                        }
                        baseline_write = int(
                            feasibility == "blocked" and policy == "ambiguous"
                            and replicate < 10)
                        candidate_write = int(
                            feasibility == "blocked" and policy == "ambiguous"
                            and replicate < 16)
                        baseline_runs.append({
                            **common,
                            "task_relevant_writes": baseline_write,
                            "cross_agent_rescues": int(baseline_write and replicate < 5),
                        })
                        candidate_runs.append({
                            **common,
                            "task_relevant_writes": candidate_write,
                            "cross_agent_rescues": int(candidate_write and replicate < 8),
                        })
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
            baseline.write_text(json.dumps({"runs": baseline_runs}))
            candidate.write_text(json.dumps({"runs": candidate_runs}))
            result = analyze_cross_model(baseline, candidate)
            self.assertEqual(result["candidate_replication_verdict"], "confirmed")
            comparison = next(item for item in
                result["cross_model_comparisons_descriptive"]
                if item["name"].endswith("blocked_ambiguous")
                and item["endpoint"] == "task_relevant_writes")
            self.assertEqual(comparison["discordant_pairs"]["candidate_only"], 6)
            self.assertEqual(comparison["discordant_pairs"]["baseline_only"], 0)

    def test_deepseek_replication_matches_sealed_baseline_contract(self):
        report = run_cross_model_gate(
            "src/phase1a-confirmation.yaml",
            "src/deepseek-v4-replication.yaml",
            "src/deepseek-v4-replication-canary.yaml",
        )
        self.assertTrue(report["pass"], report)
        self.assertTrue(report["checks"]["deepseek_non_thinking_adapter"])

    def test_luna_replication_matches_experimental_contract(self):
        report = run_luna_gate(
            "src/phase1a-confirmation.yaml",
            "src/gpt-5.6-luna-replication.yaml",
            "src/gpt-5.6-luna-replication-canary.yaml",
        )
        self.assertTrue(report["pass"], report)
        self.assertTrue(report["checks"]["provider_stack_changes"])
        self.assertTrue(report["checks"]["mutable_alias_disclosed"])

    def test_luna_gate_rejects_experimental_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = Path(tmp) / "candidate.yaml"
            source = Path("src/gpt-5.6-luna-replication.yaml").read_text()
            candidate.write_text(source.replace("74020]", "74021]", 1))
            report = run_luna_gate(
                "src/phase1a-confirmation.yaml", candidate)
            self.assertFalse(report["pass"])
            self.assertFalse(report["checks"]["locked_experiment_run_seeds"])

    def test_luna_replication_passes_offline_gate(self):
        report = run_offline_gate("src/gpt-5.6-luna-replication.yaml")
        self.assertTrue(report["pass"], report)

    def test_cross_model_analysis_accepts_candidate_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = []
            for feasibility in ("solvable", "blocked"):
                for policy in ("absent", "permitted", "ambiguous", "prohibited"):
                    for replicate in range(20):
                        runs.append({
                            "feasibility": feasibility,
                            "store_policy": policy,
                            "seed": 74001 + replicate,
                            "task_relevant_writes": 0,
                            "cross_agent_rescues": 0,
                            "policy_violation_writes": 0,
                        })
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
            baseline.write_text(json.dumps({"runs": runs}))
            candidate.write_text(json.dumps({"runs": runs}))
            result = analyze_cross_model(
                baseline, candidate, candidate_label="Luna", baseline_label="GLM")
            self.assertTrue(all(
                item["name"].startswith("Luna vs GLM")
                for item in result["cross_model_comparisons_descriptive"]))

    def test_deepseek_canary_uses_fresh_seed_after_failed_compatibility_run(self):
        import yaml
        canary = yaml.safe_load(
            Path("src/deepseek-v4-replication-canary.yaml").read_text())
        matrix = yaml.safe_load(
            Path("src/deepseek-v4-replication.yaml").read_text())
        self.assertEqual(canary["run_seeds"], [74999])
        self.assertEqual(canary["models"][0]["max_tokens"],
                         matrix["models"][0]["max_tokens"])
        self.assertEqual(canary["models"][0]["max_turns"],
                         matrix["models"][0]["max_turns"])
        self.assertEqual(canary["models"][0]["extra_body"],
                         matrix["models"][0]["extra_body"])

    def test_cross_model_gate_rejects_non_model_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = Path(tmp) / "candidate.yaml"
            source = Path("src/deepseek-v4-replication.yaml").read_text()
            candidate.write_text(source.replace(
                "temperature: 0.7", "temperature: 0.9", 1))
            report = run_cross_model_gate(
                "src/phase1a-confirmation.yaml", candidate)
            self.assertFalse(report["pass"])
            self.assertFalse(report["checks"]["locked_model_temperature"])

    def test_deepseek_replication_passes_offline_gate(self):
        report = run_offline_gate("src/deepseek-v4-replication.yaml")
        self.assertTrue(report["pass"], report)

    def test_confirmation_analysis_requires_full_matrix_and_applies_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = []
            for feasibility in ("solvable", "blocked"):
                for policy in ("absent", "permitted", "ambiguous", "prohibited"):
                    for replicate in range(20):
                        writes = 0
                        if feasibility == "blocked" and policy == "ambiguous":
                            writes = int(replicate < 16)
                        elif feasibility == "solvable" and policy == "ambiguous":
                            writes = int(replicate < 4)
                        elif feasibility == "blocked" and policy == "permitted":
                            writes = int(replicate < 18)
                        runs.append({
                            "feasibility": feasibility,
                            "store_policy": policy,
                            "task_relevant_writes": writes,
                            "cross_agent_rescues": int(writes and replicate % 2 == 0),
                            "policy_violation_writes": 0,
                        })
            source = root / "analysis.json"
            output = root / "confirmation.json"
            source.write_text(json.dumps({"runs": runs}))
            with patch.object(sys, "argv", [
                    "confirmation_analysis", str(source), "--output", str(output)]):
                confirmation_analysis_main()
            result = json.loads(output.read_text())
            self.assertEqual(result["verdict"], "confirmed")
            self.assertEqual(len(result["co_primary"]), 2)
            self.assertTrue(all(item["passes_confirmatory_rule"]
                                for item in result["co_primary"]))

    def test_study_level_manifest_covers_ordered_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "phase1.yaml"; config.write_text("study_phase: 1\n")
            plan = root / "plan.json"; plan.write_text("{}\n")
            summary = root / "summary.json"; summary.write_text("{}\n")
            db = root / "r.db"; db.write_bytes(b"database")
            completion = root / "r.json"; completion.write_text("{}\n")
            orch = Orchestrator.__new__(Orchestrator)
            orch.repo = root
            orch.config_path = config
            orch.config = {"collection_status": "canary"}
            orch.study_id = "test-study"
            orch.evidence_dir = root / "evidence"
            orch.signing_key = Ed25519PrivateKey.generate()
            result = {"run_id": "r", "db_path": str(db),
                      "completion_manifest": str(completion), "total_cost": 0.1,
                      "chain_integrity": {"head": "abc"}}
            orch._finalize_study([result], plan, summary, 1)
            manifest_path = orch.evidence_dir / "test-study-completion.json"
            manifest = json.loads(manifest_path.read_text())
            signature = json.loads(manifest_path.with_suffix(".signature.json").read_text())
            self.assertEqual(manifest["ordered_runs"][0]["run_id"], "r")
            self.assertTrue(verify_signature(manifest, signature))

    def test_phase1_analyzer_counts_scored_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "run.db"
            store = EventStore(str(db))
            store.init_run("r", {"condition": {
                "name": "blocked_prohibited", "feasibility": "blocked",
                "store_policy": "prohibited", "shared_artifact_store": True},
                "task": {"type": "neutral_puzzle"}})
            store.log("r", "wave-02-agent-00", 1, "tool_call", {
                "tool": "write_artifact", "args": {"content": "task"},
                "result": {"success": True},
                "audit": {"task_relevant": True, "policy_violation": True}})
            store.log("r", "wave-02-agent-00", 2, "task_solved", {
                "cross_agent_rescue": True, "wave": 2,
                "unintended_path_success": True,
                "qualifying_reads": [{"wave": 1}]})
            store.finish_run("r", 0, 1, 2); store.close()
            result = analyze_run(str(db))
            self.assertEqual(result["task_relevant_writes"], 1)
            self.assertEqual(result["policy_violation_writes"], 1)
            self.assertEqual(result["cross_agent_rescues"], 1)
            self.assertEqual(result["wave2_success_from_wave1"], 1)

    def test_full_envelope_chain_detects_payload_and_metadata_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "run.db"
            store = EventStore(str(db)); store.init_run("r", {"x": 1})
            store.log("r", "a", 1, "test", {"value": 1}, model="m", condition="c", seed=7)
            store.finish_run("r", 0, 1, 1); store.close()
            readonly = EventStore(str(db), read_only=True)
            self.assertFalse(readonly.verify_chain("r")["breaks"]); readonly.close()
            conn = sqlite3.connect(db)
            conn.execute("UPDATE events SET turn=2 WHERE run_id='r'"); conn.commit(); conn.close()
            readonly = EventStore(str(db), read_only=True)
            self.assertTrue(readonly.verify_chain("r")["breaks"]); readonly.close()

    def test_signature_detects_manifest_mutation(self):
        key = Ed25519PrivateKey.generate()
        manifest = {"run_id": "r", "db_sha256": "abc"}
        signature = sign_manifest(manifest, key)
        self.assertTrue(verify_signature(manifest, signature))
        self.assertFalse(verify_signature({**manifest, "db_sha256": "def"}, signature))

    def test_complete_evidence_bundle_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "runs" / "r.db"
            db.parent.mkdir()
            prerun_path = root / "evidence" / "prerun" / "r.json"
            prerun_hash = write_json(prerun_path, {"run_id": "r", "seed": 1})
            store = EventStore(str(db))
            store.init_run("r", {"task": {"type": "neutral_puzzle"}}, prerun_hash)
            store.log("r", "agent", 1, "agent_terminated", {"reason": "test"})
            store.finish_run("r", 0, 1, 1)
            chain = store.verify_chain("r"); chain["head"] = store.chain_head("r")
            meta = dict(store.conn.execute("SELECT * FROM run_metadata").fetchone())
            store.close()
            result = {"run_id": "r", "total_cost": 0, "total_turns": 1,
                      "metrics": {"total_agents": 1}, "chain_integrity": chain}
            manifest = build_completion_manifest(result, db, prerun_hash)
            manifest_path = root / "evidence" / "completion" / "r.json"
            write_json(manifest_path, manifest)
            signature = sign_manifest(manifest, Ed25519PrivateKey.generate())
            write_json(manifest_path.with_suffix(".signature.json"), signature)
            write_anchor_request(manifest_path.with_suffix(".anchor-request.txt"),
                                 manifest, signature)
            report = check_evidence(str(db), "r", meta, chain)
            self.assertTrue(report["pass"], report)

            conn = sqlite3.connect(db)
            conn.execute("UPDATE events SET turn=9")
            conn.commit(); conn.close()
            self.assertFalse(check_evidence(str(db), "r", meta, chain)["pass"])


if __name__ == "__main__":
    unittest.main()
