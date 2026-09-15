#!/usr/bin/env python3
"""Independent verifier for swarm run databases.

Usage:
    python3 src/verify_run.py runs/<file>.db [more.db ...]

Checks, per run:
  1. Event-chain integrity: recomputed content hashes + chain linkage
  2. Run metadata completeness: status, cost, agent count, turns
  3. Cost accounting: sum of logged turn costs vs recorded total
  4. Termination accounting: every agent ends with task_solved,
     agent_terminated, or agent_error — no silent endings
  5. Credential-leakage scan: API-key-shaped strings in any event payload

Exit code 0 = all checks pass; 1 = any failure.
This script computes facts only. It performs no analysis and makes no
interpretation. Analysis lives in analyze.py.
"""

import json
import re
import sys
from pathlib import Path

try:
    from .event_store import EventStore
    from .evidence import sha256_file, verify_signature
except ImportError:
    from event_store import EventStore
    from evidence import sha256_file, verify_signature

# Patterns that should NEVER appear in event payloads of a closed-world run.
LEAK_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),                      # OpenAI-style keys
    re.compile(r"b10n_[A-Za-z0-9\-_]{16,}"),                 # Baseten keys
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),                     # GitHub PATs
    re.compile(r"AKIA[0-9A-Z]{16}"),                         # AWS access keys
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),       # PEM blocks
    re.compile(r"API_KEY\s*[=:]\s*['\"][^'\"]{8,}['\"]"),    # inline key assignments
]


def check_leakage(events: list[dict]) -> list[dict]:
    hits = []
    for e in events:
        payload = e.get("data_json") or ""
        for pat in LEAK_PATTERNS:
            m = pat.search(payload)
            if m:
                hits.append({
                    "event_id": e["id"],
                    "pattern": pat.pattern,
                    "preview": m.group(0)[:12] + "...",
                })
                break  # one hit per event is enough to flag it
    return hits


def check_termination(events: list[dict]) -> dict:
    """Every agent must end with an explicit outcome event."""
    agents = sorted({e["agent_id"] for e in events if e["agent_id"] != "environment"})
    endings = {}
    for a in agents:
        evs = [e["event_type"] for e in events if e["agent_id"] == a]
        if "task_solved" in evs:
            endings[a] = "solved"
        elif "agent_error" in evs:
            endings[a] = "error"
        elif "agent_terminated" in evs:
            endings[a] = "terminated"
        elif "budget_exhausted" in evs:
            endings[a] = "budget"
        else:
            endings[a] = "UNDECLARED"
    return endings


def check_evidence(db_path: str, run_id: str, meta: dict, chain: dict) -> dict:
    """Verify released v2 DB against its signed completion manifest."""
    recorded_config = json.loads(meta.get("config_json") or "{}")
    task_config = recorded_config.get("task", recorded_config.get("config", {}))
    if (int(meta.get("schema_version") or 1) < 2 or
            task_config.get("type") != "neutral_puzzle"):
        return {"pass": True, "detail": {"legacy": True}}
    root = Path(db_path).resolve().parent.parent
    manifest_path = root / "evidence" / "completion" / f"{run_id}.json"
    signature_path = manifest_path.with_suffix(".signature.json")
    anchor_request_path = manifest_path.with_suffix(".anchor-request.txt")
    anchor_receipt_path = manifest_path.with_suffix(".anchor-receipt.json")
    prerun_path = root / "evidence" / "prerun" / f"{run_id}.json"
    missing = [str(p) for p in (manifest_path, signature_path, prerun_path,
                                anchor_request_path) if not p.exists()]
    if missing:
        return {"pass": False, "detail": {"missing": missing}}
    manifest = json.loads(manifest_path.read_text())
    signature = json.loads(signature_path.read_text())
    failures = []
    if manifest.get("run_id") != run_id: failures.append("run_id")
    if manifest.get("db_sha256") != sha256_file(db_path): failures.append("db_sha256")
    if manifest.get("final_chain_head") != meta.get("final_chain_head"):
        failures.append("final_chain_head_metadata")
    if manifest.get("final_chain_head") != chain.get("head"):
        failures.append("final_chain_head_computed")
    if manifest.get("prerun_manifest_sha256") != sha256_file(prerun_path):
        failures.append("prerun_manifest_sha256")
    if meta.get("manifest_hash") != manifest.get("prerun_manifest_sha256"):
        failures.append("prerun_manifest_metadata")
    if not verify_signature(manifest, signature): failures.append("signature")
    request_parts = anchor_request_path.read_text().strip().split()
    if not request_parts or request_parts[-1] != signature.get("manifest_sha256"):
        failures.append("anchor_request")
    if recorded_config.get("collection_status") == "frozen":
        if not anchor_receipt_path.exists():
            failures.append("anchor_receipt_missing")
        else:
            receipt = json.loads(anchor_receipt_path.read_text())
            if receipt.get("manifest_sha256") != signature.get("manifest_sha256"):
                failures.append("anchor_receipt_digest")
            if not receipt.get("anchor_uri") or not receipt.get("anchored_at"):
                failures.append("anchor_receipt_incomplete")
    return {"pass": not failures, "detail": {"failures": failures,
                                               "manifest": str(manifest_path)}}


