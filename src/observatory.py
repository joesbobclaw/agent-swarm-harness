#!/usr/bin/env python3
"""Agent Coordination Observatory: behavioral telemetry explorer.

The Observatory reads one or more append-only run databases and produces a
portable JSON dataset or standalone HTML report.  It deliberately separates:

* observed behavior (environment and tool events),
* stated rationale (model-generated text, excluded from the explorer), and
* mechanistic evidence (reserved for a later, explicitly separate phase).

No network service or third-party dependency is required.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from .event_store import EventStore
except ImportError:
    from event_store import EventStore


OBSERVATORY_SCHEMA_VERSION = 1
BEHAVIORAL_TOOLS = {
    "list_artifacts",
    "read_artifact",
    "write_artifact",
    "solve_local",
    "solve_with_fragment",
    "submit_answer",
    "submit_solution",
    "report_to_overseer",
}
BEHAVIORAL_EVENT_TYPES = {
    "agent_terminated",
    "model_error",
    "solution_claim_rejected",
    "store_snapshot",
    "task_solved",
    "wave_finished",
    "wave_started",
}


def _json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {"_parse_error": True}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _content_metadata(content: Any, include_content: bool) -> dict[str, Any]:
    if not isinstance(content, str) or not content:
        return {}
    out: dict[str, Any] = {
        "content_sha256": _digest(content),
        "content_length": len(content),
    }
    if include_content:
        out["content"] = content
    return out


def resolve_db_paths(inputs: Iterable[str], run_prefix: str = "",
                     exclude_name_contains: Iterable[str] = ()) -> list[Path]:
    paths: list[Path] = []
    for raw in inputs:
        path = Path(raw)
        if path.is_dir():
            paths.extend(sorted(path.glob("*.db")))
        elif path.is_file():
            paths.append(path)
        else:
            raise FileNotFoundError(raw)
    unique = {p.resolve(): p for p in paths}
    selected = sorted(unique.values(), key=lambda p: str(p))
    if run_prefix:
        selected = [p for p in selected if p.stem.startswith(run_prefix)]
    excluded = tuple(token for token in exclude_name_contains if token)
    if excluded:
        selected = [p for p in selected if not any(token in p.stem for token in excluded)]
    if not selected:
        raise ValueError("no run databases selected")
    return selected


def _normalize_tool_event(event: dict[str, Any], payload: dict[str, Any],
                          include_content: bool) -> dict[str, Any]:
    tool = payload.get("tool", "unknown")
    args = payload.get("args") if isinstance(payload.get("args"), dict) else {}
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    audit = payload.get("audit") if isinstance(payload.get("audit"), dict) else {}
    normalized: dict[str, Any] = {
        "event_id": event["id"],
        "sequence_no": event.get("sequence_no"),
        "timestamp": event["timestamp"],
        "agent_id": event["agent_id"],
        "turn": event["turn"],
        "kind": "tool_call",
        "tool": tool,
        "success": bool(result.get("success", result.get("correct", False))),
    }
    if tool == "write_artifact":
        artifact_id = result.get("id") or audit.get("artifact_id")
        normalized.update({
            "artifact_id": artifact_id,
            "task_relevant": bool(audit.get("task_relevant")),
            "policy_violation": bool(audit.get("policy_violation")),
            "wave": result.get("wave", audit.get("wave")),
            **_content_metadata(args.get("content"), include_content),
        })
    elif tool == "read_artifact":
        normalized.update({
            "artifact_id": result.get("id") or args.get("id"),
            "artifact_author": result.get("author"),
            "artifact_wave": result.get("wave"),
            **_content_metadata(result.get("content"), include_content),
        })
    elif tool == "list_artifacts":
        artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), list) else []
        normalized["artifact_count"] = len(artifacts)
    elif tool in {"submit_answer", "submit_solution"}:
        normalized.update({
            "correct": bool(result.get("correct")),
            "cross_agent_rescue": bool(audit.get("cross_agent_rescue")),
            "intended_path_success": bool(audit.get("intended_path_success")),
            "path": audit.get("path"),
            "task_id": audit.get("task_id"),
        })
    elif tool == "solve_local":
        normalized.update({
            "failure_code": result.get("failure_code"),
            "task_id": result.get("task_id"),
        })
    return normalized


def load_run(db_path: Path, include_content: bool = False) -> dict[str, Any]:
    store = EventStore(str(db_path), read_only=True)
    try:
        metadata_rows = [dict(row) for row in store.conn.execute(
            "SELECT * FROM run_metadata ORDER BY start_time").fetchall()]
        if len(metadata_rows) != 1:
            raise ValueError(f"expected one run_metadata row, found {len(metadata_rows)}")
        metadata = metadata_rows[0]
        run_id = metadata["run_id"]
        config = _json(metadata.get("config_json"))
        condition = config.get("condition") if isinstance(config.get("condition"), dict) else {}
        model = config.get("model") if isinstance(config.get("model"), dict) else {}
        raw_events = [dict(row) for row in store.conn.execute(
            "SELECT * FROM events WHERE run_id=? ORDER BY id", (run_id,)).fetchall()]
        chain = store.verify_chain(run_id)

        behavioral_events: list[dict[str, Any]] = []
        writes: dict[str, dict[str, Any]] = {}
        reads: list[dict[str, Any]] = []
        solved: list[dict[str, Any]] = []
        rationale_event_count = 0

        for event in raw_events:
            payload = _json(event.get("data_json"))
            if event["event_type"] == "model_response":
                rationale_event_count += 1
                continue
            if event["event_type"] == "tool_call":
                if payload.get("tool") not in BEHAVIORAL_TOOLS:
                    continue
                normalized = _normalize_tool_event(event, payload, include_content)
                behavioral_events.append(normalized)
                if normalized.get("tool") == "write_artifact" and normalized.get("success"):
                    artifact_id = normalized.get("artifact_id")
                    if artifact_id:
                        writes[str(artifact_id)] = normalized
                elif normalized.get("tool") == "read_artifact" and normalized.get("success"):
                    reads.append(normalized)
                continue
            if event["event_type"] not in BEHAVIORAL_EVENT_TYPES:
                continue
            normalized = {
                "event_id": event["id"],
                "sequence_no": event.get("sequence_no"),
                "timestamp": event["timestamp"],
                "agent_id": event["agent_id"],
                "turn": event["turn"],
                "kind": event["event_type"],
            }
            if event["event_type"] == "task_solved":
                normalized.update({
                    "task_id": payload.get("task_id"),
                    "path": payload.get("path"),
                    "cross_agent_rescue": bool(payload.get("cross_agent_rescue")),
                    "intended_path_success": bool(payload.get("intended_path_success")),
                    "qualifying_reads": payload.get("qualifying_reads", []),
                    "wave": payload.get("wave"),
                })
                solved.append(normalized)
            elif event["event_type"] == "agent_terminated":
                normalized["reason"] = payload.get("reason")
            elif event["event_type"] == "model_error":
                normalized["error_type"] = payload.get("type") or payload.get("error_type")
            behavioral_events.append(normalized)

        flows: list[dict[str, Any]] = []
        for read in reads:
            artifact_id = str(read.get("artifact_id") or "")
            write = writes.get(artifact_id)
            if not write:
                continue
            subsequent_solutions = [
                solution for solution in solved
                if solution["agent_id"] == read["agent_id"]
                and solution["event_id"] > read["event_id"]
            ]
            rescue_solution = next((
                solution for solution in subsequent_solutions
                if solution.get("cross_agent_rescue") and any(
                    item.get("artifact_id") == artifact_id
                    for item in solution.get("qualifying_reads", [])
                    if isinstance(item, dict)
                )
            ), None)
            flows.append({
                "artifact_id": artifact_id,
                "writer": write["agent_id"],
                "reader": read["agent_id"],
                "write_event_id": write["event_id"],
                "read_event_id": read["event_id"],
                "write_turn": write["turn"],
                "read_turn": read["turn"],
                "task_relevant": bool(write.get("task_relevant")),
                "policy_violation": bool(write.get("policy_violation")),
                "subsequent_solution": bool(subsequent_solutions),
                "verified_rescue": rescue_solution is not None,
                "solution_event_id": rescue_solution.get("event_id") if rescue_solution else None,
                "task_id": rescue_solution.get("task_id") if rescue_solution else None,
            })

        relevant_writes = [e for e in writes.values() if e.get("task_relevant")]
        policy_violations = [e for e in writes.values() if e.get("policy_violation")]
        rescues = [e for e in solved if e.get("cross_agent_rescue")]
        return {
            "db": str(db_path),
            "run_id": run_id,
            "condition": condition.get("name") or (raw_events[0].get("condition") if raw_events else "unknown"),
            "feasibility": condition.get("feasibility"),
            "store_policy": condition.get("store_policy") or (
                "absent" if not condition.get("shared_artifact_store") else "ambiguous"),
            "model": model.get("id") or model.get("name") or (
                raw_events[0].get("model") if raw_events else "unknown"),
            "status": metadata.get("status"),
            "agents": metadata.get("agent_count", 0),
            "turns": metadata.get("total_turns", 0),
            "cost": metadata.get("total_cost", 0.0),
            "start_time": metadata.get("start_time"),
            "end_time": metadata.get("end_time"),
            "chain_ok": not chain["breaks"] and chain["verified"] == chain["total"],
            "chain_events": chain["total"],
            "rationale_event_count": rationale_event_count,
            "artifact_writes": len(writes),
            "task_relevant_writes": len(relevant_writes),
            "artifact_reads": len(reads),
            "policy_violation_writes": len(policy_violations),
            "solved_agents": len({e["agent_id"] for e in solved}),
            "cross_agent_rescues": len(rescues),
            "behavioral_events": behavioral_events,
            "flows": flows,
        }
    finally:
        store.close()


def _aggregate_conditions(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        grouped[(run.get("feasibility") or "unknown",
                 run.get("store_policy") or "unknown")].append(run)
    aggregates = []
    for (feasibility, policy), group in sorted(grouped.items()):
        count = len(group)
        runs_with_write = sum(bool(run["task_relevant_writes"]) for run in group)
        runs_with_rescue = sum(bool(run["cross_agent_rescues"]) for run in group)
        aggregates.append({
            "feasibility": feasibility,
            "store_policy": policy,
            "runs": count,
            "agents": sum(run["agents"] for run in group),
            "runs_with_task_relevant_write": runs_with_write,
            "sharing_rate": runs_with_write / count,
            "runs_with_cross_agent_rescue": runs_with_rescue,
            "rescue_rate": runs_with_rescue / count,
            "artifact_reads": sum(run["artifact_reads"] for run in group),
            "artifact_writes": sum(run["artifact_writes"] for run in group),
            "policy_violation_writes": sum(run["policy_violation_writes"] for run in group),
            "cost": sum(run["cost"] for run in group),
            "all_chains_ok": all(run["chain_ok"] for run in group),
        })
    return aggregates


def build_dataset(paths: Iterable[Path], include_content: bool = False) -> dict[str, Any]:
    runs = [load_run(path, include_content=include_content) for path in paths]
    events = []
    flows = []
    for run in runs:
        for event in run.pop("behavioral_events"):
            events.append({"run_id": run["run_id"], "condition": run["condition"], **event})
        for flow in run.pop("flows"):
            flows.append({"run_id": run["run_id"], "condition": run["condition"], **flow})
    return {
        "schema_version": OBSERVATORY_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evidence_policy": {
            "scope": "behavioral_telemetry",
            "observed": "Environment events and tool-boundary operations.",
            "stated_rationale": "Model responses are counted but their text is excluded; they are not internal thought.",
            "causal_limit": "Read-before-success establishes information delivery and temporal precedence, not internal cognitive causation.",
            "content_included": include_content,
        },
        "phase2_interpretability": {
            "status": "not_collected",
            "scope": "Future activation, probe, SAE, and causal-intervention evidence for open-weight models.",
        },
        "totals": {
            "runs": len(runs),
            "agents": sum(run["agents"] for run in runs),
            "cost": sum(run["cost"] for run in runs),
            "events": len(events),
            "flows": len(flows),
            "verified_rescue_flows": sum(flow["verified_rescue"] for flow in flows),
            "policy_violation_writes": sum(run["policy_violation_writes"] for run in runs),
            "all_chains_ok": all(run["chain_ok"] for run in runs),
        },
        "conditions": _aggregate_conditions(runs),
        "runs": runs,
        "flows": flows,
        "events": sorted(events, key=lambda e: (e["run_id"], e["event_id"])),
    }


def render_html(dataset: dict[str, Any]) -> str:
    encoded = json.dumps(dataset, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    title = "Agent Coordination Observatory"
    return f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>{html.escape(title)}</title>
<style>
:root{{--bg:#091017;--panel:#111c26;--panel2:#172532;--ink:#e9f0f5;--muted:#91a3b3;--line:#294051;--cyan:#55d6c2;--amber:#ffbf69;--red:#ff6b6b;--blue:#6aa9ff}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace}}
header{{padding:32px clamp(18px,4vw,60px);border-bottom:1px solid var(--line);background:linear-gradient(135deg,#101e29,#081017)}}
h1{{margin:0 0 8px;font-size:clamp(28px,4vw,48px);letter-spacing:-2px}} h2{{margin:30px 0 12px}} p{{max-width:900px;color:var(--muted)}}
main{{padding:24px clamp(18px,4vw,60px) 60px}} .badge{{display:inline-block;padding:5px 9px;border:1px solid var(--line);border-radius:999px;color:var(--cyan)}}
.notice{{padding:14px 16px;border-left:3px solid var(--amber);background:var(--panel);max-width:1000px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:18px 0}} .card{{background:var(--panel);border:1px solid var(--line);padding:16px;border-radius:10px}}
.card strong{{display:block;font-size:26px;color:var(--cyan)}} .card span{{color:var(--muted)}}
.controls{{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0}} select,input{{background:var(--panel2);color:var(--ink);border:1px solid var(--line);padding:9px;border-radius:6px}}
.tablewrap{{overflow:auto;border:1px solid var(--line);border-radius:10px}} table{{width:100%;border-collapse:collapse;background:var(--panel)}} th,td{{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}} th{{position:sticky;top:0;background:var(--panel2);color:var(--muted)}}
.yes{{color:var(--cyan)}} .no{{color:var(--muted)}} .bad{{color:var(--red)}} code{{color:var(--blue)}} footer{{color:var(--muted);margin-top:30px}}
</style>
</head>
<body>
<header><span class=\"badge\">Phase 1 · Behavioral telemetry</span><h1>{html.escape(title)}</h1><p>Trace shared-state coordination from observed writes to reads to consequential actions. No conversational text is treated as internal thought.</p></header>
<main>
<div class=\"notice\"><strong>Evidence boundary:</strong> This explorer shows instrumented behavior. Read-before-success proves delivery and temporal precedence, not a model's hidden reasoning. Phase 2 mechanistic evidence is not collected.</div>
<div class=\"grid\" id=\"cards\"></div>
<h2>Condition profile</h2><div class=\"tablewrap\"><table><thead><tr><th>Feasibility</th><th>Policy</th><th>Runs</th><th>Shared</th><th>Rescued</th><th>Reads</th><th>Violations</th><th>Integrity</th></tr></thead><tbody id=\"conditions\"></tbody></table></div>
<h2>Information-flow edges</h2><p>Each edge is an observed artifact write followed by a successful read. “Rescue” additionally requires a later correct submission with that artifact recorded as qualifying evidence.</p>
<div class=\"controls\"><input id=\"flowSearch\" placeholder=\"Filter run, agent, artifact\"><select id=\"flowKind\"><option value=\"all\">All flows</option><option value=\"rescue\">Verified rescues</option><option value=\"nonrescue\">Reads without rescue</option></select></div>
<div class=\"tablewrap\"><table><thead><tr><th>Run</th><th>Artifact</th><th>Writer → reader</th><th>Write/read event</th><th>Task relevant</th><th>Outcome</th></tr></thead><tbody id=\"flows\"></tbody></table></div>
<h2>Behavioral event explorer</h2>
<div class=\"controls\"><input id=\"eventSearch\" placeholder=\"Filter run or agent\"><select id=\"eventKind\"><option value=\"all\">All events</option></select></div>
<div class=\"tablewrap\"><table><thead><tr><th>Run</th><th>Event</th><th>Agent</th><th>Turn</th><th>Operation</th><th>Observed outcome</th></tr></thead><tbody id=\"events\"></tbody></table></div>
<h2>Phase 2 · Mechanistic interpretability</h2><p><strong>Status: not collected.</strong> Future open-weight studies may add activation probes, SAE features, and causal interventions. Those signals must remain separate from behavioral facts and model-generated rationales.</p>
<footer>Generated <span id=\"generated\"></span> · Standalone report · No external scripts or network requests</footer>
</main>
<script>const DATA={encoded};
const pct=x=>`${{Math.round(x*100)}}%`; const yn=x=>x?'<span class="yes">yes</span>':'<span class="no">no</span>';
document.getElementById('generated').textContent=DATA.generated_at;
const cards=[['Runs',DATA.totals.runs],['Agents',DATA.totals.agents],['Behavioral events',DATA.totals.events],['Information flows',DATA.totals.flows],['Verified rescues',DATA.totals.verified_rescue_flows],['Evidence chains',DATA.totals.all_chains_ok?'all valid':'check failures']];
document.getElementById('cards').innerHTML=cards.map(([a,b])=>`<div class="card"><strong>${{b}}</strong><span>${{a}}</span></div>`).join('');
document.getElementById('conditions').innerHTML=DATA.conditions.map(c=>`<tr><td>${{c.feasibility}}</td><td>${{c.store_policy}}</td><td>${{c.runs}}</td><td>${{c.runs_with_task_relevant_write}}/${{c.runs}} (${{pct(c.sharing_rate)}})</td><td>${{c.runs_with_cross_agent_rescue}}/${{c.runs}} (${{pct(c.rescue_rate)}})</td><td>${{c.artifact_reads}}</td><td class="${{c.policy_violation_writes?'bad':''}}">${{c.policy_violation_writes}}</td><td>${{yn(c.all_chains_ok)}}</td></tr>`).join('');
const esc=s=>String(s??'').replace(/[&<>\"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}}[c]));
function drawFlows(){{const q=document.getElementById('flowSearch').value.toLowerCase(),kind=document.getElementById('flowKind').value;let rows=DATA.flows.filter(f=>JSON.stringify([f.run_id,f.writer,f.reader,f.artifact_id]).toLowerCase().includes(q));if(kind==='rescue')rows=rows.filter(f=>f.verified_rescue);if(kind==='nonrescue')rows=rows.filter(f=>!f.verified_rescue);document.getElementById('flows').innerHTML=rows.slice(0,1000).map(f=>`<tr><td>${{esc(f.run_id)}}</td><td><code>${{esc(f.artifact_id)}}</code></td><td>${{esc(f.writer)}} → ${{esc(f.reader)}}</td><td>${{f.write_event_id}} → ${{f.read_event_id}}</td><td>${{yn(f.task_relevant)}}</td><td class="${{f.verified_rescue?'yes':'no'}}">${{f.verified_rescue?'verified rescue':(f.subsequent_solution?'later solution; not attributed':'read only')}}</td></tr>`).join('')||'<tr><td colspan="6">No matching flows</td></tr>'}}
const kinds=[...new Set(DATA.events.map(e=>e.tool||e.kind))].sort();document.getElementById('eventKind').innerHTML+=[...kinds].map(k=>`<option value="${{esc(k)}}">${{esc(k)}}</option>`).join('');
function outcome(e){{if(e.tool==='write_artifact')return e.policy_violation?'policy violation':(e.task_relevant?'task-relevant write':'write');if(e.tool==='read_artifact')return `read ${{e.artifact_id||''}} from ${{e.artifact_author||'?'}}`;if(e.tool==='submit_answer')return e.correct?(e.cross_agent_rescue?'correct · rescue':'correct'):'incorrect';if(e.kind==='task_solved')return e.cross_agent_rescue?'solved · rescue':`solved · ${{e.path||'unknown path'}}`;if(e.kind==='agent_terminated')return e.reason||'terminated';return e.success===false?'failed':'observed'}}
function drawEvents(){{const q=document.getElementById('eventSearch').value.toLowerCase(),kind=document.getElementById('eventKind').value;let rows=DATA.events.filter(e=>JSON.stringify([e.run_id,e.agent_id]).toLowerCase().includes(q));if(kind!=='all')rows=rows.filter(e=>(e.tool||e.kind)===kind);document.getElementById('events').innerHTML=rows.slice(0,2000).map(e=>`<tr><td>${{esc(e.run_id)}}</td><td>${{e.event_id}}</td><td>${{esc(e.agent_id)}}</td><td>${{e.turn}}</td><td>${{esc(e.tool||e.kind)}}</td><td>${{esc(outcome(e))}}</td></tr>`).join('')||'<tr><td colspan="6">No matching events</td></tr>'}}
['flowSearch','flowKind'].forEach(id=>document.getElementById(id).addEventListener('input',drawFlows));['eventSearch','eventKind'].forEach(id=>document.getElementById(id).addEventListener('input',drawEvents));drawFlows();drawEvents();</script>
</body></html>"""


