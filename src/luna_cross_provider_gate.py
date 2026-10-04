#!/usr/bin/env python3
"""Fail-closed contract checks for the GPT-5.6 Luna replication."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


LOCKED_EXPERIMENT_FIELDS = (
    "study_phase", "signing_key_path_env", "agent_cost_budget", "plan_seed",
    "conditions", "agents_per_condition", "max_turns_per_agent",
    "replicate_ids", "run_seeds", "task",
)
LOCKED_MODEL_FIELDS = ("max_turns", "max_tokens", "temperature")
CANARY_MODEL_FIELDS = (
    "id", "name", "provider", "cost_per_1k_input", "cost_per_1k_output",
    "temperature", "max_turns", "max_tokens", "reasoning_effort",
    "token_parameter", "snapshot_status",
)


def load_yaml(path: str | Path) -> dict:
    return yaml.safe_load(Path(path).read_text())


def run_gate(baseline_path: str | Path, candidate_path: str | Path,
             canary_path: str | Path | None = None) -> dict:
    baseline = load_yaml(baseline_path)
    candidate = load_yaml(candidate_path)
    checks: dict[str, bool] = {}

    checks["single_model_each"] = (
        len(baseline.get("models", [])) == 1
        and len(candidate.get("models", [])) == 1
    )
    baseline_model = baseline.get("models", [{}])[0]
    candidate_model = candidate.get("models", [{}])[0]

    for field in LOCKED_EXPERIMENT_FIELDS:
        checks[f"locked_experiment_{field}"] = (
            baseline.get(field) == candidate.get(field))
    for field in LOCKED_MODEL_FIELDS:
        checks[f"locked_model_{field}"] = (
            baseline_model.get(field) == candidate_model.get(field))

    checks["model_family_changes"] = (
        baseline_model.get("id") != candidate_model.get("id"))
    checks["luna_model_exact"] = candidate_model.get("id") == "gpt-5.6-luna"
    checks["openai_provider_exact"] = (
        candidate.get("api_base") == "https://api.openai.com/v1"
        and candidate.get("api_key_env") == "OPENAI_API_KEY"
        and candidate_model.get("provider") == "openai"
    )
    checks["provider_stack_changes"] = (
        baseline.get("api_base") != candidate.get("api_base")
        and baseline_model.get("provider") != candidate_model.get("provider"))
    checks["non_reasoning_mode"] = (
        candidate_model.get("reasoning_effort") == "none")
    checks["openai_token_parameter"] = (
        candidate_model.get("token_parameter") == "max_completion_tokens")
    checks["mutable_alias_disclosed"] = (
        candidate_model.get("snapshot_status")
        == "mutable_alias_no_dated_snapshot_available_at_freeze")
    checks["official_pricing_locked"] = (
        candidate_model.get("cost_per_1k_input") == 0.0002
        and candidate_model.get("cost_per_1k_output") == 0.0012)
    checks["cost_budget_scaled_only_for_provider"] = (
        candidate.get("cost_budget") == 8.0
        and candidate.get("cost_budget") > baseline.get("cost_budget", 0))
    checks["replication_namespace_isolated"] = (
        bool(candidate.get("run_id_prefix"))
        and candidate.get("run_id_prefix") != baseline.get("run_id_prefix")
        and candidate.get("study_id") != baseline.get("study_id")
        and candidate.get("execution_plan_file") != baseline.get("execution_plan_file")
        and candidate.get("required_canary_receipt")
        != baseline.get("required_canary_receipt")
    )
    checks["matrix_state_valid"] = (
        candidate.get("collection_status") in {"locked", "frozen"})
    checks["replication_scale"] = (
        len(candidate.get("conditions", [])) == 8
        and len(candidate.get("replicate_ids", [])) == 20
        and len(candidate.get("conditions", []))
        * len(candidate.get("replicate_ids", []))
        * len(candidate.get("models", [])) == 160
    )

    if canary_path is not None:
        canary = load_yaml(canary_path)
        canary_model = canary.get("models", [{}])[0]
        checks["canary_excluded"] = (
            canary.get("run_kind") == "excluded_canary")
        checks["canary_state_valid"] = (
            canary.get("collection_status") in {"locked", "canary"})
        checks["canary_model_matches"] = all(
            canary_model.get(field) == candidate_model.get(field)
            for field in CANARY_MODEL_FIELDS)
        checks["canary_route_matches"] = (
            canary.get("api_base") == candidate.get("api_base")
            and canary.get("api_key_env") == candidate.get("api_key_env")
            and canary.get("provider_route") == candidate.get("provider_route"))
        checks["canary_namespace_isolated"] = (
            canary.get("study_id") != candidate.get("study_id")
            and canary.get("run_id_prefix") != candidate.get("run_id_prefix")
            and canary.get("execution_plan_file")
            != candidate.get("execution_plan_file"))
        checks["canary_shape"] = (
            len(canary.get("conditions", [])) == 1
            and len(canary.get("replicate_ids", [])) == 1
            and canary.get("agents_per_condition") == 1
            and canary.get("conditions", [{}])[0].get("feasibility") == "solvable"
            and canary.get("conditions", [{}])[0].get("store_policy") == "permitted"
        )

    return {"pass": all(checks.values()), "checks": checks}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline")
    parser.add_argument("candidate")
    parser.add_argument("--canary")
    args = parser.parse_args()
    report = run_gate(args.baseline, args.candidate, args.canary)
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
