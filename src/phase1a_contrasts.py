#!/usr/bin/env python3
"""Post-study reporting contrasts for the sealed Phase 1A pilot.

Uses run-level binary endpoints, Wilson score intervals for proportions,
Newcombe-style intervals for risk differences, and two-sided Fisher exact
tests. The preregistered emphasis remains effect direction and size.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


Z95 = 1.959963984540054


def wilson(successes: int, total: int) -> tuple[float, float]:
    if total <= 0:
        return (float("nan"), float("nan"))
    p = successes / total
    z2 = Z95 * Z95
    denominator = 1 + z2 / total
    center = (p + z2 / (2 * total)) / denominator
    radius = Z95 * math.sqrt((p * (1 - p) + z2 / (4 * total)) / total) / denominator
    return (max(0.0, center - radius), min(1.0, center + radius))


def fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    row1, row2 = a + b, c + d
    col1 = a + c
    total = row1 + row2

    def probability(x: int) -> float:
        return (math.comb(col1, x) * math.comb(total - col1, row1 - x)
                / math.comb(total, row1))

    low = max(0, row1 - (total - col1))
    high = min(row1, col1)
    observed = probability(a)
    return min(1.0, sum(probability(x) for x in range(low, high + 1)
                        if probability(x) <= observed + 1e-12))


def endpoint_count(runs: list[dict], endpoint: str) -> tuple[int, int]:
    return sum(int(run[endpoint] > 0) for run in runs), len(runs)


def contrast(name: str, first: list[dict], second: list[dict], endpoint: str) -> dict:
    x1, n1 = endpoint_count(first, endpoint)
    x0, n0 = endpoint_count(second, endpoint)
    p1, p0 = x1 / n1, x0 / n0
    l1, u1 = wilson(x1, n1)
    l0, u0 = wilson(x0, n0)
    difference = p1 - p0
    difference_low = difference - math.sqrt((p1 - l1) ** 2 + (u0 - p0) ** 2)
    difference_high = difference + math.sqrt((u1 - p1) ** 2 + (p0 - l0) ** 2)
    return {
        "name": name,
        "endpoint": endpoint,
        "first": {"successes": x1, "runs": n1, "proportion": p1,
                  "wilson_95": [l1, u1]},
        "second": {"successes": x0, "runs": n0, "proportion": p0,
                   "wilson_95": [l0, u0]},
        "risk_difference": difference,
        "risk_difference_newcombe_95": [max(-1.0, difference_low),
                                         min(1.0, difference_high)],
        "fisher_two_sided_p": fisher_two_sided(x1, n1 - x1, x0, n0 - x0),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("analysis_json")
    parser.add_argument("--output", default="runs/phase1a_contrasts.json")
    args = parser.parse_args()
    data = json.loads(Path(args.analysis_json).read_text())
    by_condition: dict[str, list[dict]] = {}
    for run in data["runs"]:
        by_condition.setdefault(run["condition"], []).append(run)

    definitions = [
        ("blocked vs solvable within ambiguous",
         by_condition["blocked_ambiguous"], by_condition["solvable_ambiguous"]),
        ("ambiguous vs prohibited within blocked",
         by_condition["blocked_ambiguous"], by_condition["blocked_prohibited"]),
        ("permitted vs ambiguous within blocked",
         by_condition["blocked_permitted"], by_condition["blocked_ambiguous"]),
        ("pooled available stores vs absent within blocked",
         by_condition["blocked_permitted"] + by_condition["blocked_ambiguous"]
         + by_condition["blocked_prohibited"], by_condition["blocked_absent"]),
    ]
    endpoints = ["task_relevant_writes", "cross_agent_rescues"]
    output = {
        "schema": "phase1a-reporting-contrasts-v1",
        "unit": "run",
        "intervals": "Wilson score for proportions; Newcombe difference from Wilson bounds",
        "tests": "two-sided Fisher exact; descriptive for this pilot",
        "contrasts": [contrast(name, first, second, endpoint)
                      for name, first, second in definitions for endpoint in endpoints],
    }
    Path(args.output).write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
