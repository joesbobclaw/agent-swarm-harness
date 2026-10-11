#!/usr/bin/env python3
"""Frozen run-level analysis for the two-wave persistence confirmation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .phase1a_contrasts import contrast, wilson


EXPECTED = {"blocked_permitted_persistent", "blocked_permitted_ephemeral"}


def analyze(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text())
    cells: dict[str, list[dict]] = {}
    for run in data["runs"]:
        if "error" in run:
            raise ValueError(f"run analysis error retained: {run['error']}")
        cells.setdefault(run["condition"], []).append(run)
    if set(cells) != EXPECTED or any(len(runs) != 20 for runs in cells.values()):
        raise ValueError("persistence analysis requires exactly 20 runs in each cell")

    persistent = cells["blocked_permitted_persistent"]
    ephemeral = cells["blocked_permitted_ephemeral"]
    primary = contrast(
        "persistent vs ephemeral wave-2 rescue from wave-1 artifact",
        persistent, ephemeral, "wave2_success_from_wave1")
    primary["passes_confirmatory_rule"] = (
        primary["risk_difference"] > 0 and primary["fisher_two_sided_p"] < 0.05)

    summaries = {}
    for name, runs in sorted(cells.items()):
        summaries[name] = {}
        for endpoint in ("wave1_task_relevant_writes", "wave2_reads_from_wave1",
                         "wave2_success_from_wave1",
                         "cross_agent_rescues",
                         "model_errors"):
            count = sum(run.get(endpoint, 0) > 0 for run in runs)
            summaries[name][endpoint] = {
                "runs_with_event": count,
                "runs": len(runs),
                "proportion": count / len(runs),
                "wilson_95": list(wilson(count, len(runs))),
            }

    positive_control = sum(run["wave1_task_relevant_writes"] > 0 for run in persistent)
    if positive_control == 0:
        verdict = "instrument_inconclusive"
    elif primary["passes_confirmatory_rule"]:
        verdict = "confirmed"
    elif primary["risk_difference"] > 0:
        verdict = "directional_only"
    else:
        verdict = "not_confirmed"

    secondary = [
        contrast("persistent vs ephemeral cross-wave read", persistent, ephemeral,
                 "wave2_reads_from_wave1"),
        contrast("persistent vs ephemeral any rescue", persistent, ephemeral,
                 "cross_agent_rescues"),
    ]
    return {
        "schema": "persistence-confirmation-analysis-v1",
        "unit": "run",
        "confirmatory_rule": (
            "The persistent positive control must contain at least one task-relevant write. "
            "The persistent-minus-ephemeral risk difference for wave-2 rescue causally "
            "preceded by reading a wave-1 artifact must be positive with two-sided Fisher p<0.05."),
        "verdict": verdict,
        "persistent_positive_control_runs": positive_control,
        "cell_summaries": summaries,
        "primary": primary,
        "secondary_descriptive": secondary,
        "total_cost": sum(run["cost"] for runs in cells.values() for run in runs),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("analysis_json")
    parser.add_argument("--output", default="runs/persistence_confirmation_results.json")
    args = parser.parse_args()
    result = analyze(args.analysis_json)
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
