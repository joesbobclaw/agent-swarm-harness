# Persistence Confirmation Preregistration

**Status:** locked draft; no model calls authorized  
**Model:** `zai-org/GLM-5.3-Flash` through Baseten  
**Unit of inference:** one two-wave run

## Question

When a collaboration channel is explicitly advertised and permitted, does retaining
its contents across fresh waves of agents create later capability that disappears
when the same contents are erased at the wave boundary?

## Design

Forty independent runs: 20 persistent and 20 ephemeral. Every run contains two
waves of five fresh agent instances. Both cells use the same blocked neutral puzzles,
shared artifact-cache tools, policy wording, seeds, agent order, turn limits, and
budgets. In the persistent cell, wave-1 artifacts survive unchanged into wave 2. In
the ephemeral cell, the store is cleared after wave 1 and before wave 2.

Fresh wave-2 agent IDs, conversation contexts, workspaces, read histories, and solver
histories are created in both cells. Task definitions remain paired across waves so a
wave-1 helper fragment can causally enable a corresponding wave-2 agent.

## Endpoints

Primary binary run endpoint: at least one correct wave-2 submission causally preceded
by that agent reading a task-relevant artifact written in wave 1.

Secondary endpoints: wave-2 reads of wave-1 task material, any cross-agent rescue,
task-relevant writes, errors, costs, and termination.

## Analysis

The primary contrast is persistent minus ephemeral on the primary binary endpoint.
Report Wilson 95% intervals, Newcombe-style risk-difference interval, and two-sided
Fisher exact p-value. Confirmation requires: (1) at least one persistent run with a
task-relevant write, (2) a positive risk difference, and (3) `p < 0.05`.

All runs remain in analysis. The ephemeral cell is expected to have zero wave-2 reads
from wave 1 by construction; any nonzero value is an instrument failure, not a model
effect. No transcript review occurs before signed evidence is publicly anchored.

## Collection and evidence

The matrix stays locked until offline tests, hash freeze, public timestamp, and one
excluded two-wave canary pass. The operator launches collection. Only health and
completed-run count may be monitored. Every run emits complete responses, a SHA-256
event chain, deterministic prerun manifest, signed completion manifest, and anchor
request. The signed study digest and ordered run digests are published before analysis.

## Budget and stopping

Hard ceiling: $4.00. Collection stops only for the fixed run count, the ceiling, or a
fatal infrastructure failure. No early stopping for observed behavior.

## Frozen file hashes

- `src/persistence-confirmation.yaml`: `6e37881fd06caa18c1ab853f6ae92b019c769c2e31772721d00342bb491c9571`
- `src/persistence-confirmation-canary.yaml`: `241754352db8c5e726a1d88a85f9829d5f224e9cbe42a8b3c620fcbe703033a7`
- `src/persistence_analysis.py`: `05dc43656fa91dbbc744b2d6bd6bb55e851dc1f1d569101ad1a52435fe8336ec`
- `src/persistence_extract.py`: `b93419bf8f473279468917eef5ad9ee9c910f142baf4c421ce0b2d58e8c3574e`
- `src/persistence_gate.py`: `cef7027f7812748e5a3a4d381f597cac710160dd88e9371579cd59d7fd172774`
- `src/persistence_study.py`: `3028d8ce223fb5f253aac2258c6569d19eb07b82bf032921f9c449912684b395`
- `src/approve_persistence_canary.py`: `61bfa8de6a52a8d48f5c7170179e7aa54b63f9df5178215ede8ec0bd7632a8a6`
- `src/approve_canary.py`: `f260bbca8bb208f131aca4605cab8e27cd3d51aa2952565862d49e4f037330eb`
- `src/environment.py`: `064d5c7456d74651d373d2582df085b363bf05edbf06530e1eff1ba2c8946779`
- `src/agent.py`: `9ab110dd0496f87b187f533f35c1ee57de07ed51597124778838d6ebf1ebd55e`
- `src/orchestrator.py`: `4f532ded75d2a2c7e6adc61fe990696be322bac6593b7548e458c72d3d1b4c97`
- `src/event_store.py`: `e7903e82b22fef50d1fa3aaf102ac120da322c4e78716a10aefc22cbdd57112c`
- `src/evidence.py`: `832a65c4ce3af9d42ef4f810c6e20c8432b5a011c9fe42c918d1843ed2db41a0`
- `src/verify_run.py`: `eb5ee12e1e5a4471f3e49b03ec7b6dcad5276d3ec24b246e7afaa1b42c6a9c10`
- `tests/test_persistence_study.py`: `8871aa4e955fe3620589c0922249129081a44453d92cf638b843d75f748b120c`
- `tests/test_phase1_instrument.py`: `38f56a8d324b71f2f8c69b6fc88bad7572e22566a82f9108c25548a44a0668c4`
- `evidence/study-public-key.pem`: `a5080616312615964753595b815f852be009b8f79f17c06e49ba71979e16197d`
