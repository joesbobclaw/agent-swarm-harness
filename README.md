# Agent Swarm Harness

Standalone, closed-world research harness for studying coordination and
unauthorized-channel substitution under controlled task conditions.

OpenClaw is not required to run the primary study. It may be used later as a
separate infrastructure variant, but it is deliberately excluded from the
main experiment so credential transport and agent behavior remain distinct.

## Local run

Provide the Baseten credential through your local shell, password manager, or
CI secret facility. Do not commit it, put it in YAML, or send it in chat.

Set `BASETEN_API_KEY` using your local secret manager or shell environment,
then run:

```bash
python3 -m src.orchestrator src/config.yaml
```

The harness records run databases under `runs/`. Keep those logs and the
exact configuration together for later analysis.

## Study design

See [STUDY-SPEC.md](STUDY-SPEC.md) for the preregistered-style design,
controls, outcomes, replication plan, and canary go/no-go criteria.

Phase 0 results and their evidence citations are documented in
[FINDINGS.md](FINDINGS.md). The proposed causal follow-up is specified in
[PHASE1-DESIGN.md](PHASE1-DESIGN.md).

## Phase 1 instrument

`src/phase1.yaml` defines the locked 2 × 4 feasibility-by-policy pilot.
`src/phase1b-persistence.yaml` defines the separately locked two-wave
persistent-versus-ephemeral follow-up. Neither file is authorized for live
collection while `collection_status: locked`.

`PHASE1A-CONFIRMATION-PREREGISTRATION.md` defines the independent 160-run
confirmation of the Phase 1A pilot. Its matrix is
`src/phase1a-confirmation.yaml`, its excluded canary is
`src/phase1a-confirmation-canary.yaml`, and its precommitted verdict logic is
`src/confirmation_analysis.py`. Confirmation run IDs use a `confirm_` prefix
and a study-specific execution-plan file so they cannot overwrite pilot
evidence. The matrix remains locked until its freeze commit, public timestamp,
and same-commit canary receipt exist.

Run the no-network mechanical gate:

```bash
python3 -m src.offline_gate src/phase1.yaml
python3 -m unittest discover -s tests -v
```

Phase 1 emits a deterministic pre-run manifest, a full-envelope SHA-256 event
chain, a completion manifest signed with a dedicated Ed25519 study key, and an
anchor-request digest. The operator must publish that digest to an independent,
timestamped location and record its URI before any discretionary transcript
analysis. Record the returned URI and timestamp with `python3 -m
src.record_anchor <completion-manifest.json> <anchor-uri> <timestamp>`; frozen
runs fail verification without the matching receipt. The signing-key file remains outside the repository; its path is
provided through `SWARM_SIGNING_KEY_PATH` by the operator's local secret
facility.

After offline validation, freeze the Phase 1 preregistration, config, analysis
script, verifier, exclusions, and cost ceiling in one commit. Only then change
the status to `canary` in the separate `src/phase1-canary.yaml` for an explicitly
excluded live plumbing run. After it passes verification, create the mechanical
gate receipt with `python3 -m src.approve_canary <canary.db>`. The full matrix
uses immutable `collection_status: frozen` and refuses to run without a receipt
from the same instrument commit.
