# Preregistration — GPT-5.4 Mini Cross-Provider Replication

**Status:** frozen; excluded canary only after public byte-for-byte verification

**Baseline:** sealed GLM-5.3-Flash confirmation, publicly anchored at
<https://github.com/joesbobclaw/agent-swarm-harness/issues/5>

**Candidate model:** OpenAI dated snapshot `gpt-5.4-mini-2026-03-17`

**Official model record:**
<https://developers.openai.com/api/docs/models/gpt-5.4-mini>

**Matrix:** `src/gpt-5.4-mini-replication.yaml`

**Excluded canary:** `src/gpt-5.4-mini-replication-canary.yaml`

This is a new study namespace and dataset. It does not append observations to
the GLM, DeepSeek, or failed Luna compatibility canary.

## Pre-study fallback record

The publicly frozen Luna canary emitted no textual tool calls and repeated that
simulated tool interactions were unavailable for all ten turns. It remains
preserved and received no pass receipt. Native function calling was not added
because it would change the tool affordance. This GPT-5.4 Mini study is the
predeclared fallback, uses a fresh namespace and seed, and retains the unchanged
textual tool protocol.

## Research question and design

Does the coordination-policy pattern replicate in a dated OpenAI model snapshot
on OpenAI's native provider stack when prompts, textual tools, tasks, scheduling,
sampling temperature, limits, environment seeds, endpoints, and analysis remain
fixed?

The study repeats the sealed 2 × 4 matrix with twenty independent runs per cell,
five sequential agents per run, and 800 agent instances. The run is the
independent unit. Model family, provider, and adapter change together, so this
is not a pure model-effect estimate.

The matrix reuses seeds 74001–74020 and plan seed 20261002. It uses temperature
`0.7`, reasoning effort `none`, a 4,096-token output ceiling, ten turns per
agent, a `$0.08` per-agent ceiling, and a `$25` hard study ceiling. Applying
official GPT-5.4 Mini prices to the completed DeepSeek token volume projects
approximately `$16.00`.

## Endpoints and decision rule

The sealed mechanical endpoints remain task-relevant shared write, verified
cross-agent rescue, and prohibited-policy violation write. The two co-primary
contrasts remain blocked versus solvable under ambiguity and ambiguous versus
prohibited when blocked.

The pattern is confirmed only if both risk differences are positive and both
two-sided Fisher tests remain below 0.05 after Holm correction. Sharing and
rescue are reported separately. Cross-model paired comparisons are descriptive.

## Isolation and evidence sequence

Run IDs use `gpt54m_`; canary IDs use `gpt54m_canary_`. Study plans, receipts,
and manifests are candidate-specific. Existing evidence is never overwritten.

Before any model call, tests and both mechanical gates must pass; this document,
configs, code, tests, analysis, verifier, and public key must be hashed and
committed; matrix state must be `frozen` and canary state `canary`; and the
public snapshot must match byte-for-byte.

The fresh excluded solvable/permitted canary must show a real paid response,
provider model metadata, parseable textual tool calls, a correct submission,
clean termination, valid chain/signature, and no credential leakage. The matrix
requires a verified same-commit receipt.

The human operator launches the 160-run matrix. Only process health and run
counts may be observed until all signed evidence is publicly anchored. Errors
and halted runs remain; no observed run is silently replaced. Conversational
rationales are not treated as internal reasoning.

## Frozen hashes

No canary may run until the freeze commit containing these hashes is published
and verified byte-for-byte.

- Review baseline: `db0dea045fbf514321149bd48caacd8df471e971`
- Matrix config: `80170075509733b699f21bdd68f9cf5ef384521d5f1812c62b251af52abf1551`
- Canary config: `afaf3858a5850291eb23988201706113a57a073c6551b084784b93a8ebef3661`
- Mini cross-provider gate: `d0682455bb16238d69a974cedd25884463a5b9d94c154c073935e563264b88b0`
- Mini operator: `3ca97e2aebf06253e53606a4beaab21cc52015b0534c2322f6bba758e7ade4f5`
- Cross-model analysis: `174db6d52f40624bd060958ec8a0158b5667794f8049945e6b09f1115f381fa4`
- Offline gate: `3ad34777554fa2c67864661bfa0271959b41190d61468ce5c99fabc2e67b2995`
- Canary approver: `97a77dcea6439e3902132c907c4ce898651f6c318c941a3f9bdbcc12348e71b2`
- Agent: `2dc3ff02d3f9810185cae4b5f9373b1c9f4a20477d5ece2e10b48dd6dba6fa97`
- Environment: `ccae50fbc2fbc27ee47eb0a46dd74ecc4588b6bf53da10ca80b5ac3462fd26b2`
- Orchestrator: `35be829b0ce6df4acf6cb3e3c65ef8c480095e0ba6d16729a96df6f3bda359f1`
- Verifier: `eb5ee12e1e5a4471f3e49b03ec7b6dcad5276d3ec24b246e7afaa1b42c6a9c10`
- Instrument tests: `76b2b5e5945457181ba8e8ac1c5b57866336a0da54587eac1687fb3a6503c261`
- Observatory tests: `22d691b70375d4ce138dacd2d73bc80bfcad2876559e453fa93b9f9b8e21978c`
- Public key: `a5080616312615964753595b815f852be009b8f79f17c06e49ba71979e16197d`
- README: `d011336d163fb09bb2a8a4b1882c98ad48df3c9999b527436f182be378c37d88`
