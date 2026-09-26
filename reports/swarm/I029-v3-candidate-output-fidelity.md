# I029 — INT003 candidate-output boundary and subset fidelity audit

## Scientific question

Does the promoted INT003 full-test export write exactly the final fused cap-160
candidate set that the matcher scored, and are accepted matches guaranteed to be
a subset of the submitted `candidate_pairs.tsv` under batching, resume, partition,
and merge paths?

This matters because the final challenge package includes both
`matching_results.tsv` and `candidate_pairs.tsv`. A format-valid file is not
enough if it represents a different candidate boundary from the one used by the
matcher.

## Scope and protocol

Tier-0/1 source + committed-artifact audit on latest main
`f08c041b274e58ae900620ac714ec8a0a06f09b0`.

Audited:

- `src/ber/blocking.py`
- `src/ber/retrieval_v3.py`
- `src/ber/v3.py`
- `src/ber/predict.py`
- `src/ber/shortlist.py`
- `src/ber/validate.py`
- `modal_v3.py`
- `modal_app.py`
- `reports/int003_depth10.json`
- `reports/int003_depth10_export.json`
- `reports/SUBMISSION_3.md`

No challenge rows, labels, model probabilities, confirmation/frozen holdout,
threshold tuning, France pseudo-labels, leaderboard feedback, or external entity
data were consumed.

## Result

**PROMOTE the current INT003 candidate export path past this integrity gate.**

The submitted candidate file is sourced from the exact rows passed to matcher
inference. The matching file is a thresholded subset of those same rows. I found
no pre-fusion, pre-cap, separately reconstructed, or stale candidate pool in the
v3 scoring/export path.

The existing cloud validator also verifies prediction-subset, duplicate, row
coverage, and file-order invariants. One narrower validation gap remains:
`validate()` does not itself enforce the configured per-anchor candidate cap.
That means a validator PASS alone does not prove cap-160. Current source
semantics do prove it, so this is a guardrail opportunity rather than evidence
that the promoted output is wrong.

## Candidate membership trace

### 1. Both retrieval indexes contain target-side records only

The lexical index in `blocking.build_index()` is built with `source>1`.
The v3 character index in `retrieval_v3.build_char_index()` uses the same
target-side restriction.

Candidate target IDs therefore originate from supplied S2/S3 inventory rows,
not from a free-standing ID reconstruction.

### 2. Fusion creates one final bounded set

`fused_candidates()` first obtains:

- lexical candidates at cap 160,
- character candidates at cap 64.

It unions the channels, groups by `(anchor, rid)`, aggregates the fused RRF
score and channel evidence, joins the supplied split to resolve the target row,
then applies one final:

`row_number() OVER(PARTITION BY anchor ORDER BY retrieval DESC, entity_id) <= 160`

The resulting `batch_candidates` table is therefore deduplicated and bounded
to at most 160 targets per anchor before feature construction.

The documented R026 caveat remains: target ID breaks final hard-cap ties.
That can affect *which* tied candidate survives, but it does not create a
different export boundary from the one actually scored.

### 3. Pair features read the same candidate table

For feature version 3, `predict.score_batch()` invokes
`v3.pair_query(split, anchor_table, candidate_table)`.

The `candidate_table` argument is the exact `batch_candidates` table created
by `fused_candidates()`. There is no second retrieval call or export-specific
candidate reconstruction between fusion and scoring.

### 4. The shortlist stage is an identity operation for INT003

The saved v3 training/config path fixes:

- `candidate_cap = 160`
- `shortlist_cap = 160`.

`shortlist_rows(rows, cap)` immediately returns `rows` unchanged whenever
`len(rows) <= cap`.

Because `fused_candidates()` has already enforced at most 160 rows per anchor,
the INT003 shortlist cannot remove or replace any candidate. Consequently the
model scores every final fused candidate.

