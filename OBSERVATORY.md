# Agent Coordination Observatory

Agent Coordination Observatory is the behavioral-telemetry layer for this
research program. It answers three operational questions:

1. Which shared resources carried information between agents?
2. Who wrote, read, and subsequently acted on that information?
3. Did the information flow produce a verified cross-agent rescue or violate a
   stated policy boundary?

It does **not** treat model-generated conversational text as internal thought.
The current explorer uses environment events and tool-boundary operations only.

## Evidence model

- **Observed behavior:** reads, writes, submissions, solutions, policy flags,
  errors, termination, event order, and evidence-chain verification.
- **Stated rationale:** counted but excluded from the explorer. It may support
  qualitative analysis, but is not faithful internal reasoning.
- **Mechanistic evidence:** not collected in Phase 1. Phase 2 may add activation
  probes, SAE features, and controlled interventions for open-weight models.

A read-before-correct-submission sequence establishes information delivery and
temporal precedence. It does not by itself establish a model's internal causal
reasoning.

## Commands

Validate all confirmation databases and their event chains:

```bash
python3 -m src.observatory doctor runs/ --run-prefix confirm_ \
  --exclude-name-contains canary
```

Build a standalone interactive report and normalized JSON export:

```bash
python3 -m src.observatory report runs/ --run-prefix confirm_ \
  --exclude-name-contains canary \
  --output reports/agent-coordination-observatory.html \
  --json-output reports/agent-coordination-observatory.json
```

Export JSON only:

```bash
python3 -m src.observatory export runs/ --run-prefix confirm_ \
  --exclude-name-contains canary \
  --output reports/agent-coordination-observatory.json
```

Artifact contents are excluded by default. Use `--include-content` only when
the evidence is synthetic or has been reviewed for sensitive material.

## Phase 2 boundary

Mechanistic interpretability remains a separate evidence track. A future
adapter may attach activation-derived signals to the same ordered behavioral
events, but those signals must be labeled as correlational unless they survive
held-out semantic controls and causal intervention tests.
