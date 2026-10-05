#!/usr/bin/env python3
"""Approve the excluded discoverability canary only after it uses the new surface."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .approve_canary import check_canary_semantics
from .event_store import EventStore
from .evidence import git_commit, sha256_file, write_json
from .verify_run import verify_db


GENERIC_TOOLS = {"list_directory", "read_path", "write_path"}


def successful_generic_calls(db: Path) -> list[str]:
    store = EventStore(str(db), read_only=True)
    try:
        calls = []
        for row in store.conn.execute(
                "SELECT data_json FROM events WHERE event_type='tool_call' ORDER BY id"):
            data = json.loads(row["data_json"] or "{}")
            if (data.get("tool") in GENERIC_TOOLS
                    and data.get("result", {}).get("success") is True):
                calls.append(data["tool"])
        return calls
    finally:
        store.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("db")
    parser.add_argument("--output", default="evidence/discoverability-confirmation-canary-pass.json")
    parser.add_argument("--expected-model", required=True)
    args = parser.parse_args()
    db = Path(args.db).resolve()
    repo = Path(__file__).resolve().parent.parent
    ok, report = verify_db(str(db))
    semantic = check_canary_semantics(
        db, expected_model=args.expected_model, expected_tool_interface="textual")
    generic_calls = successful_generic_calls(db)
    if not ok or not semantic["pass"] or not generic_calls:
        raise SystemExit("Discoverability canary failed; no receipt written: " + json.dumps({
            "evidence_ok": ok, "semantic": semantic, "generic_calls": generic_calls,
        }, sort_keys=True))
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
        "successful_generic_filesystem_calls": generic_calls,
    }
    output = repo / args.output
    write_json(output, receipt)
    print(output)


if __name__ == "__main__":
    main()
