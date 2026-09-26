# INT005 / D017 — learned representation and competing owner filter

## Hypothesis

V3 scores each S1–target pair independently. The supplied training truth assigns each S2/S3 target to exactly one S1 owner, while the submitted v3 file assigns 99,661 test targets to several S1 owners. France alone has 78,398 conflicted targets and 210,488 assignments beyond the first owner. A representation trained on labeled matching records can help identify implausible owners, especially when many S1 businesses have the same name at different addresses.

This is a structural observation, **not** a verified test-label constraint or a French accuracy estimate.

## Change

`src/ber/dense_training.py` trains a 117.65-million-parameter MIT-licensed multilingual E5-small checkpoint, pinned to revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`, on 102,125 existing INT003 fit anchors. Training uses all labeled positive fragments for those anchors, two hard negatives mined from the frozen v3 candidate pool, and in-batch contrastive negatives. Inputs contain only supplied business names and addresses; IDs identify examples and labels but do not enter model text.

`src/ber/ownership.py` retrieves up to 32 competing S1 records for each v3 predicted target from the **complete** clean training inventory, using the existing lexical/character blocker in reverse. It always includes the original predicted owner, even if reverse retrieval misses it. The owner filter retains a v3 predicted edge when its dense cosine similarity is within 0.05 of the strongest owner. This can abstain from pruning close ties.

For the test export, `src/ber/conflict_filter.py` applies the same frozen encoder and 0.05 margin only to targets already claimed by several v3-selected owners. It removes weaker claims. All retained matches remain a subset of the original v3 candidate file, which is therefore the exact final blocking artifact for this variant.

The [SC-Block paper](https://arxiv.org/abs/2303.03132) motivates contrastive record representations and nearest-neighbor blocking. The [Faiss documentation](https://github.com/facebookresearch/faiss/wiki/Faiss-indexes) describes the IVF scalar-quantized full-inventory ANN experiment in `src/ber/dense_retrieval.py`. Neither paper provides a score estimate for this challenge.

## Protocol

- Encoder: one L4, batch 48, one epoch, 2,128 steps, 371 seconds. Initial/final 50-step mean training losses 1.6013/0.0984. Training loss alone is not accuracy evidence.
- D017: same 4,389 calibration anchors and 3,051 reused development holdout anchors as v3; complete S1 competitor inventory; v3 prediction threshold 0.625; dense margin selected on calibration only at 0.05, then frozen for holdout and test.
- Only supplied data. No French labels. No external business records or identity lookups. No IDs used as predictors.
- The reverse-owner calibration/holdout protocol has a broader competitor set than the test conflict-only export. The local gains validate the learned owner *signal*, not the exact test export end to end.

## Results

| Set / country | V3 macro F0.5 | Reverse-owner dense 0.05 | Gain |
|---|---:|---:|---:|
| Calibration, all | 0.949121 | 0.953049 | +0.003928 |
| Calibration, India | 0.931688 | 0.939118 | +0.007430 |
| Calibration, US | 0.960726 | 0.962322 | +0.001596 |
| Holdout, all | 0.944783 | 0.948116 | +0.003333 |
| Holdout, India | 0.917541 | 0.925187 | +0.007646 |
| Holdout, US | 0.962737 | 0.963228 | +0.000491 |

At the frozen 0.05 margin, calibration removes 83 false edges and 21 true edges; holdout removes 60 false edges and 21 true edges. Calibration singleton false-positive rate drops 6.35% → 4.37%; holdout drops 10.55% → 9.55%. A plain address-only rule removed many more true edges and was rejected.

The test conflict-only export removes 212,049 of 5,819,438 v3 predicted edges. By country, v3 → filtered edge counts are France 1,130,876 → 938,641; India 2,495,140 → 2,478,928; US 2,193,422 → 2,189,820. French predictions per S1 drop 4.359 → 3.618. This is an unlabeled distribution check, **not** a French F0.5 measurement. The filtered matching file is `output/submission_v4_d017_conflicts/matching_results.tsv` locally and `project/output/submission_v4_d017_conflicts/matching_results.tsv` in the private Modal volume; SHA-256 `86e394a10dd7b0bec62ed95115bf56aa31a3336768d9657f3cc3041bbac7d8ea`. It contains 1,732,544 S1 rows and passes the organizer's matching-file validator. The original validated v3 candidate file stays in the private volume with SHA-256 `56333f15abb4eecc99d11db07b8a5a4d56d7b2763fd7b1727a6c0debe7a195e3`.

The full **4,133,346-record India train S2/S3 inventory** was encoded in four shards and indexed with Faiss IVF2048-SQ8. On 1,754 calibration anchors, adding the global dense top 16 to original v3 candidates while retaining a hard cap of 32 raises the blocking oracle 0.969196 → 0.992386; candidate pair recall 0.918060 → 0.974762. On 1,212 separate India holdout anchors, the oracle is 0.965995 → 0.991419. At cap 160 with 64 dense slots, calibration oracle reaches 0.997304. A compact version that only computes v3 fused top 32 before adding 16 dense records still reaches 0.992075 calibration / 0.990414 holdout oracle at cap 32. These are **oracle scores with truth-selected decisions**, not actual matcher F0.5. The US inventory and exact combined matcher evaluation are in progress.

## Risks and recommendation

The public v3 score was reported by the user as 0.917; no v4 public score is available yet. The large French conflict count makes this export a plausible substantial improvement, but only a leaderboard submission can measure it. The conflict-only test action has no exact local counterpart because full-inventory train predictions for all 2.2 million S1 anchors have not been produced. Keep v3 available and compare the public score before making v4 the final selection.

The existing v3 blocker caps the measured full-pipeline oracle near 0.981 on the confirmation set. INT005 shows a large India recall gain at 32 candidates, but US replication, actual matcher performance on the new pairs, and France transfer must be checked before promoting a new submission. The smaller candidate set also addresses the organizer's final-ranking efficiency criterion if the test pipeline reproduces it.
