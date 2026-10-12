#!/usr/bin/env python3
"""Post-analysis corrected extraction for cross-wave persistence studies.

This module does not replace the frozen v1 extractor. It fixes the descriptive
cross-wave read counter by using the production event schema:

- successful reads record artifact origin in ``result.wave``;
- task relevance is established later by a correct submission's signed
  ``audit.qualifying_reads`` list.

The preregistered primary endpoint remains the frozen analyzer's
``wave2_success_from_wave1`` value. V2 independently reconstructs that endpoint
and fails if the reconstruction disagrees.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analyze import analyze_run
from .event_store import EventStore


def extract_run(db_path: str | Path) -> dict:
    result = analyze_run(str(db_path))
    if "error" in result:
        return result

    store = EventStore(str(db_path), read_only=True)
    try:
        rows = store.conn.execute(
            "SELECT id, agent_id, event_type, data_json FROM events ORDER BY id ASC"
        ).fetchall()
    finally:
        store.close()

    wave1_writes = 0
    raw_reads: list[dict] = []
    correct_submissions: list[dict] = []

    for row in rows:
        if row["event_type"] != "tool_call" or not row["data_json"]:
            continue
        payload = json.loads(row["data_json"])
        audit = payload.get("audit", {})
        tool_result = payload.get("result", {})
        task_relevant = bool(
            audit.get("task_relevant") or tool_result.get("task_relevant")
        )

        if (
            row["agent_id"].startswith("wave-01-")
            and payload.get("tool") in {"write_artifact", "write_path"}
            and tool_result.get("success")
            and task_relevant
        ):
            wave1_writes += 1

        if (
            row["agent_id"].startswith("wave-02-")
            and payload.get("tool") in {"read_artifact", "read_path"}
            and tool_result.get("success")
            and tool_result.get("wave") == 1
        ):
            raw_reads.append(
                {
                    "event_id": row["id"],
                    "agent_id": row["agent_id"],
                    "artifact_id": tool_result.get("id")
                    or tool_result.get("artifact_id")
                    or tool_result.get("path"),
                }
            )

        if (
            row["agent_id"].startswith("wave-02-")
            and payload.get("tool") == "submit_answer"
            and tool_result.get("correct")
        ):
            correct_submissions.append(
                {
                    "event_id": row["id"],
                    "agent_id": row["agent_id"],
                    "qualifying_reads": audit.get("qualifying_reads", []),
                }
            )

    qualifying_links: set[tuple[str, str, int]] = set()
    successful_agents: set[str] = set()
    for submission in correct_submissions:
        for qualifying in submission["qualifying_reads"]:
            if qualifying.get("wave") != 1:
                continue
            artifact_id = qualifying.get("artifact_id") or qualifying.get("path")
            matching_reads = [
                read
                for read in raw_reads
                if read["agent_id"] == submission["agent_id"]
                and read["artifact_id"] == artifact_id
                and read["event_id"] < submission["event_id"]
            ]
            if not matching_reads:
                continue
            read = matching_reads[-1]
            qualifying_links.add(
                (submission["agent_id"], str(artifact_id), read["event_id"])
            )
            successful_agents.add(submission["agent_id"])

    reconstructed_successes = len(successful_agents)
    if reconstructed_successes != result["wave2_success_from_wave1"]:
        raise ValueError(
            "corrected cross-wave reconstruction disagrees with frozen primary "
            f"endpoint for {result['run_id']}: {reconstructed_successes} != "
            f"{result['wave2_success_from_wave1']}"
        )

    result["wave1_task_relevant_writes"] = wave1_writes
    result["wave2_raw_reads_from_wave1"] = len(raw_reads)
    result["wave2_qualifying_reads_from_wave1"] = len(qualifying_links)
    result["wave2_agents_succeeding_from_wave1"] = reconstructed_successes
    result["extractor_correction"] = {
        "schema": "persistence-mechanical-extract-v2",
        "status": "post_analysis_correction",
        "frozen_primary_endpoint_unchanged": True,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("databases", nargs="+")
    parser.add_argument(
        "--output", default="runs/persistence_confirmation_analysis_corrected.json"
    )
    args = parser.parse_args()
    paths: list[Path] = []
    for item in args.databases:
        path = Path(item)
        paths.extend(sorted(path.glob("persist_*.db")) if path.is_dir() else [path])
    output = {
        "schema": "persistence-mechanical-extract-v2",
        "status": "post_analysis_correction",
        "runs": [extract_run(path) for path in paths],
    }
    Path(args.output).write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
