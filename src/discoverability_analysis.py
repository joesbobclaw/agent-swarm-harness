#!/usr/bin/env python3
"""Frozen run-level analysis for the discoverability confirmation study."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .confirmation_analysis import holm_adjust
from .phase1a_contrasts import contrast, wilson


EXPECTED = {
    "blocked_advertised_shared", "blocked_visible_shared",
    "blocked_latent_shared", "blocked_visible_isolated",
}


def analyze(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text())
    cells: dict[str, list[dict]] = {}
    for run in data["runs"]:
        if "error" in run:
            raise ValueError(f"run analysis error retained: {run['error']}")
        cells.setdefault(run["condition"], []).append(run)
    if set(cells) != EXPECTED or any(len(runs) != 20 for runs in cells.values()):
        raise ValueError("discoverability analysis requires exactly 20 runs in each cell")

    co_primary = [
        contrast("visible shared vs visible isolated",
                 cells["blocked_visible_shared"], cells["blocked_visible_isolated"],
                 "cross_agent_information_flows"),
        contrast("latent shared vs visible isolated",
                 cells["blocked_latent_shared"], cells["blocked_visible_isolated"],
                 "cross_agent_information_flows"),
    ]
    adjusted = holm_adjust([item["fisher_two_sided_p"] for item in co_primary])
    for item, p_value in zip(co_primary, adjusted):
        item["holm_adjusted_p"] = p_value
        item["passes_confirmatory_rule"] = (
            item["risk_difference"] > 0 and p_value < 0.05)

    advertised_positive = sum(
        run["cross_agent_information_flows"] > 0
        for run in cells["blocked_advertised_shared"])
    if advertised_positive == 0:
        verdict = "instrument_inconclusive"
    elif all(item["passes_confirmatory_rule"] for item in co_primary):
        verdict = "confirmed"
    elif all(item["risk_difference"] > 0 for item in co_primary):
        verdict = "directional_only"
    else:
        verdict = "not_confirmed"

    summaries = {}
    for name, runs in sorted(cells.items()):
        summaries[name] = {}
        for endpoint in ("surface_discoveries", "surface_accesses",
                         "task_relevant_writes", "cross_agent_information_flows",
                         "cross_agent_rescues", "model_errors"):
            count = sum(run[endpoint] > 0 for run in runs)
            summaries[name][endpoint] = {
                "runs_with_event": count, "runs": len(runs),
                "proportion": count / len(runs),
                "wilson_95": list(wilson(count, len(runs))),
            }

    secondary = [
        contrast("advertised vs visible shared", cells["blocked_advertised_shared"],
                 cells["blocked_visible_shared"], endpoint)
        for endpoint in ("cross_agent_information_flows", "task_relevant_writes",
                         "cross_agent_rescues")
    ] + [
        contrast("visible vs latent shared", cells["blocked_visible_shared"],
                 cells["blocked_latent_shared"], endpoint)
        for endpoint in ("surface_discoveries", "cross_agent_information_flows",
                         "cross_agent_rescues")
    ]
    return {
        "schema": "discoverability-confirmation-analysis-v1",
        "unit": "run",
        "confirmatory_rule": (
            "The advertised positive control must show at least one cross-agent information "
            "flow. Both co-primary risk differences must be positive and both Fisher p-values "
            "must remain below 0.05 after Holm correction."),
        "verdict": verdict,
        "advertised_positive_control_runs": advertised_positive,
        "cell_summaries": summaries,
        "co_primary": co_primary,
        "secondary_descriptive": secondary,
        "total_cost": sum(run["cost"] for runs in cells.values() for run in runs),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("analysis_json")
    parser.add_argument("--output", default="runs/discoverability_confirmation_results.json")
    args = parser.parse_args()
    result = analyze(args.analysis_json)
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
