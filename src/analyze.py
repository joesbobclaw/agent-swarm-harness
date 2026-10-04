#!/usr/bin/env python3
"""Pre-committed mechanical analysis for swarm run databases.

Usage:
    python3 src/analyze.py runs/<file>.db [more.db ...]
    python3 src/analyze.py runs/            # all .db files in a directory

For each run database this computes, mechanically and without judgment:
  - condition, seed, agent count
  - solved agents (distinct agents with verified task_solved events)
  - artifact writes / reads (from tool_call events)
  - undocumented-store writes (shared store, explicit_mailbox = False)
  - coordinating agents (distinct agents that wrote)
  - first write turn
  - overseer reports, solution claims, rejected claims
  - termination reasons, model errors
  - cost (recorded), chain integrity

Outputs a printed table and a JSON file. Run-level unit of analysis.
Agents are nested within runs and are never treated as independent
replications. This script computes facts only; interpretation is the
paper's job.
"""

import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

try:
    from .event_store import EventStore
except ImportError:
    from event_store import EventStore


def analyze_run(db_path: str) -> dict:
    store = EventStore(db_path, read_only=True)
    try:
        metas = [dict(r) for r in store.conn.execute(
            "SELECT * FROM run_metadata").fetchall()]
        if not metas:
            return {"db": db_path, "error": "no run_metadata"}
        meta = metas[0]
        run_id = meta["run_id"]

        events = [dict(r) for r in store.conn.execute(
            "SELECT * FROM events WHERE run_id = ? ORDER BY id ASC",
            (run_id,)).fetchall()]

        tool_calls = []
        for e in events:
            if e["event_type"] == "tool_call" and e["data_json"]:
                d = json.loads(e["data_json"])
                d["_turn"] = e["turn"]
                d["_agent"] = e["agent_id"]
                tool_calls.append(d)

        write_attempts = [t for t in tool_calls if t.get("tool") == "write_artifact"]
        read_attempts = [t for t in tool_calls if t.get("tool") == "read_artifact"]
        writes = [t for t in write_attempts if t.get("result", {}).get("success")]
        reads = [t for t in read_attempts if t.get("result", {}).get("success")]
        submits = [t for t in tool_calls if t.get("tool") in
                   {"submit_solution", "submit_answer"}]
        overseer = [t for t in tool_calls
                    if t.get("tool") == "report_to_overseer"]

        solved_agents = sorted({e["agent_id"] for e in events
                                if e["event_type"] == "task_solved"})
        rejected_claims = sum(1 for e in events
                              if e["event_type"] == "solution_claim_rejected")
        model_errors = sum(1 for e in events
                           if e["event_type"] == "model_error")
        solved_payloads = [json.loads(e["data_json"]) for e in events
                           if e["event_type"] == "task_solved"]
        relevant_writes = [t for t in writes
                           if t.get("audit", {}).get("task_relevant") or
                           t.get("result", {}).get("task_relevant")]
        policy_violations = [t for t in writes
                             if t.get("audit", {}).get("policy_violation") or
                             t.get("result", {}).get("policy_violation")]
        rescues = [d for d in solved_payloads if d.get("cross_agent_rescue")]
        seeded_rescues = [d for d in solved_payloads if d.get("seeded_rescue")]
        seeded_reads = [t for t in reads
                        if t.get("result", {}).get("author") == "seed-agent"]
        wave2_from_wave1 = [d for d in rescues if d.get("wave") == 2 and any(
            r.get("wave") == 1 for r in d.get("qualifying_reads", []))]

        term_reasons = defaultdict(int)
        for e in events:
            if e["event_type"] == "agent_terminated" and e["data_json"]:
                d = json.loads(e["data_json"])
                term_reasons[d.get("reason", "unknown")] += 1

        # Condition flags come from the run's own recorded config.
        cond = {}
        if meta.get("config_json"):
            cfg = json.loads(meta["config_json"])
            cond = cfg.get("condition", {})
        shared = bool(cond.get("shared_artifact_store", False))
        documented = bool(cond.get("explicit_mailbox", False))
        store_policy = cond.get("store_policy")
        if store_policy is None:
            store_policy = "absent" if not shared else ("permitted" if documented else "ambiguous")

        chain = store.verify_chain(run_id)

        return {
            "db": db_path,
            "run_id": run_id,
            "condition": cond.get("name", events[0]["condition"] if events else "?"),
            "shared_store": shared,
            "documented_shared": documented,
            "undocumented_shared": shared and not documented,
            "feasibility": cond.get("feasibility"),
            "store_policy": store_policy,
            "store_initialization": cond.get("store_initialization", "empty"),
            "tool_interface": cond.get("tool_interface", "textual"),
            "seed": events[0]["seed"] if events else None,
            "status": meta["status"],
            "agents": meta["agent_count"],
            "turns": meta["total_turns"],
            "solved_agents": len(solved_agents),
            "solved_agent_ids": solved_agents,
            "artifact_writes": len(writes),
            "artifact_write_attempts": len(write_attempts),
            "writing_agents": len({t["_agent"] for t in writes}),
            "first_write_turn": min((t["_turn"] for t in writes), default=None),
            "artifact_reads": len(reads),
            "artifact_read_attempts": len(read_attempts),
            "task_relevant_writes": len(relevant_writes),
            "policy_violation_writes": len(policy_violations),
            "intended_path_successes": sum(bool(d.get("intended_path_success")) for d in solved_payloads),
            "unintended_path_successes": sum(bool(d.get("unintended_path_success")) for d in solved_payloads),
            "cross_agent_rescues": len(rescues),
            "seeded_rescues": len(seeded_rescues),
            "seeded_artifact_reads": len(seeded_reads),
            "wave2_success_from_wave1": len(wave2_from_wave1),
            "overseer_reports": len(overseer),
            "solution_claims": len(submits),
            "rejected_claims": rejected_claims,
            "model_errors": model_errors,
            "termination_reasons": dict(term_reasons),
            "cost": meta["total_cost"],
            "chain_ok": not chain["breaks"] and chain["verified"] == chain["total"],
        }
    finally:
        store.close()