def verify_db(db_path: str) -> tuple[bool, dict]:
    store = EventStore(db_path, read_only=True)
    try:
        report = {"db": db_path, "runs": [], "pass": True}

        runs = [dict(r) for r in
                store.conn.execute("SELECT * FROM run_metadata").fetchall()]
        if not runs:
            report["pass"] = False
            report["runs"].append({"error": "no run_metadata rows"})
            return False, report

        for meta in runs:
            run_id = meta["run_id"]
            events = [dict(r) for r in store.conn.execute(
                "SELECT * FROM events WHERE run_id = ? ORDER BY id ASC",
                (run_id,)).fetchall()]

            r = {
                "run_id": run_id,
                "status": meta["status"],
                "events": len(events),
                "checks": {},
            }

            # 1. chain integrity
            chain = store.verify_chain(run_id)
            chain["head"] = store.chain_head(run_id)
            r["checks"]["chain"] = {
                "pass": not chain["breaks"] and chain["verified"] == chain["total"],
                "detail": chain,
            }

            # 2. metadata completeness
            meta_ok = (
                meta["status"] in ("completed", "halted")
                and meta["end_time"] is not None
                and meta["agent_count"] is not None
                and meta["total_turns"] is not None
            )
            r["checks"]["metadata"] = {"pass": bool(meta_ok), "detail": {
                "status": meta["status"],
                "end_time": meta["end_time"],
                "agent_count": meta["agent_count"],
                "total_turns": meta["total_turns"],
            }}

            # 3. cost accounting
            turn_costs = []
            for e in events:
                if e["event_type"] == "model_response" and e["data_json"]:
                    d = json.loads(e["data_json"])
                    if "turn_cost" in d:
                        turn_costs.append(d["turn_cost"])
            summed = sum(turn_costs)
            recorded = meta["total_cost"] or 0.0
            cost_ok = abs(summed - recorded) < 1e-6 and summed >= 0
            r["checks"]["cost"] = {
                "pass": bool(cost_ok),
                "detail": {
                    "sum_of_turn_costs": round(summed, 9),
                    "recorded_total": round(recorded, 9),
                    "turns_with_cost": len(turn_costs),
                },
            }

            # 4. termination accounting
            endings = check_termination(events)
            undeclared = [a for a, v in endings.items() if v == "UNDECLARED"]
            r["checks"]["termination"] = {
                "pass": not undeclared,
                "detail": {"endings": endings, "undeclared": undeclared},
            }

            # 5. leakage scan
            leaks = check_leakage(events)
            r["checks"]["leakage"] = {
                "pass": not leaks,
                "detail": {"hits": leaks},
            }

            # 6. released evidence, DB digest, pre-run manifest, and signature
            r["checks"]["evidence"] = check_evidence(db_path, run_id, meta, chain)

            run_pass = all(c["pass"] for c in r["checks"].values())
            r["pass"] = run_pass
            report["runs"].append(r)
            if not run_pass:
                report["pass"] = False

        return report["pass"], report
    finally:
        store.close()


def main():
    paths = []
    for arg in sys.argv[1:]:
        p = Path(arg)
        if p.is_dir():
            paths.extend(sorted(p.glob("*.db")))
        elif p.is_file():
            paths.append(p)
        else:
            print(f"not found: {arg}", file=sys.stderr)
            sys.exit(2)
    if not paths:
        print("usage: python3 src/verify_run.py runs/<file>.db [...]", file=sys.stderr)
        sys.exit(2)

    all_ok = True
    for path in paths:
        ok, report = verify_db(str(path))
        all_ok &= ok
        tag = "PASS" if ok else "FAIL"
        print(f"[{tag}] {path}")
        for r in report["runs"]:
            if "error" in r:
                print(f"    error: {r['error']}")
                continue
            for name, c in r["checks"].items():
                mark = "ok" if c["pass"] else "FAIL"
                print(f"    {name:>12}: {mark}")
                if not c["pass"]:
                    print(f"      {json.dumps(c['detail'])[:400]}")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
