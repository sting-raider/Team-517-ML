# Current result — September 26, 2026

**Submission 2 selected:** INT002 depth10 CatBoost, 53 features, cap160,
threshold0.65. Matched 5,000-anchor confirmation macro F0.5 is **0.940478**,
versus **0.927580** for the uploaded-v1 model on identical anchors.
India0.913639; US0.958045; singleton FPR5.818%. Full export is underway.
See [submission-2 evidence](SUBMISSION_2.md) and int002_depth10_confirmation.json.
Submission1 has public score0.898. No public/private score is known for submission2.

# Measured entity resolution results — 25 September 2026

**Historical cap-640 selection (not the uploaded first file):** 640 raw blocking candidates per anchor, 47 numerical
features, CatBoost depth 10, and threshold 0.625. On 4,389 calibration anchors it
scores **0.930679 macro F0.5**. A separate, previously untouched 5,000-anchor
confirmation sample scores **0.928835**, with entity-bootstrap 95% interval
**[0.924276, 0.933230]**. The uploaded first file instead used cap 160 and threshold 0.575, scoring 0.898 publicly. See
`submission_v1_confirmation.json`, `tuning.json`, and `retrieval_study.json`.

The 640-candidate pair recall on confirmation is **0.947246**, with an oracle macro
ceiling of **0.980951**. India scores **0.900722**; US scores **0.948339**.
These estimates do not cover French performance, since France has no labeled data.

The historical 30-candidate configuration's separate 5,000-anchor confirmation sample
scores **0.914759 macro F0.5**.
An entity bootstrap gives a 95% interval of **[0.909539, 0.920184]**. This interval
describes sampling uncertainty within the supplied training distribution; it does
not cover country shift, model-selection uncertainty, or private-leaderboard risk.

## Dataset audit

There are 24,229,173 source records: 12,527,040 training and 11,702,133 test.
Training has 2,206,821 reference entities and 10,320,219 searchable records.
Test has 1,732,544 reference entities, including 259,452 French entities (14.98%).
The overall training singleton rate is 5.5848%; predicting nothing is a weak baseline.

No missing labeled anchors/targets, duplicate labeled pairs, targets assigned to
multiple anchors, or cross-country positive links were found. Some S2/S3 addresses
are empty. The complete per-file/country counts are in `data_audit.json`.

## Measured experiments

| Experiment | Evaluation sample | Macro F0.5 | Candidate pair recall |
|---|---|---:|---:|
| Initial name-led retrieval + CatBoost | 3,051 development holdout anchors | 0.829099 | 0.718012 |
| Expanded address retrieval + CatBoost, cap 80 | Same development holdout | 0.921733 | 0.912795 |
| Historical lexical shortlist, cap 30 | Separate 5,000 confirmation anchors | 0.914759 | 0.896235 |
| Selected depth-10 matcher, raw cap 640 | Fresh 5,000 confirmation anchors | **0.928835** | **0.947246** |

These rows use different candidate configurations and the confirmation row uses a
different sample, so its score should not be interpreted as a paired 0.007 loss.
On the same 4,389 calibration anchors, the initial classifier scores 0.921486 with
80 candidates, 0.927373 with 640, and the historical 30-candidate shortlist scores
0.919908. The shortlist was withdrawn from deployment when quality became the
priority. The selected depth-10 classifier scores 0.930679 on 640 candidates.

Historical 30-candidate confirmation by country: **US 0.937055**, **India 0.881481**.
Singleton false-positive rate is **7.664% overall**, **4.848% US**, and **11.927%
India**. The candidate set for that experiment imposes an oracle macro-score
ceiling of **0.960220**. Perfect matching cannot recover links missing from it.

The matcher was fitted on approximately 18,000 anchors from a deterministic 30,000
anchor development sample, with every training S2/S3 record as retrieval inventory.
The rest of the development sample serves early stopping, calibration, and holdout.
No positives were inserted into candidate lists. Confirmation anchors are outside
the entire development sample. Training record IDs do not enter the feature vector.

## Unseen-country stress

With the expanded 80-candidate blocker:

| Matcher training labels | Evaluation country | Macro F0.5 |
|---|---|---:|
| US + India | India | 0.886178 |
| US only, threshold calibrated on US | India | 0.777201 |
| US + India | US | 0.945167 |
| India only, threshold calibrated on India | US | 0.907797 |

France has no provided labels. These tests demonstrate transfer risk and do not
establish a French score. The test set also has a different country mixture.

## Next experiments, in order

1. Inspect missed retrieval links on **development** anchors, separating name
   replacement, transliteration, missing addresses, and changed address numbers.
   Keep the confirmation sample out of further tuning.
2. Add a complementary character/phonetic or licensed multilingual retriever. Measure
   newly recovered links against its additional comparison and memory cost.
3. Train a larger, more varied matcher sample and a compact multilingual pair model;
   retain the existing numerical features for address/unit conflicts. Use a checkpoint
   with an explicitly compatible MIT/Apache 2.0 license and stay below the parameter cap.
4. Improve singleton precision and ambiguity handling with out-of-fold evidence.
   Current India singleton false merges are a specific weakness.
5. Compare any ensemble only after local validation; keep
   complete candidate exports for the exact final matcher inputs.

No AWS credits, external business lookup, geocoding, or external training records
were used. The local RTX 3060 was used to encode supplied text for an experimental
semantic feature that is not in the selected first submission. The first uploaded cap-160 file scored 0.898 publicly; historical scores above
must not be conflated with that submitted configuration.