This is important: `candidate_pairs.tsv` is not a larger blocker pool that
contains unscored rows, nor is it a post-hoc shortlist reconstructed after
model inference.

### 5. Export is built directly from scored rows

Inside `score_batch()`:

- `considered[anchor]` receives every target paired with a model probability,
- `selected[anchor]` receives only targets whose probability is at least the
  frozen threshold.

The shard writer then writes:

- `matching_results.tsv` from `selected`,
- `candidate_pairs.tsv` from `considered`.

Therefore `matching_results[anchor] ⊆ candidate_pairs[anchor]` holds by
construction, and candidate export membership equals scored membership.

## Resume and shard integrity

The resume path is also coherent:

- `run.json` binds model SHA256, complete config, cap, batch size, limit,
  database path, index version, and partition identity.
- Reusing an output directory with a different run identity fails.
- Each completed shard stores SHA256 for both output TSVs.
- A resumed run verifies those hashes before accepting a completed shard.
- Incomplete shards are recomputed from the same run identity.

Thus a partially resumed v3 run cannot silently combine completed shards from a
different model/config/cap under the same output directory.

## Partition and final merge integrity

Each partition constructs its Source-1 universe in entity-ID order. Shards are
written in that order and concatenated in sequence.

The generic `merge_score()` then heap-merges partition files by Source-1
entity ID, requires identical headers, and runs `ber.validate.validate()` over
the merged pair.

The validator checks:

- exactly one row for every Source-1 entity in sorted order,
- no duplicate target IDs within a row,
- target-ID format,
- prediction set is a subset of candidate set,
- no extra output rows.

For the promoted INT003 export, the committed receipt reports:

- 1,732,544 Source-1 anchors,
- 264,828,881 candidate pairs,
- 5,819,438 predicted matches,
- 102,598 empty predictions,
- status PASS.

The recorded candidate SHA256 is
`56333f15abb4eecc99d11db07b8a5a4d56d7b2763fd7b1727a6c0debe7a195e3`.

## Validation caveat

`validate()` accepts the candidate file and counts candidates, but it does not
take the configured candidate cap and does not reject a row solely because it
contains more than 160 candidates.

So the statement "cloud validator PASS proves cap-160" would be too strong.

For current INT003, cap-160 is instead established by the audited generation
path: the final fused SQL applies the cap before pair-query/scoring, and export
uses exactly the scored rows. The export receipt's 152.86 mean candidates per
anchor is consistent with that path but does not independently prove the
per-anchor maximum.

A future integration-hardening patch could make `validate()` accept an optional
`max_candidates` and have Modal pass the configured cap. That would turn the
current source-level proof into an explicit output-file assertion. This audit
does not change production code because no current-output defect was found.

## Red-team checks

- No separate candidate retrieval occurs during TSV writing.
- No pre-fusion lexical or character table is exported.
- No pre-cap union is exported.
- The shortlist does not alter membership at INT003's equal 160/160 caps.
- Matches and candidates share the same anchor-keyed in-memory mappings.
- Completed shard reuse is checksummed and bound to the same run manifest.
- Partition merge is by anchor ID, not raw concatenation order.
- Candidate IDs come from target-side supplied inventory joins.
- The final validator explicitly enforces match-subset and duplicate invariants.
- Exhaustive target-ID existence checking was disabled in the cloud merge
  receipt, but the retrieval/index lineage already restricts candidate rows to
  supplied target inventory. This is a validation-strength caveat, not evidence
  of unknown IDs.

## Recommendation

**PROMOTE** current INT003 candidate-output semantics. No submission artifact
needs regeneration because of this audit.

For research-throughput/integration safety, a separate small infrastructure
patch may add a per-anchor `max_candidates` assertion to `ber.validate`.
That would improve future failure detection, but it should not be confused with
a measured modeling improvement or a defect in the frozen INT003 output.

Safe to merge independently: yes. This report changes no retrieval, matcher,
threshold, or export behavior.
