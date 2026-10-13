"""Fail-closed contract gate for the coordination shadow validation pilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def gate(matrix_path: Path, canary_path: Path) -> dict:
    matrix = yaml.safe_load(matrix_path.read_text())
    canary = yaml.safe_load(canary_path.read_text())
    expected = {(feasibility, policy) for feasibility in ("solvable", "blocked")
                for policy in ("absent", "permitted", "ambiguous", "prohibited")}
    actual = {(row["feasibility"], row["store_policy"]) for row in matrix["conditions"]}
    checks = {
        "launch_states": matrix.get("collection_status") == "frozen"
                  and canary.get("collection_status") == "canary",
        "complete_2x4": actual == expected and len(matrix["conditions"]) == 8,
        "three_replicates": len(matrix.get("replicate_ids", [])) == 3
                            and len(matrix.get("run_seeds", [])) == 3,
        "five_agents": matrix.get("agents_per_condition") == 5,
        "fresh_namespace": matrix.get("run_id_prefix") == "shadowv1",
        "same_model_route": matrix.get("provider_route") == canary.get("provider_route"),
        "canary_excluded": canary.get("run_kind") == "excluded_canary",
        "canary_solvable_permitted": len(canary.get("conditions", [])) == 1
            and canary["conditions"][0].get("feasibility") == "solvable"
            and canary["conditions"][0].get("store_policy") == "permitted",
        "bounded_budget": 0 < float(matrix.get("cost_budget", 0)) <= 1.0,
    }
    return {"checks": checks, "pass": all(checks.values())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("matrix", type=Path)
    parser.add_argument("--canary", type=Path, required=True)
    args = parser.parse_args(argv)
    result = gate(args.matrix, args.canary)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
