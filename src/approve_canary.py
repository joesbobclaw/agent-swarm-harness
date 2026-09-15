#!/usr/bin/env python3
"""Create the mechanical gate receipt after an excluded canary verifies."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

try:
    from .evidence import git_commit, sha256_file, write_json
    from .verify_run import verify_db
except ImportError:
    from evidence import git_commit, sha256_file, write_json
    from verify_run import verify_db


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("db", help="excluded Phase 1 canary database")
    parser.add_argument("--output", default="evidence/phase1a-canary-pass.json")
    args = parser.parse_args()
    db = Path(args.db).resolve()
    repo = Path(__file__).resolve().parent.parent
    ok, report = verify_db(str(db))
    if not ok:
        raise SystemExit("Canary verification failed; no gate receipt written.")
    meta = report["runs"][0]
    run_id = meta["run_id"]
    if "canary" not in run_id:
        raise SystemExit("Refusing to approve a run not explicitly labeled canary.")
    receipt = {
        "schema": "swarm-study-canary-pass-v1",
        "verified": True,
        "canary_run_id": run_id,
        "canary_db_sha256": sha256_file(db),
        "instrument_commit": git_commit(repo),
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }
    output = repo / args.output
    write_json(output, receipt)
    print(output)


if __name__ == "__main__":
    main()
