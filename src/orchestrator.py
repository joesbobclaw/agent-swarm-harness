"""Run a frozen experiment plan and emit independently verifiable evidence."""

from __future__ import annotations

import hashlib
import json
import os
import random
import subprocess
import time
from datetime import datetime
from pathlib import Path

import yaml

from .agent import Agent
from .environment import Environment
from .event_store import EventStore, canonical_json
from .evidence import (build_completion_manifest, build_prerun_manifest,
                       git_commit, load_private_key, sha256_file, sign_manifest,
                       write_anchor_request, write_json)


class Orchestrator:
    def __init__(self, config_path: str):
        self.config_path = Path(config_path).resolve()
        with open(self.config_path) as handle:
            self.config = yaml.safe_load(handle)
        status = self.config.get("collection_status", "locked")
        if self.config.get("study_phase") == 1 and status not in {"locked", "canary", "frozen"}:
            raise SystemExit(f"\n[PREFLIGHT] Invalid Phase 1 collection_status: {status}\n")
        if self.config.get("study_phase") == 1 and status == "locked":
            raise SystemExit(
                "\n[PREFLIGHT] Phase 1 data collection is locked. Finish offline tests, "
                "freeze the preregistration, then set collection_status to 'canary' for "
                "the excluded plumbing canary or 'frozen' for the matrix.\n")
        if (self.config.get("study_phase") == 1 and status == "canary" and
                self.config.get("run_kind") != "excluded_canary"):
            raise SystemExit("\n[PREFLIGHT] Canary runs must declare run_kind: excluded_canary.\n")
        self.repo = self.config_path.parent.parent
        self.study_id = self.config.get("study_id", f"phase-{self.config.get('study_phase', 0)}")
        self.output_dir = self.repo / "runs"
        self.evidence_dir = self.repo / "evidence"
        if self.config.get("study_phase") == 1:
            scoped_paths = [
                "src", "PHASE1-DESIGN.md", "PHASE1-READINESS.md", "README.md",
                "requirements.txt", "tests",
            ]
            preregistration_file = self.config.get("preregistration_file")
            if preregistration_file:
                scoped_paths.append(preregistration_file)
            scoped = subprocess.run(
                ["git", "status", "--porcelain", "--", *scoped_paths],
                cwd=self.repo, capture_output=True, text=True, check=True).stdout.strip()
            if scoped:
                raise SystemExit(
                    "\n[PREFLIGHT] Phase 1 instrument files are not clean in git. "
                    "Commit the reviewed freeze before a live call.\n")
            if status == "frozen":
                receipt_path = self.repo / self.config.get(
                    "required_canary_receipt", "evidence/phase1a-canary-pass.json")
                if not receipt_path.exists():
                    raise SystemExit(
                        f"\n[PREFLIGHT] Frozen matrix requires verified canary receipt: {receipt_path}\n")
                receipt = json.loads(receipt_path.read_text())
                if (receipt.get("verified") is not True or
                        receipt.get("instrument_commit") != git_commit(self.repo)):
                    raise SystemExit(
                        "\n[PREFLIGHT] Canary receipt is invalid or belongs to a different instrument commit.\n")
        self.api_base = self.config["api_base"]
        self.api_key = os.environ.get(self.config["api_key_env"], "")
        if not self.api_key:
            raise SystemExit(
                f"\n[PREFLIGHT] {self.config['api_key_env']} is not set.\n"
                "Supply it through the operator's local secret facility; never put it "
                "in YAML, a command argument, or a study log.\n")
        self.signing_key = None
        if self.config.get("study_phase") == 1:
            key_path = os.environ.get(self.config.get("signing_key_path_env",
                                                       "SWARM_SIGNING_KEY_PATH"), "")
            if not key_path:
                raise SystemExit("\n[PREFLIGHT] Phase 1 requires a dedicated Ed25519 signing-key path.\n")
            self.signing_key = load_private_key(key_path)

    def _run_id(self, condition: dict, model: dict, replicate_id: int) -> str:
        model_name = model["id"].split("/")[-1].replace(".", "_")
        prefix = self.config.get("run_id_prefix", "")
        stem = f"{condition['name']}_{model_name}_rep{replicate_id}"
        return f"{prefix}_{stem}".strip("_").replace("/", "_")

    def _environment(self, condition: dict, seed: int, agent_count: int) -> Environment:
        return Environment(
            shared_artifact_store=condition.get("shared_artifact_store", False),
            explicit_mailbox=condition.get("explicit_mailbox", False),
            store_persists=condition.get("store_persists", False),
            document=self.config["task"].get("document", ""), seed=seed,
            task_config=self.config["task"],
            feasibility=condition.get("feasibility", "solvable"),
            store_policy=condition.get("store_policy"), agent_count=agent_count)

    def _run_agent(self, env: Environment, store: EventStore, run_id: str,
                   condition: dict, model: dict, seed: int, agent_id: str,
                   agent_index: int, max_turns: int, agent_budget: float | None,
                   remaining_global_budget: float) -> dict:
        effective_model = {**model, "tool_interface": condition.get(
            "tool_interface", model.get("tool_interface", "textual"))}
        agent = Agent(agent_id, agent_index, env, effective_model, run_id, condition["name"],
                      seed, store, self.api_base, self.api_key)
        cost = 0.0
        turns = 0
        reason = None
        for _ in range(max_turns):
            result = agent.execute_turn(cost_budget=agent_budget)
            cost += result.get("cost", 0.0)
            turns += 1
            if result["type"] == "budget_exhausted":
                reason = result["termination_reason"]
            elif result.get("solved"):
                reason = "solved"
            elif result["type"] == "error":
                reason = result.get("termination_reason", "model_error")
            elif cost >= remaining_global_budget:
                reason = "global_cost_budget"
            if reason:
                event = "agent_error" if reason == "model_error" else "agent_terminated"
                if reason != "solved":
                    store.log(run_id, agent_id, agent.turn, event,
                              {"reason": reason, "agent_cost": agent.cost},
                              model=model["id"], condition=condition["name"], seed=seed)
                break
            time.sleep(0.1)
        if not reason:
            reason = "max_turns"
            store.log(run_id, agent_id, agent.turn, "agent_terminated",
                      {"reason": reason, "turns": agent.turn, "agent_cost": agent.cost},
                      model=model["id"], condition=condition["name"], seed=seed)
        return {"cost": cost, "turns": turns, "solved": agent.solved, "reason": reason}

    def run_condition(self, condition: dict, model: dict, seed: int,
                      replicate_id: int, global_budget: float | None = None) -> dict:
        run_id = self._run_id(condition, model, replicate_id)
        db_path = self.output_dir / f"{run_id}.db"
        if db_path.exists():
            raise FileExistsError(f"refusing to overwrite existing run: {db_path}")
        agent_count = condition.get("agents_per_wave",
                                    self.config.get("agents_per_condition", 5))
        env = self._environment(condition, seed, agent_count)
        prerun = build_prerun_manifest(run_id, condition, model, seed,
                                       env.manifest_tasks(), self.config_path, self.repo)
        prerun_path = self.evidence_dir / "prerun" / f"{run_id}.json"
        prerun_hash = write_json(prerun_path, prerun)
        store = EventStore(str(db_path))
        total_cost = 0.0
        total_turns = 0
        solutions = 0
        agents_started = 0
        reasons: dict[str, int] = {}
        waves = int(condition.get("waves", 1))
        persistence = condition.get("persistence", "persistent")
        agent_budget = self.config.get("agent_cost_budget")
        global_budget = global_budget if global_budget is not None else self.config.get("cost_budget", float("inf"))
        try:
            store.init_run(run_id, {"condition": condition, "model": model, "seed": seed,
                                    "task": self.config["task"],
                                    "collection_status": self.config.get("collection_status"),
                                    "prerun_manifest": str(prerun_path)},
                           manifest_hash=prerun_hash)
            for wave in range(1, waves + 1):
                reset = wave > 1 and persistence == "ephemeral"
                wave_state = env.start_wave(wave, reset_store=reset)
                store.log(run_id, "environment", 0, "wave_started", wave_state,
                          model=model["id"], condition=condition["name"], seed=seed)
                if wave == 1 and condition.get("store_initialization", "empty") == "seeded":
                    seeded = env.seed_coordination_artifact(
                        int(condition.get("seed_target_index", 0)))
                    store.log(run_id, "environment", 0, "store_seeded", seeded,
                              model=model["id"], condition=condition["name"], seed=seed)
                if reset:
                    store.log(run_id, "environment", 0, "store_reset", wave_state,
                              model=model["id"], condition=condition["name"], seed=seed)
                for index in range(agent_count):
                    if total_cost >= global_budget:
                        break
                    agent_id = f"wave-{wave:02d}-agent-{index:02d}"
                    agents_started += 1
                    outcome = self._run_agent(
                        env, store, run_id, condition, model, seed, agent_id, index,
                        self.config.get("max_turns_per_agent", 10), agent_budget,
                        max(global_budget - total_cost, 0.0))
                    total_cost += outcome["cost"]
                    total_turns += outcome["turns"]
                    solutions += int(outcome["solved"])
                    reasons[outcome["reason"]] = reasons.get(outcome["reason"], 0) + 1
                    if total_cost >= global_budget:
                        break
                snapshot = {"wave": wave, "artifact_count": len(env.artifacts),
                            "artifact_hashes": [hashlib.sha256(a.content.encode()).hexdigest()
                                                for a in env.artifacts]}
                store.log(run_id, "environment", 0, "store_snapshot", snapshot,
                          model=model["id"], condition=condition["name"], seed=seed)
                store.log(run_id, "environment", 0, "wave_finished",
                          {"wave": wave, "total_cost": total_cost},
                          model=model["id"], condition=condition["name"], seed=seed)
                if total_cost >= global_budget:
                    break
            planned_agents = agent_count * waves
            halted = agents_started < planned_agents
            if halted:
                store.log(run_id, "environment", 0, "run_halted",
                          {"reason": "global_cost_budget", "agents_started": agents_started,
                           "agents_planned": planned_agents}, model=model["id"],
                          condition=condition["name"], seed=seed)
            metrics = {
                "solutions_found": solutions, "total_agents": agents_started,
                "planned_agents": planned_agents,
                "artifacts_written": env.total_artifacts_written,
                "task_relevant_writes": env.total_task_relevant_writes,
                "policy_violation_writes": env.total_policy_violation_writes,
                "seeded_artifacts": env.total_seeded_artifacts,
                "seeded_artifact_reads": env.total_seeded_artifact_reads,
                "seeded_rescues": env.total_seeded_rescues,
                "artifacts_read": env.total_artifacts_read,
                "overseer_reports": len(env.overseer_reports),
                "solution_claims": len(env.solution_claims),
                "coordinating_agents": len({a.author for a in env.artifacts
                                             if a.author != "seed-agent"}),
                "termination_reasons": reasons, "waves": waves,
                "persistence": persistence,
            }
            store.finish_run(run_id, total_cost, agents_started, total_turns,
                             status="halted" if halted else "completed")
            chain = store.verify_chain(run_id)
            chain["head"] = store.chain_head(run_id)
            result = {"run_id": run_id, "condition": condition["name"],
                      "model": model["id"], "seed": seed, "replicate_id": replicate_id,
                      "total_cost": total_cost, "total_turns": total_turns,
                      "metrics": metrics, "chain_integrity": chain, "db_path": str(db_path),
                      "prerun_manifest": str(prerun_path),
                      "prerun_manifest_sha256": prerun_hash}
        finally:
            store.close()

        if self.signing_key:
            completion = build_completion_manifest(result, db_path, prerun_hash)
            completion_path = self.evidence_dir / "completion" / f"{run_id}.json"
            write_json(completion_path, completion)
            signature = sign_manifest(completion, self.signing_key)
            signature_path = completion_path.with_suffix(".signature.json")
            write_json(signature_path, signature)
            anchor_path = completion_path.with_suffix(".anchor-request.txt")
            write_anchor_request(anchor_path, completion, signature)
            result.update({"completion_manifest": str(completion_path),
                           "signature": str(signature_path),
                           "anchor_request": str(anchor_path)})
        return result

    def _execution_plan(self) -> list[tuple[dict, dict, int, int]]:
        replicates = self.config.get("replicate_ids", self.config.get("seeds", [1]))
        seeds = self.config.get("run_seeds", replicates)
        if len(seeds) != len(replicates):
            raise ValueError("run_seeds and replicate_ids must have equal length")
        plan = [(condition, model, seed, replicate)
                for replicate, seed in zip(replicates, seeds)
                for condition in self.config["conditions"]
                for model in self.config["models"]]
        random.Random(self.config.get("plan_seed", 20260914)).shuffle(plan)
        return plan

    def run_all(self) -> list[dict]:
        plan = self._execution_plan()
        plan_public = [{"order": i, "condition": c["name"], "model": m["id"],
                        "run_seed": s, "replicate_id": r}
                       for i, (c, m, s, r) in enumerate(plan, 1)]
        plan_path = self.evidence_dir / self.config.get(
            "execution_plan_file", "execution-plan.json")
        write_json(plan_path, {"schema": "swarm-study-execution-plan-v1", "runs": plan_public})
        budget = self.config.get("cost_budget", 10.0)
        results, total_cost = [], 0.0
        print(f"=== Agent Swarm Harness — Phase {self.config.get('study_phase', 0)} ===")
        print(f"Runs: {len(plan)} · Cost budget: ${budget:.2f}")
        for condition, model, seed, replicate in plan:
            if total_cost >= budget:
                break
            print(f"  [{condition['name']}] replicate={replicate} ...", end=" ", flush=True)
            try:
                result = self.run_condition(condition, model, seed, replicate,
                                            global_budget=budget - total_cost)
                results.append(result); total_cost += result["total_cost"]
                print(f"OK · ${result['total_cost']:.4f} · {result['metrics']['solutions_found']} solved")
            except Exception as exc:
                print(f"FAIL: {exc}")
                results.append({"condition": condition["name"], "model": model["id"],
                                "replicate_id": replicate, "error": str(exc)})
        summary_path = self._save_summary(results)
        if self.signing_key:
            self._finalize_study(results, plan_path, summary_path, len(plan))
        return results

    def _save_summary(self, results: list[dict]) -> Path:
        summary = {"timestamp": datetime.now().isoformat(), "results": results}
        path = self.output_dir / f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        write_json(path, summary)
        print(f"Summary saved to {path}")
        return path

    def _finalize_study(self, results: list[dict], plan_path: Path,
                        summary_path: Path, planned_runs: int) -> None:
        ordered = []
        for result in results:
            if "error" in result:
                ordered.append({"condition": result.get("condition"),
                                "replicate_id": result.get("replicate_id"),
                                "error": result["error"]})
                continue
            ordered.append({
                "run_id": result["run_id"],
                "db_sha256": sha256_file(result["db_path"]),
                "final_chain_head": result["chain_integrity"]["head"],
                "completion_manifest_sha256": sha256_file(result["completion_manifest"]),
                "total_cost": result["total_cost"],
            })
        complete = len(results) == planned_runs and all("error" not in r for r in results)
        manifest = {
            "schema": "swarm-study-matrix-completion-v1",
            "study_id": self.study_id,
            "collection_status": self.config.get("collection_status"),
            "status": "complete" if complete else "incomplete",
            "code_commit": git_commit(self.repo),
            "config_sha256": sha256_file(self.config_path),
            "execution_plan_sha256": sha256_file(plan_path),
            "summary_sha256": sha256_file(summary_path),
            "planned_runs": planned_runs,
            "recorded_runs": len(results),
            "total_cost": sum(r.get("total_cost", 0.0) for r in results),
            "ordered_runs": ordered,
        }
        path = self.evidence_dir / f"{self.study_id}-completion.json"
        write_json(path, manifest)
        signature = sign_manifest(manifest, self.signing_key)
        write_json(path.with_suffix(".signature.json"), signature)
        write_anchor_request(path.with_suffix(".anchor-request.txt"), manifest, signature)
        print(f"Study completion manifest saved to {path}")


def main():
    import sys
    config_path = sys.argv[1] if len(sys.argv) > 1 else "src/config.yaml"
    Orchestrator(config_path).run_all()


if __name__ == "__main__":
    main()
