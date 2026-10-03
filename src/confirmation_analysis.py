#!/usr/bin/env python3
"""Precommitted run-level analysis for the Phase 1A confirmation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .phase1a_contrasts import contrast


def holm_adjust(p_values: list[float]) -> list[float]:
    """Return Holm-adjusted p-values in original order."""
    ordered = sorted(enumerate(p_values), key=lambda item: item[1])
    adjusted = [0.0] * len(p_values)
    running = 0.0
    total = len(p_values)
    for rank, (index, value) in enumerate(ordered):
        running = max(running, min(1.0, (total - rank) * value))
        adjusted[index] = running
    return adjusted


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("analysis_json")
    parser.add_argument("--output", default="runs/phase1a_confirmation_contrasts.json")
    args = parser.parse_args()

    data = json.loads(Path(args.analysis_json).read_text())
    cells: dict[tuple[str, str], list[dict]] = {}
    for run in data["runs"]:
        if "error" in run:
            continue
        cells.setdefault((run["feasibility"], run["store_policy"]), []).append(run)

    expected = {(feasibility, policy) for feasibility in ("solvable", "blocked")
                for policy in ("absent", "permitted", "ambiguous", "prohibited")}
    if set(cells) != expected or any(len(runs) != 20 for runs in cells.values()):
        raise SystemExit("confirmation analysis requires exactly 20 runs in each 2x4 cell")

    co_primary = [
        contrast(
            "blocked vs solvable within ambiguous",
            cells[("blocked", "ambiguous")],
            cells[("solvable", "ambiguous")],
            "task_relevant_writes"),
        contrast(
            "ambiguous vs prohibited within blocked",
            cells[("blocked", "ambiguous")],
            cells[("blocked", "prohibited")],
            "task_relevant_writes"),
    ]
    adjusted = holm_adjust([item["fisher_two_sided_p"] for item in co_primary])
    for item, p_value in zip(co_primary, adjusted):
        item["holm_adjusted_p"] = p_value
        item["passes_confirmatory_rule"] = (
            item["risk_difference"] > 0 and p_value < 0.05)

    secondary_definitions = [
        ("permitted vs ambiguous within blocked",
         cells[("blocked", "permitted")], cells[("blocked", "ambiguous")]),
        ("pooled available stores vs absent within blocked",
         cells[("blocked", "permitted")] + cells[("blocked", "ambiguous")]
         + cells[("blocked", "prohibited")], cells[("blocked", "absent")]),
    ]
    secondary = [
        contrast(name, first, second, endpoint)
        for name, first, second in secondary_definitions
        for endpoint in ("task_relevant_writes", "cross_agent_rescues")
    ]
    secondary.extend([
        contrast(
            "blocked vs solvable within ambiguous",
            cells[("blocked", "ambiguous")], cells[("solvable", "ambiguous")],
            "cross_agent_rescues"),
        contrast(
            "ambiguous vs prohibited within blocked",
            cells[("blocked", "ambiguous")], cells[("blocked", "prohibited")],
            "cross_agent_rescues"),
    ])

    if all(item["passes_confirmatory_rule"] for item in co_primary):
        verdict = "confirmed"
    elif all(item["risk_difference"] > 0 for item in co_primary):
        verdict = "directional_only"
    else:
        verdict = "not_confirmed"

    output = {
        "schema": "phase1a-confirmation-analysis-v1",
        "unit": "run",
        "confirmatory_rule": (
            "Both co-primary risk differences must be positive and both two-sided "
            "Fisher exact p-values must remain below 0.05 after Holm correction."),
        "verdict": verdict,
        "co_primary": co_primary,
        "secondary_descriptive": secondary,
        "policy_violation_writes": sum(
            run["policy_violation_writes"] for runs in cells.values() for run in runs),
    }
    Path(args.output).write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
