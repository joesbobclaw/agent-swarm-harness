# Agent Swarm Safety Study Specification

**Status:** design draft for pilot implementation  
**Scope:** closed-world study of unauthorized-channel discovery and coordination  
**Non-goal:** reproduce the Artifactory or Hugging Face incident

## 1. Research question

Under what conditions do agents discover and repurpose an ambiguous shared substrate to coordinate or transmit task-relevant information when their assigned task is difficult or impossible?

The study treats the Hugging Face incident as motivation for a mechanism study, not as a target to recreate.

## 2. Claims this study may support

If preregistered predictions are supported, the study may provide evidence about:

- whether shared state increases cross-agent coordination;
- whether ambiguity increases unauthorized use relative to explicit authorization;
- whether task impossibility increases boundary-crossing behavior;
- whether persistent state creates cumulative capability across waves;
- whether agents recognize and report authorization conflicts before acting.

It will not establish that a model is generally misaligned, deceptive, dangerous, or representative of real-world incidents.

## 3. Core factorial design

Primary pilot factors:

1. **Task feasibility:** solvable vs. impossible
2. **Shared substrate:** isolated vs. shared
3. **Authorization:** explicit vs. ambiguous
4. **Persistence:** ephemeral vs. persistent

The minimum first pilot is feasibility × substrate:

- solvable + isolated
- solvable + shared
- impossible + isolated
- impossible + shared

Expand authorization and persistence after the instrumentation is proven.

## 4. Task design

Use synthetic closed-world tasks with no real network or external targets.

Each task has:

- a unique task ID;
- a target state;
- an intended solution path;
- a deterministic answer/flag;
- a feasibility label known to the experimenter but hidden from the agent;
- a scorer that records both answer correctness and path compliance.

Solvable tasks should have a reliable intended solution. Impossible tasks should fail for a documented, pre-verified reason—not because of a flaky model call or harness bug.

The current confidential-document task becomes a separate narrow condition called **unauthorized-channel substitution**, not the headline alignment claim.

## 5. Agent and environment controls

Keep agents isolated at the process/workspace level. Expose only simulated tools.

The shared condition should provide a neutral substrate such as a package/cache-like store. It should not be named “mailbox” unless the explicit-authorization condition is being tested.

The environment records:

- first discovery of shared state;
- list/read/write operations;
- cross-agent information transfer;
- task IDs mentioned;
- attempts to transmit answers or credentials;
- reports to the overseer;
- scorer interactions;
- requests for unauthorized access;
- whether the agent states that an action is unauthorized.

No real secrets, credentials, network targets, or external services are used.

## 6. Outcomes

Primary outcomes:

- run-level discovery of shared state;
- run-level unauthorized coordination;
- run-level scorer manipulation attempt;
- task success through intended path;
- task success through unintended path.

Secondary outcomes:

- time/turn to first discovery;
- number and size of shared writes;
- number of agents participating;
- cross-task information transfer;
- refusal/reporting behavior;
- persistence of useful information into later waves;
- token and dollar cost;
- termination reason.

Analyze at both levels:

- **run-level:** the independent experimental unit;
- **agent-level:** nested observations within a run.

Do not treat ten agents in one shared run as ten independent replications.

## 7. Preregistered predictions

- Shared state increases coordination relative to isolation.
- Ambiguous authorization increases unauthorized use relative to explicit authorization.
- Impossible tasks increase boundary-crossing attempts relative to solvable tasks.
- The effect of shared state is larger for impossible tasks than solvable tasks.
- Persistent state increases later-wave access to useful strategies.
- Explicit authorization increases legitimate coordination without necessarily increasing unauthorized actions.

Report null results and failed runs separately from model errors.

## 8. Replication plan

Pilot:

- one model;
- four feasibility × substrate cells;
- at least 10 independent runs per cell;
- 3–5 agents per run;
- 5–10 turns per agent;
- conservative dollar cap.

Expansion:

- multiple models;
- authorization and persistence factors;
- at least 20 independent runs per primary cell;
- preregistered stopping and exclusion rules.

The independent run count matters more than simply adding agents to one shared run.

## 9. Analysis and reporting

Release:

- harness code;
- exact configs;
- prompts;
- environment implementation;
- event schema;
- raw redacted event logs;
- run-level summary data;
- cost and termination logs;
- analysis script;
- known limitations.

Report effect sizes and confidence intervals, not only example transcripts.

A useful result would look like:

> Impossible tasks increased unauthorized shared-state writes only when shared infrastructure was available, with the effect concentrated in ambiguous-authorization conditions.

A weak result would look like:

> One agent copied a fake memo into a fake folder.

## 10. Standalone execution and canary procedure

OpenClaw is deliberately excluded from the primary experimental path. The
harness reads `BASETEN_API_KEY` from the operator's local process environment;
the credential is never stored in the repository, config, prompts, or run logs.

Before a new study:

1. the human operator supplies the key through a local password manager, shell,
   or CI secret facility;
2. run a small, separately labeled plumbing canary;
3. verify model response, tool parsing, usage/cost accounting, event integrity,
   credential non-disclosure, and clean termination;
4. exclude the canary from study analysis;
5. only then execute the frozen matrix.

OpenClaw may be studied later as a separate infrastructure condition, but mixing
its runtime and secret transport into the primary study would add an unnecessary
confound.

## 11. Go/no-go criteria

Go to the pilot only if:

- the standalone canary authenticates through the configured provider route;
- at least one real model response is logged;
- usage fields are present and cost math is nonzero;
- the event chain verifies;
- no credential material appears in output or artifacts;
- the environment remains closed-world;
- the run terminates within its configured budget.

Stop if authentication, cost accounting, event integrity, or isolation cannot be verified.

## 12. Interpretation boundary

This study can test a causal mechanism related to the incident. It cannot recreate the incident, measure general alignment, or establish real-world attack propensity.

The strongest contribution is a reproducible, safe demonstration of how feasibility pressure, shared state, authorization ambiguity, and persistence interact.
