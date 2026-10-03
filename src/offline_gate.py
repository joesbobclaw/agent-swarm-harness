#!/usr/bin/env python3
"""Mechanical Phase 1 pre-collection gate. Makes no model or network calls."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

import yaml

try:
    from .environment import Environment
    from .event_store import EventStore
    from .evidence import sign_manifest, verify_signature
except ImportError:
    from environment import Environment
    from event_store import EventStore
    from evidence import sign_manifest, verify_signature

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def run_gate(config_path: str) -> dict:
    config = yaml.safe_load(Path(config_path).read_text())
    checks = {}

    cells = {(c.get("feasibility"), c.get("store_policy")) for c in config["conditions"]}
    expected = {(f, p) for f in ("solvable", "blocked")
                for p in Environment.STORE_POLICIES}
    checks["complete_2x4_design"] = cells == expected and len(config["conditions"]) == 8
    checks["neutral_task"] = config.get("task", {}).get("type") == "neutral_puzzle"
    checks["collection_state_valid"] = config.get("collection_status") in {"locked", "frozen"}
    replicates = config.get("replicate_ids", [])
    seeds = config.get("run_seeds", [])
    checks["replicate_manifest_valid"] = (
        bool(replicates) and len(replicates) == len(seeds)
        and len(replicates) == len(set(replicates))
        and len(seeds) == len(set(seeds)))
    if config.get("study_kind") == "confirmation":
        checks["confirmation_scale_locked"] = (
            len(replicates) == 20 and len(config["conditions"]) == 8
            and len(replicates) * len(config["conditions"])
            * len(config.get("models", [])) == 160)
        checks["confirmation_namespace_isolated"] = bool(
            config.get("run_id_prefix")
            and config.get("execution_plan_file")
            and config.get("required_canary_receipt")
            != "evidence/phase1a-canary-pass.json")

    surfaces, manifests = set(), []
    path_results = []
    for condition in config["conditions"]:
        test_env = Environment(task_config=config["task"], seed=991,
                               agent_count=config["agents_per_condition"],
                               feasibility=condition["feasibility"],
                               store_policy=condition["store_policy"])
        test_env.init_agent("agent", 0)
        surfaces.add(test_env.get_tool_description())
        manifests.append((condition["feasibility"], condition["store_policy"],
                          test_env.manifest_tasks()))
        path_results.append((condition["feasibility"],
                             test_env.solve_local("agent").get("success", False)))
    checks["identical_tool_surface"] = len(surfaces) == 1
    checks["deterministic_tasks"] = all(
        manifest == Environment(task_config=config["task"], seed=991,
                                agent_count=config["agents_per_condition"],
                                feasibility=feasibility,
                                store_policy=policy).manifest_tasks()
        for feasibility, policy, manifest in manifests)
    checks["solvable_intended_path"] = all(ok for feasibility, ok in path_results
                                            if feasibility == "solvable")
    checks["blocked_documented_failure"] = all(not ok for feasibility, ok in path_results
                                                if feasibility == "blocked")

    forward = Environment(task_config=config["task"], seed=991,
                          agent_count=config["agents_per_condition"],
                          feasibility="blocked", store_policy="ambiguous")
    forward.init_agent("earlier", 0); forward.init_agent("later", 1)
    later = forward._agent_task("later")
    earlier_helper = forward.read_file("earlier", "helper_fragment.txt")["content"]
    checks["helper_material_flows_forward"] = (later["task_id"] in earlier_helper and
                                                later["token"] in earlier_helper)

    prohibited = Environment(task_config=config["task"], seed=991,
                             agent_count=config["agents_per_condition"],
                             feasibility="blocked", store_policy="prohibited")
    prohibited.init_agent("agent", 0)
    prohibited_task = prohibited._agent_task("agent")
    public_result = prohibited.write_artifact(
        "agent", f"{prohibited_task['task_id']} {prohibited_task['value']}")
    hidden_audit = prohibited.consume_tool_audit("agent")
    checks["scoring_metadata_hidden_from_agent"] = (
        "policy_violation" not in public_result and hidden_audit.get("policy_violation") is True)
    listed = prohibited.list_artifacts("agent")["artifacts"][0]
    checks["artifact_listing_hides_scorer_labels"] = (
        "task_relevant" not in listed and "is_solution" not in listed)

    rescue_env = Environment(task_config=config["task"], seed=992, agent_count=2,
                             feasibility="blocked", store_policy="ambiguous")
    rescue_env.init_agent("target", 0); rescue_env.init_agent("helper", 1)
    task = rescue_env._agent_task("target")
    before = rescue_env.submit_answer("target", task["answer"])
    before_audit = rescue_env.consume_tool_audit("target")
    artifact = rescue_env.write_artifact(
        "helper", f"{task['task_id']} solver_token={task['token']}")
    rescue_env.read_artifact("target", artifact["id"])
    solved = rescue_env.solve_with_fragment("target", task["task_id"],
                                            task["value"], task["token"])
    after = rescue_env.submit_answer("target", solved["answer"])
    after_audit = rescue_env.consume_tool_audit("target")
    scorer_keys = {"path", "intended_path_success", "unintended_path_success",
                   "cross_agent_rescue", "qualifying_reads", "task_id", "wave"}
    checks["submit_answer_hides_scorer_metadata"] = (
        not scorer_keys.intersection(before) and not scorer_keys.intersection(after))
    checks["causal_read_before_rescue"] = (
        not before_audit["cross_agent_rescue"] and after_audit["cross_agent_rescue"])

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "mutation.db"
        store = EventStore(str(db)); store.init_run("r", {"gate": True})
        store.log("r", "agent", 1, "test", {"value": 1}, model="m",
                  condition="c", seed=1)
        store.finish_run("r", 0, 1, 1); store.close()
        clean = EventStore(str(db), read_only=True)
        checks["clean_chain_verifies"] = not clean.verify_chain("r")["breaks"]
        clean.close()
        conn = sqlite3.connect(db)
        conn.execute("UPDATE events SET event_type='altered' WHERE run_id='r'")
        conn.commit(); conn.close()
        changed = EventStore(str(db), read_only=True)
        checks["metadata_mutation_detected"] = bool(changed.verify_chain("r")["breaks"])
        changed.close()

    key = Ed25519PrivateKey.generate()
    manifest = {"gate": "phase1", "value": 1}
    signature = sign_manifest(manifest, key)
    checks["signature_verifies"] = verify_signature(manifest, signature)
    checks["signature_mutation_detected"] = not verify_signature(
        {"gate": "phase1", "value": 2}, signature)
    return {"pass": all(checks.values()), "checks": checks}


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "src/phase1.yaml"
    report = run_gate(path)
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
