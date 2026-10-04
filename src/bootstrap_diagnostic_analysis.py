#!/usr/bin/env python3
"""Frozen descriptive analysis for the GPT-5.4 Mini bootstrap diagnostic."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .phase1a_contrasts import contrast, wilson


EXPECTED = {
    "blocked_permitted_empty_textual",
    "blocked_permitted_seeded_textual",
    "blocked_permitted_empty_native",
    "blocked_permitted_seeded_native",
}


def analyze(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text())
    cells: dict[str, list[dict]] = {}
    for run in data["runs"]:
        if "error" in run:
            raise ValueError(f"run analysis error retained: {run['error']}")
        cells.setdefault(run["condition"], []).append(run)
    if set(cells) != EXPECTED or any(len(runs) != 10 for runs in cells.values()):
        raise ValueError("diagnostic analysis requires exactly 10 runs in each 2x2 cell")

    summaries = {}
    for name, runs in sorted(cells.items()):
        values = {}
        for endpoint in (
            "task_relevant_writes", "cross_agent_rescues", "seeded_rescues",
            "seeded_artifact_reads", "model_errors",
        ):
            successes = sum(int(run[endpoint] > 0) for run in runs)
            values[endpoint] = {
                "runs_with_event": successes,
                "runs": len(runs),
                "proportion": successes / len(runs),
                "wilson_95": list(wilson(successes, len(runs))),
            }
        summaries[name] = values

    definitions = [
        ("native vs textual initiation with empty store",
         cells["blocked_permitted_empty_native"],
         cells["blocked_permitted_empty_textual"], "task_relevant_writes"),
        ("seeded vs empty rescue under textual tools",
         cells["blocked_permitted_seeded_textual"],
         cells["blocked_permitted_empty_textual"], "cross_agent_rescues"),
        ("seeded vs empty rescue under native tools",
         cells["blocked_permitted_seeded_native"],
         cells["blocked_permitted_empty_native"], "cross_agent_rescues"),
        ("native vs textual adoption with seeded store",
         cells["blocked_permitted_seeded_native"],
         cells["blocked_permitted_seeded_textual"], "seeded_rescues"),
    ]
    return {
        "schema": "gpt54mini-bootstrap-diagnostic-analysis-v1",
        "unit": "run",
        "status": "exploratory_pilot",
        "decision_rule": "No confirmatory verdict; report all four cells and frozen contrasts.",
        "cell_summaries": summaries,
        "contrasts": [contrast(name, first, second, endpoint)
                      for name, first, second, endpoint in definitions],
        "total_model_errors": sum(
            run["model_errors"] for runs in cells.values() for run in runs),
        "total_cost": sum(run["cost"] for runs in cells.values() for run in runs),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("analysis_json")
    parser.add_argument("--output", default="runs/gpt54mini_bootstrap_diagnostic_results.json")
    args = parser.parse_args()
    result = analyze(args.analysis_json)
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
