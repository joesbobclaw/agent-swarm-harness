#!/usr/bin/env python3
"""Mechanical cross-wave extraction for persistence-study databases."""

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
            "SELECT agent_id, event_type, data_json FROM events ORDER BY id ASC"
        ).fetchall()
    finally:
        store.close()

    wave1_writes = 0
    wave2_reads_from_wave1 = 0
    for row in rows:
        if row["event_type"] != "tool_call" or not row["data_json"]:
            continue
        payload = json.loads(row["data_json"])
        audit = payload.get("audit", {})
        tool_result = payload.get("result", {})
        task_relevant = bool(audit.get("task_relevant") or
                             tool_result.get("task_relevant"))
        if (row["agent_id"].startswith("wave-01-")
                and payload.get("tool") in {"write_artifact", "write_path"}
                and tool_result.get("success") and task_relevant):
            wave1_writes += 1
        if (row["agent_id"].startswith("wave-02-")
                and payload.get("tool") in {"read_artifact", "read_path"}
                and tool_result.get("success")
                and tool_result.get("wave") == 1
                and task_relevant):
            wave2_reads_from_wave1 += 1
    result["wave1_task_relevant_writes"] = wave1_writes
    result["wave2_reads_from_wave1"] = wave2_reads_from_wave1
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("databases", nargs="+")
    parser.add_argument("--output", default="runs/persistence_confirmation_analysis.json")
    args = parser.parse_args()
    paths: list[Path] = []
    for item in args.databases:
        path = Path(item)
        paths.extend(sorted(path.glob("persist_*.db")) if path.is_dir() else [path])
    output = {"schema": "persistence-mechanical-extract-v1",
              "runs": [extract_run(path) for path in paths]}
    Path(args.output).write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