def aggregate(runs: list[dict]) -> dict:
    by_cond = defaultdict(list)
    for r in runs:
        by_cond[r["condition"]].append(r)

    out = {}
    for cond, rs in sorted(by_cond.items()):
        n = len(rs)
        out[cond] = {
            "runs": n,
            "total_agents": sum(r["agents"] for r in rs),
            "total_solved_agents": sum(r["solved_agents"] for r in rs),
            "runs_with_solution": sum(1 for r in rs if r["solved_agents"] > 0),
            "mean_writes_per_run": round(
                sum(r["artifact_writes"] for r in rs) / n, 2),
            "total_undocumented_shared_writes": sum(
                r["artifact_writes"] for r in rs if r["undocumented_shared"]),
            "total_artifact_reads": sum(r["artifact_reads"] for r in rs),
            "total_task_relevant_writes": sum(r["task_relevant_writes"] for r in rs),
            "runs_with_task_relevant_write": sum(1 for r in rs if r["task_relevant_writes"]),
            "total_policy_violation_writes": sum(r["policy_violation_writes"] for r in rs),
            "total_cross_agent_rescues": sum(r["cross_agent_rescues"] for r in rs),
            "runs_with_cross_agent_rescue": sum(1 for r in rs if r["cross_agent_rescues"]),
            "wave2_success_from_wave1": sum(r["wave2_success_from_wave1"] for r in rs),
            "runs_with_reads": sum(1 for r in rs if r["artifact_reads"] > 0),
            "total_rejected_claims": sum(r["rejected_claims"] for r in rs),
            "total_model_errors": sum(r["model_errors"] for r in rs),
            "mean_cost_per_run": round(
                sum(r["cost"] for r in rs) / n, 6),
            "all_chains_ok": all(r["chain_ok"] for r in rs),
        }
    return out


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
        print("usage: python3 src/analyze.py runs/<file>.db [...]", file=sys.stderr)
        sys.exit(2)

    runs = []
    for p in paths:
        try:
            runs.append(analyze_run(str(p)))
        except Exception as e:
            runs.append({"db": str(p), "error": str(e)})

    ok_runs = [r for r in runs if "error" not in r]
    bad_runs = [r for r in runs if "error" in r]

    print(f"{'condition':<18} {'seed':>4} {'ag':>3} {'solv':>4} {'wr':>4} "
          f"{'rd':>4} {'1stT':>4} {'ovs':>3} {'clm':>3} {'rej':>3} "
          f"{'err':>3} {'cost':>9} chain")
    for r in ok_runs:
        print(f"{r['condition']:<18} {str(r['seed']):>4} {r['agents']:>3} "
              f"{r['solved_agents']:>4} {r['artifact_writes']:>4} "
              f"{r['artifact_reads']:>4} "
              f"{str(r['first_write_turn'] or '-'):>4} "
              f"{r['overseer_reports']:>3} {r['solution_claims']:>3} "
              f"{r['rejected_claims']:>3} {r['model_errors']:>3} "
              f"{r['cost']:>9.6f} {'ok' if r['chain_ok'] else 'BROKEN'}")

    agg = aggregate(ok_runs)
    print("\n=== Per-condition aggregates (run-level unit) ===")
    for cond, a in agg.items():
        print(f"{cond}: {json.dumps(a)}")

    if bad_runs:
        print("\n=== Runs with errors (reported, never silently dropped) ===")
        for r in bad_runs:
            print(f"{r['db']}: {r['error']}")

    out_path = Path(ok_runs[0]["db"]).parent if ok_runs else Path("runs")
    out_file = out_path / f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_file, "w") as f:
        json.dump({"runs": runs, "aggregates": agg}, f, indent=2)
    print(f"\nAnalysis written to {out_file}")


if __name__ == "__main__":
    main()
