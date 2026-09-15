# Phase 1 Instrument Readiness

**Instrument status:** implemented and offline gate passing
**Collection status:** locked
**Live Phase 1 observations collected:** none

## Implemented

- Neutral deterministic puzzle tasks with environment-held answer keys.
- Independent `solvable` / `blocked` feasibility control.
- Identical artifact-tool surfaces for `absent`, `permitted`, `ambiguous`, and
  `prohibited` policy conditions.
- Scorer-only classification of task-relevant and prohibited writes; this
  metadata is not shown to agents.
- Ground-truth intended-path, unintended-path, and causal cross-agent-rescue
  scoring. Rescue requires a qualifying read from another agent before the
  successful submission.
- Deterministic run/task manifests and balanced execution-plan ordering.
- Real two-wave persistent and ephemeral store behavior with explicit wave,
  snapshot, and reset events.
- Complete model-response capture.
- Full-envelope SHA-256 event chains covering metadata, order, payload, and
  previous-hash linkage.
- Ed25519-signed completion manifests, database digests, and an external-anchor
  request artifact.
- Read-only independent verification and Phase 1 analysis fields.
- Offline unit, negative, and mutation tests.

## Current gate

Run from the repository root:

```bash
python3 -m src.offline_gate src/phase1.yaml
python3 -m unittest discover -s tests -v
```

The gate currently passes. `src/phase1.yaml` and
`src/phase1b-persistence.yaml` both remain locked against live collection.

## Required before the excluded live canary

1. Independently review the task prompts, scorer definitions, and analyzer.
2. Freeze the final Phase 1A preregistration, exclusions, run count, model
   settings, cost ceiling, config hashes, code commit, and analysis contrasts.
3. Create a dedicated Ed25519 study signing key outside the repository and
   retain its public key with the preregistration.
4. Select the independent timestamped anchor location and precommit the receipt
   procedure.
5. Use the separately labeled `src/phase1-canary.yaml`; do not modify the frozen
   matrix config.
6. Have the human operator run one small standalone Baseten canary. Exclude it
   from the study data.
7. Verify authentication, response capture, tool parsing, cost accounting,
   termination, chain integrity, signed manifest, DB digest, and credential
   non-disclosure.
8. Run `python3 -m src.approve_canary <canary.db>` to create the same-commit
   gate receipt required by the matrix preflight.

Only after those checks pass should the frozen Phase 1A matrix be executed.
Phase 1B remains locked until Phase 1A instrumentation and interpretation are
complete.
