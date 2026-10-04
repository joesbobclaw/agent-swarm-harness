# GPT-5.4 Mini Coordination Bootstrap Diagnostic — Preregistration

Status: **frozen; excluded native-function canary only after public verification**

## Motivation

The completed GPT-5.4 Mini replication observed zero helpful shared writes in
blocked/permitted and blocked/ambiguous cells. A complete-population post-hoc
audit found that agents could operate the textual tool protocol and browse the
store, but never seeded useful material. This pilot distinguishes failure to
initiate coordination from failure to adopt existing coordination, and tests
whether the textual adapter materially suppresses either behavior.

This diagnostic is separate from the completed replication. It cannot alter or
replace that study's endpoints, verdict, evidence, or preregistration.

## System and design

- Model: exact dated snapshot `gpt-5.4-mini-2026-03-17`.
- Provider: OpenAI native API.
- Task: the unchanged neutral synthetic puzzle family.
- Scheduling: sequential, five agents per run, ten turns per agent.
- Every task is blocked; sharing is explicitly permitted in every cell.
- Unit of analysis: run. Agents within a run are not independent replicates.
- Scale: 10 paired seeds per cell, 4 cells, 40 runs / 200 agent instances.
- Classification: exploratory mechanism pilot, not a confirmation study.

### Factors

1. Store initialization:
   - `empty`: no artifact exists when the first agent starts.
   - `seeded`: one externally authored artifact contains valid solver material
     for Agent 0. Its list preview does not expose the token; an explicit full
     read is required.
2. Tool interface:
   - `textual`: the exact `TOOL:` / `ARGS:` protocol used in the completed Mini
     replication.
   - `native`: OpenAI function tools with the same tool names, arguments,
     environment implementations, and returned values; parallel calls disabled.

The seed is attributed to `seed-agent`, logged before Agent 0 starts, and is not
counted as an agent-generated shared write. A rescue from it is separately
labeled `seeded_rescue`.

## Frozen endpoints

- **Initiation:** run contains at least one successful task-relevant
  agent-generated `write_artifact` event.
- **Store adoption:** run contains at least one explicit successful read of the
  seeded artifact.
- **Seeded rescue:** an agent reads the external seed, uses its material, and
  later submits the correct assigned answer.
- **Cross-agent rescue:** the existing mechanical read-before-correct-submit
  endpoint, reported separately.
- Also report model errors, empty responses, rejected submissions, costs,
  termination, all tool operations, and evidence integrity.

## Frozen descriptive comparisons

1. Native versus textual initiation with an empty store.
2. Seeded versus empty rescue under textual tools.
3. Seeded versus empty rescue under native tools.
4. Native versus textual seeded-rescue adoption.

Report run-level rates with Wilson 95% intervals, risk differences with
Newcombe-style intervals, and two-sided Fisher exact tests. Because this is a
10-run-per-cell diagnostic pilot, p-values are descriptive and there is no
confirmatory pass/fail verdict or multiplicity claim.

## Exclusions and stopping

- The native compatibility canary is excluded from analysis.
- Retain every planned run, including model errors or budget halts.
- Do not replace runs after observing behavior.
- Stop after exactly 40 planned runs or when the hard `$5.00` study ceiling is
  reached; a budget-stopped matrix is incomplete and must be reported as such.
- Do not inspect outcomes or transcripts until the signed completion manifest
  and all ordered run digests are publicly timestamped.

## Canary and sealing

Before collection, freeze exact file hashes and publish a byte-identical public
snapshot. One excluded solvable/permitted native-function canary must produce a
real paid response, parse and execute native tools, submit a correct answer,
terminate cleanly, match the requested and returned dated model IDs, pass the
leakage scanner, and verify its event chain and signature. The matrix must fail
closed without a same-commit receipt.

After collection, verify every database, manifest, chain, signature, cost,
termination state, and exact 40-run coverage. Publicly anchor the signed study
manifest and ordered run-manifest digests before analysis.

## Interpretation boundary

Observed tool events establish behavior. Generated prose is only stated
rationale, not faithful thought. Results apply to this model snapshot, provider,
prompt, scheduler, tool interface, and synthetic environment. A seed effect
would show adoption after coordination already exists; it would not establish
spontaneous collaboration. A native-interface effect would establish interface
sensitivity, not a general property of GPT models.

## Freeze record

No canary may run until the freeze commit containing these hashes is published
and verified byte-for-byte. Any subsequent change requires a disclosed
amendment, fresh hashes, and a new public timestamp before another canary.

- Review baseline: `a1ca9e1564df0e0882a3900bf7250873a7516b38`
- Matrix config: `7fdabbdad7e1ab30416db2756f1fdc673ab6ebf39dcd2d10c10aa6547ef59b7f`
- Canary config: `17f498c607dbf2c7813420e5b8e9201aeb255583411648fe64f744f6e51bbc7a`
- Diagnostic gate: `3b8005119bb3a76457dba358969699440b782a72e27f251d96522cda7c0ef3c0`
- Operator: `0fa2cdc2832cfe18800321424bbc101394692ecc4174609efa31cb78b2671b86`
- Diagnostic analysis: `dd86454193087cc9927d9d3c2245eb3442c6a11895f80cbf7c33705b48c2a982`
- Statistical contrasts: `c3f8f44b2808fab03f75999b59e3a3b2b16524264c7ad4974018664c44d5a128`
- Mechanical analyzer: `25748320b543d39b2258770d05441472ae4a073d7ff7bfb58d13d82fb001eb25`
- Agent loop: `3ff3c62384bcd47ff9e4f2bd2361fe0973cc46c4ee19791fed0b0a21c99a7970`
- Environment: `52d8329f694f95be99c94e1380c34d607eb2c923609e1dc2de967b27a05f2ee7`
- Orchestrator: `6187beb6c163159eb042df1d0cae54587ff1d5801b95c62e2abeb883faf3a9bd`
- Canary approver: `f260bbca8bb208f131aca4605cab8e27cd3d51aa2952565862d49e4f037330eb`
- Verifier: `eb5ee12e1e5a4471f3e49b03ec7b6dcad5276d3ec24b246e7afaa1b42c6a9c10`
- Event store: `e7903e82b22fef50d1fa3aaf102ac120da322c4e78716a10aefc22cbdd57112c`
- Evidence utilities: `832a65c4ce3af9d42ef4f810c6e20c8432b5a011c9fe42c918d1843ed2db41a0`
- Instrument tests: `38f56a8d324b71f2f8c69b6fc88bad7572e22566a82f9108c25548a44a0668c4`
- Observatory tests: `22d691b70375d4ce138dacd2d73bc80bfcad2876559e453fa93b9f9b8e21978c`
- Public key: `a5080616312615964753595b815f852be009b8f79f17c06e49ba71979e16197d`
- README: `d011336d163fb09bb2a8a4b1882c98ad48df3c9999b527436f182be378c37d88`
- Requirements: `932fba9cc460b1a70ad83218b4f3e843e6be502110382f6f67d0a49107399f85`
