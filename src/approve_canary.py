#!/usr/bin/env python3
"""Create the mechanical gate receipt after an excluded canary verifies."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

try:
    from .event_store import EventStore
    from .evidence import git_commit, sha256_file, write_json
    from .verify_run import verify_db
except ImportError:
    from event_store import EventStore
    from evidence import git_commit, sha256_file, write_json
    from verify_run import verify_db


def check_canary_semantics(db: Path, expected_model: str | None = None,
                           require_response_model: bool = False,
                           expected_response_model: str | None = None,
                           expected_tool_interface: str | None = None) -> dict:
    """Require a real, paid model path ending in a verified correct submission."""
    store = EventStore(str(db), read_only=True)
    try:
        metas = [dict(row) for row in store.conn.execute(
            "SELECT * FROM run_metadata").fetchall()]
        if len(metas) != 1:
            return {"pass": False, "failures": ["exactly_one_run_required"]}
        meta = metas[0]
        events = [dict(row) for row in store.conn.execute(
            "SELECT * FROM events WHERE run_id = ? ORDER BY id ASC",
            (meta["run_id"],)).fetchall()]
    finally:
        store.close()

    responses = [event for event in events if event["event_type"] == "model_response"]
    errors = [event for event in events if event["event_type"] == "model_error"]
    solved = [event for event in events if event["event_type"] == "task_solved"]
    successful_submits = []
    for event in events:
        if event["event_type"] != "tool_call" or not event.get("data_json"):
            continue
        data = json.loads(event["data_json"])
        if (data.get("tool") in {"submit_answer", "submit_solution"}
                and data.get("result", {}).get("correct") is True):
            successful_submits.append(event)
    ordered_success = any(
        submit["agent_id"] == solution["agent_id"] and submit["id"] < solution["id"]
        for submit in successful_submits for solution in solved)
    response_cost = sum(
        json.loads(event["data_json"]).get("turn_cost", 0.0)
        for event in responses if event.get("data_json"))
    observed_models = {event.get("model") for event in responses if event.get("model")}
    response_model_values = [
        json.loads(event["data_json"]).get("response_model")
        for event in responses if event.get("data_json")
    ]
    response_models = {value for value in response_model_values if value}
    response_payloads = [json.loads(event["data_json"]) for event in responses
                         if event.get("data_json")]
    observed_interfaces = {
        payload.get("tool_interface") for payload in response_payloads
        if payload.get("tool_interface")}
    native_calls = [payload.get("native_tool_call") for payload in response_payloads
                    if payload.get("native_tool_call")]

    checks = {
        "completed": meta.get("status") == "completed",
        "real_model_response": bool(responses),
        "nonzero_cost": response_cost > 0 and (meta.get("total_cost") or 0) > 0,
        "no_model_error": not errors,
        "correct_submit_before_solution": ordered_success,
        "expected_model": expected_model is None or observed_models == {expected_model},
        "response_model_recorded": (
            not require_response_model
            or (len(response_model_values) == len(responses)
                and all(response_model_values))),
        "expected_response_model": (
            expected_response_model is None
            or response_models == {expected_response_model}),
        "expected_tool_interface": (
            expected_tool_interface is None
            or observed_interfaces == {expected_tool_interface}),
        "native_tool_call_observed": (
            expected_tool_interface != "native" or bool(native_calls)),
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "run_id": meta.get("run_id"),
        "model_responses": len(responses),
        "response_cost": response_cost,
        "observed_models": sorted(observed_models),
        "response_models": sorted(response_models),
        "observed_tool_interfaces": sorted(observed_interfaces),
        "native_tool_calls": len(native_calls),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("db", help="excluded Phase 1 canary database")
    parser.add_argument("--output", default="evidence/phase1a-canary-pass.json")
    parser.add_argument("--expected-model")
    parser.add_argument("--require-response-model", action="store_true")
    parser.add_argument("--expected-response-model")
    parser.add_argument("--expected-tool-interface", choices=("textual", "native"))
    args = parser.parse_args()
    db = Path(args.db).resolve()
    repo = Path(__file__).resolve().parent.parent
    ok, report = verify_db(str(db))
    if not ok:
        raise SystemExit("Canary verification failed; no gate receipt written.")
    semantic = check_canary_semantics(
        db, args.expected_model, args.require_response_model,
        args.expected_response_model, args.expected_tool_interface)
    if not semantic["pass"]:
        raise SystemExit(
            "Canary semantic gate failed; no receipt written: "
            + json.dumps(semantic["checks"], sort_keys=True))
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
        "semantic_gate": semantic,
    }
    output = repo / args.output
    write_json(output, receipt)
    print(output)


if __name__ == "__main__":
    main()
