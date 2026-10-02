# M017 — multilingual pair cross-encoder

## Hypothesis

The v3 numeric matcher still leaves about 0.031 macro F0.5 below its blocking oracle on the frozen confirmation. A pretrained multilingual model that reads both complete name/address records together may distinguish aliases, address variants, and lookalikes that individually engineered similarities confuse.

## Change and protocol

`src/ber/crossencoder.py` fine-tunes [`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1), pinned to revision `1427fd652930e4ba29e8149678df786c240d8825`. The live model card and API reported Apache-2.0 and 117,641,089 parameters. The model receives only supplied business names and addresses. IDs are used solely to join records and labels.

Training reuses INT005's fit-only hard-negative JSONL: 102,125 fit anchors; up to two positive fragments and two frozen-v3 hard negatives per anchor; 402,483 pairs total, of which 198,324 are positive. One L4 GPU ran all 12,578 steps in 1,289.6 seconds at batch 32 and max sequence length 160. Mean loss for the first/last 100 steps was 1.4312/0.0863, which is training diagnostics only.

All **actual v3 candidate pairs** for the 4,389-anchor calibration and separate 3,051-anchor development holdout were scored. A fixed ensemble takes `logit(v3 probability) + cross-encoder logit`; the calibration-only F0.5 search chose an ensemble threshold of 0.775. The same formula and threshold were then applied to holdout. Candidate generation and candidate count remain exactly v3 for this isolated matcher measurement.

## Results

| Slice | V3 | M017 selected | Gain |
|---|---:|---:|---:|
| Calibration, all | 0.949121 | 0.970451 | +0.021330 |
| Holdout, all | 0.944783 | 0.965287 | +0.020504 |
| Holdout, India | 0.917541 | 0.952212 | +0.034671 |
| Holdout, US | 0.962737 | 0.973904 | +0.011167 |

The cross-encoder alone scored 0.956790 on holdout. The selected ensemble consistently outperformed it. Pair recall is unchanged on this experiment because the pool is unchanged; the neural retrieval experiment is measured separately.

## Risks and recommendation

These are existing, repeatedly used development folds; no new independent confirmation was consumed. France has no labels, so the French gain is unknown. Full 160-pair cross-encoder inference on 1.73 million test anchors would be expensive, so the next step is to score a smaller candidate pool formed by the INT005 ANN retriever and lexical blocker, tune on calibration, and verify on holdout. The final audit candidate file must contain every pair passed into that reranker. The model checkpoint is kept only on the private Modal volume; `modal run modal_crossencoder.py` recreates it from challenge labels and the pinned licensed base model.

Recommendation: **promote the matcher component for integration**, subject to the capped-candidate end-to-end result and full-test runtime.
