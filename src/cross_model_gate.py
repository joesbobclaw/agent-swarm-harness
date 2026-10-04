#!/usr/bin/env python3
"""Fail-closed checks for a one-model-at-a-time replication."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


LOCKED_TOP_LEVEL_FIELDS = (
    "study_phase", "api_base", "api_key_env", "signing_key_path_env",
    "cost_budget", "agent_cost_budget", "plan_seed", "conditions",
    "agents_per_condition", "max_turns_per_agent", "replicate_ids",
    "run_seeds", "task",
)

LOCKED_MODEL_FIELDS = ("provider", "max_turns", "max_tokens", "temperature")


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

    for field in LOCKED_TOP_LEVEL_FIELDS:
        checks[f"locked_top_level_{field}"] = baseline.get(field) == candidate.get(field)
    for field in LOCKED_MODEL_FIELDS:
        checks[f"locked_model_{field}"] = baseline_model.get(field) == candidate_model.get(field)

    checks["model_family_changes"] = baseline_model.get("id") != candidate_model.get("id")
    checks["deepseek_model_exact"] = (
        candidate_model.get("id") == "deepseek-ai/DeepSeek-V4-Flash-0731"
    )
    checks["same_provider_stack"] = (
        baseline.get("api_base") == candidate.get("api_base")
        and baseline_model.get("provider") == candidate_model.get("provider") == "baseten"
    )
    checks["pricing_is_positive"] = all(
        candidate_model.get(field, 0) > 0
        for field in ("cost_per_1k_input", "cost_per_1k_output")
    )
    checks["replication_namespace_isolated"] = (
        bool(candidate.get("run_id_prefix"))
        and candidate.get("run_id_prefix") != baseline.get("run_id_prefix")
        and candidate.get("study_id") != baseline.get("study_id")
        and candidate.get("execution_plan_file") != baseline.get("execution_plan_file")
        and candidate.get("required_canary_receipt") != baseline.get("required_canary_receipt")
    )
    checks["matrix_state_valid"] = candidate.get("collection_status") in {"locked", "frozen"}
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
        checks["canary_excluded"] = canary.get("run_kind") == "excluded_canary"
        checks["canary_state_valid"] = canary.get("collection_status") in {"locked", "canary"}
        checks["canary_model_matches"] = all(
            canary_model.get(field) == candidate_model.get(field)
            for field in (
                "id", "name", "provider", "cost_per_1k_input",
                "cost_per_1k_output", "temperature",
            )
        )
        checks["canary_route_matches"] = (
            canary.get("api_base") == candidate.get("api_base")
            and canary.get("provider_route") == candidate.get("provider_route")
        )
        checks["canary_namespace_isolated"] = (
            canary.get("study_id") != candidate.get("study_id")
            and canary.get("run_id_prefix") != candidate.get("run_id_prefix")
            and canary.get("execution_plan_file") != candidate.get("execution_plan_file")
        )
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