def write_json(dataset: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dataset, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_report(dataset: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(dataset), encoding="utf-8")


def _dataset_from_args(args: argparse.Namespace) -> dict[str, Any]:
    paths = resolve_db_paths(args.inputs, args.run_prefix, args.exclude_name_contains)
    return build_dataset(paths, include_content=args.include_content)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="coord-observatory",
                                     description="Explore signed behavioral telemetry from agent runs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def common(command: argparse.ArgumentParser) -> None:
        command.add_argument("inputs", nargs="+", help="Run databases or directories containing them")
        command.add_argument("--run-prefix", default="", help="Only include database names with this prefix")
        command.add_argument("--exclude-name-contains", action="append", default=[],
                             help="Exclude database names containing this token; repeatable")
        command.add_argument("--include-content", action="store_true",
                             help="Embed artifact contents; off by default for privacy")

    doctor = subparsers.add_parser("doctor", help="Validate database readability and evidence chains")
    common(doctor)
    export = subparsers.add_parser("export", help="Export normalized behavioral telemetry as JSON")
    common(export)
    export.add_argument("--output", required=True, type=Path)
    report = subparsers.add_parser("report", help="Build a standalone interactive HTML explorer")
    common(report)
    report.add_argument("--output", required=True, type=Path)
    report.add_argument("--json-output", type=Path)

    args = parser.parse_args(argv)
    try:
        dataset = _dataset_from_args(args)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.command == "doctor":
        print(f"runs={dataset['totals']['runs']} agents={dataset['totals']['agents']} "
              f"chains={'ok' if dataset['totals']['all_chains_ok'] else 'BROKEN'}")
        for run in dataset["runs"]:
            print(f"{run['run_id']}: status={run['status']} events={run['chain_events']} "
                  f"chain={'ok' if run['chain_ok'] else 'BROKEN'}")
        return 0 if dataset["totals"]["all_chains_ok"] else 1
    if args.command == "export":
        write_json(dataset, args.output)
        print(f"behavioral telemetry written to {args.output}")
        return 0
    write_report(dataset, args.output)
    if args.json_output:
        write_json(dataset, args.json_output)
    print(f"observatory report written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
