#!/usr/bin/env python3
"""Approve the excluded persistence canary only after both fresh waves solve."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .approve_canary import check_canary_semantics
from .event_store import EventStore
from .evidence import git_commit, sha256_file, write_json
from .verify_run import verify_db


def wave_checks(db: Path) -> dict:
    store = EventStore(str(db), read_only=True)
    try:
        events = [dict(row) for row in store.conn.execute(
            "SELECT agent_id, event_type, data_json FROM events ORDER BY id")]
    finally:
        store.close()
    started = set()
    solved = set()
    for event in events:
        if event["event_type"] == "wave_started":
            started.add(json.loads(event["data_json"] or "{}").get("wave"))
        elif event["event_type"] == "task_solved":
            if event["agent_id"].startswith("wave-01-"):
                solved.add(1)
            elif event["agent_id"].startswith("wave-02-"):
                solved.add(2)
    return {"waves_started": sorted(w for w in started if w is not None),
            "waves_solved": sorted(solved),
            "pass": started == {1, 2} and solved == {1, 2}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("db")
    parser.add_argument("--output", default="evidence/persistence-confirmation-canary-pass.json")
    parser.add_argument("--expected-model", required=True)
    args = parser.parse_args()
    db = Path(args.db).resolve()
    repo = Path(__file__).resolve().parent.parent
    ok, report = verify_db(str(db))
    semantic = check_canary_semantics(
        db, expected_model=args.expected_model, expected_tool_interface="textual")
    waves = wave_checks(db)
    if not ok or not semantic["pass"] or not waves["pass"]:
        raise SystemExit("Persistence canary failed; no receipt written: " + json.dumps({
            "evidence_ok": ok, "semantic": semantic, "waves": waves}, sort_keys=True))
    run_id = report["runs"][0]["run_id"]
    if "canary" not in run_id:
        raise SystemExit("Refusing to approve a run not explicitly labeled canary.")
    receipt = {
        "schema": "swarm-study-canary-pass-v1",
        "verified": True,
        "canary_run_id": run_id,
        "canary_db_sha256": sha256_file(db),
        "instrument_commit": git_commit(repo),
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "semantic_gate": semantic,
        "wave_gate": waves,
    }
    output = repo / args.output
    write_json(output, receipt)
    print(output)


if __name__ == "__main__":
    main()
