# Cross-Wave Persistence Extractor Correction

Status: **post-analysis correction; preregistered primary result unchanged**

## Scope

The frozen `persistence_extract.py` descriptive counter required
`audit.task_relevant` on a read event. Production read events instead record the
artifact's origin wave in `result.wave`; task relevance is established later by
the correct submission's signed `audit.qualifying_reads` list.

The frozen extractor remains unchanged. `persistence_extract_v2.py` adds three
separate mechanical fields:

- `wave2_raw_reads_from_wave1`: every successful wave-2 read whose result says
  the artifact came from wave 1;
- `wave2_qualifying_reads_from_wave1`: earlier reads that are referenced by a
  later correct submission's signed qualifying-read audit;
- `wave2_agents_succeeding_from_wave1`: wave-2 agents with at least one such
  read before their correct submission.

V2 fails closed if its reconstruction of successful wave-2 agents disagrees
with the frozen primary `wave2_success_from_wave1` endpoint.

## Corrected sealed-data extraction

### Persistent store, 20 runs

- Wave-1 task-relevant write: **20/20 runs**
- Raw wave-2 read of a wave-1 artifact: **20/20 runs**
- Raw cross-wave reads: **135**
- Qualifying cross-wave read supporting success: **12/20 runs**
- Qualifying read references: **21**
- Wave-2 success from wave-1 evidence: **12/20 runs**

### Erased store control, 20 runs

- Wave-1 task-relevant write: **19/20 runs**
- Raw wave-2 read of a wave-1 artifact: **0/20 runs**
- Qualifying cross-wave read supporting success: **0/20 runs**
- Wave-2 success from wave-1 evidence: **0/20 runs**

The corrected reconstruction exactly reproduces the frozen primary result and
does not change the confirmatory verdict, effect size, interval, or p-value.

## Audit bindings

- Frozen signed study-manifest digest: `04158e8ae753d15a33eb01deeea363c866865cabf8166a9470b3882dd6d0e04a`
- Public pre-analysis evidence anchor: <https://github.com/joesbobclaw/agent-swarm-harness/commit/3331433aefe736f811ecb57cf9885f03c7711245>
- Frozen v1 extractor SHA-256: `b93419bf8f473279468917eef5ad9ee9c910f142baf4c421ce0b2d58e8c3574e`
- Corrected v2 extractor SHA-256: `be17e87683a1ac91e143395574d52cb72493d9f93c2312662ff44fc0eeb1a555`
- Published V2 regression test SHA-256: `095ef3526406a9b0c8037e8318c399525261b54b28454608783251b536915583`
- Corrected extraction JSON SHA-256: `6f70b31abc4d7015f451bb399ce2762905dfeffa4ed4d966160ae641ba6290d8`

## Testing

Regression coverage includes the production event shape where a successful
read has `result.wave == 1` and an empty audit object, plus a negative control
proving that a read occurring after submission cannot qualify.
