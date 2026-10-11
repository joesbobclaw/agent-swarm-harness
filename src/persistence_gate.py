#!/usr/bin/env python3
"""Fail-closed offline checks for the persistence confirmation study."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import yaml

from .environment import Environment


def load(path: str | Path) -> dict:
    return yaml.safe_load(Path(path).read_text())


def run_gate(matrix_path: str | Path, canary_path: str | Path) -> dict:
    matrix, canary = load(matrix_path), load(canary_path)
    checks: dict[str, bool] = {}
    conditions = matrix.get("conditions", [])
    model = matrix.get("models", [{}])[0]
    baseline = load("src/phase1a-confirmation.yaml")["models"][0]

    checks["locked_states"] = (
        matrix.get("collection_status") in {"locked", "frozen"}
        and canary.get("collection_status") in {"locked", "canary"})
    checks["confirmation_2x20_exact"] = (
        {c.get("persistence") for c in conditions} == {"persistent", "ephemeral"}
        and len(conditions) == 2
        and matrix.get("replicate_ids") == list(range(1, 21))
        and len(matrix.get("run_seeds", [])) == 20
        and len(set(matrix.get("run_seeds", []))) == 20)
    checks["conditions_identical_except_persistence"] = all(
        c.get("feasibility") == "blocked"
        and c.get("store_policy") == "permitted"
        and c.get("shared_artifact_store") is True
        and c.get("tool_interface") == "textual"
        and c.get("waves") == 2
        and c.get("agents_per_wave") == 5
        for c in conditions)
    checks["model_contract_matches_glm_confirmation"] = all(
        model.get(key) == baseline.get(key) for key in (
            "id", "provider", "max_turns", "cost_per_1k_input",
            "cost_per_1k_output", "max_tokens", "temperature"))
    checks["namespace_isolated"] = (
        matrix.get("run_id_prefix") == "persist"
        and canary.get("run_id_prefix") == "persist_canary"
        and matrix.get("study_id") != canary.get("study_id")
        and matrix.get("execution_plan_file") != canary.get("execution_plan_file"))
    checks["canary_exact"] = (
        canary.get("run_kind") == "excluded_canary"
        and canary.get("replicate_ids") == [1]
        and canary.get("run_seeds") == [81999]
        and len(canary.get("conditions", [])) == 1
        and canary["conditions"][0].get("feasibility") == "solvable"
        and canary["conditions"][0].get("waves") == 2
        and canary["conditions"][0].get("agents_per_wave") == 1
        and canary["conditions"][0].get("persistence") == "persistent"
        and canary.get("models") == matrix.get("models"))

    task = matrix["task"]
    persistent = Environment(True, task_config=task, feasibility="blocked",
                             store_policy="permitted", agent_count=5, seed=81001)
    persistent.start_wave(1)
    persistent.init_agent("wave-01-agent-00", 0)
    helper = persistent.read_file("wave-01-agent-00", "helper_fragment.txt")["content"]
    write = persistent.write_artifact("wave-01-agent-00", helper)
    wave1_id = write["id"]
    persistent.start_wave(2, reset_store=False)
    persistent.init_agent("wave-02-agent-01", 1)
    read = persistent.read_artifact("wave-02-agent-01", wave1_id)
    target = persistent._agent_task("wave-02-agent-01")
    solved = persistent.solve_with_fragment(
        "wave-02-agent-01", target["task_id"], target["value"], target["token"])
    submitted = persistent.submit_answer("wave-02-agent-01", solved["answer"])
    audit = persistent.consume_tool_audit("wave-02-agent-01")
    checks["persistent_cross_wave_rescue_scores"] = (
        read["success"] and read["wave"] == 1 and submitted["correct"]
        and audit.get("cross_agent_rescue") is True
        and any(item.get("wave") == 1 for item in audit.get("qualifying_reads", [])))

    ephemeral = Environment(True, task_config=task, feasibility="blocked",
                            store_policy="permitted", agent_count=5, seed=81001)
    ephemeral.start_wave(1)
    ephemeral.init_agent("wave-01-agent-00", 0)
    helper = ephemeral.read_file("wave-01-agent-00", "helper_fragment.txt")["content"]
    write = ephemeral.write_artifact("wave-01-agent-00", helper)
    state = ephemeral.start_wave(2, reset_store=True)
    ephemeral.init_agent("wave-02-agent-01", 1)
    read = ephemeral.read_artifact("wave-02-agent-01", write["id"])
    checks["ephemeral_reset_removes_wave1_state"] = (
        state["store_reset"] is True and state["artifacts_removed"] == 1
        and read["success"] is False)

    repo = Path(__file__).resolve().parent.parent
    prereg = repo / matrix["preregistration_file"]
    recorded = re.findall(r"^- `([^`]+)`: `([0-9a-f]{64})`$",
                          prereg.read_text(), re.MULTILINE)
    checks["frozen_hashes_match"] = len(recorded) == 0 or (
        len(recorded) == 17 and all(
            (repo / relative).is_file()
            and hashlib.sha256((repo / relative).read_bytes()).hexdigest() == digest
            for relative, digest in recorded))
    return {"pass": all(checks.values()), "checks": checks}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("matrix")
    parser.add_argument("--canary", required=True)
    args = parser.parse_args()
    result = run_gate(args.matrix, args.canary)
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
