# F005R — independent red-team replication of common-name hard negatives

**Issue:** #114  
**Target:** F005 / PR #57  
**Branch:** `agent/i/F005R-common-name-redteam`  
**Recommendation:** **PROMOTE F005 forensic result** (no model change implied)

## Hypothesis
The strongest F005 aggregate findings should reproduce from the complete supplied training Source-1 inventory and ground truth using an implementation independent of the F005 DuckDB helper. The most important claim to validate is that same-normalized-name hard negatives almost always disagree on first address number, because that evidence motivates rare-number retrieval/matcher work.

## Change
No production matching/retrieval code changed. This is a deliberate independent replication. The analysis was implemented in the ChatGPT Python runtime with pandas/grouped arithmetic rather than importing or executing `ber.common_name_audit`.

## Protocol
- Inputs: complete `/mnt/data/train_source1.tsv` (210,069,713 bytes) and `/mnt/data/train_ground_truth.tsv` (127,015,583 bytes), streamed from the supplied Google Drive.
- Population: all 2,206,821 training Source-1 anchors; no sampling.
- Name normalization: lowercase; accent-fold; replace non-alphanumeric runs with spaces; trim. Before using the ASCII fast path, the replication independently verified **0 non-ASCII business-name rows**, matching F005's parity premise.
- Address normalization: same conceptual accent-fold/non-alphanumeric normalization, with an ASCII vectorized path and Unicode fallback. The replication independently counted **554 non-ASCII address rows**, also matching F005.
- Same-name group key: `(country, normalized_business_name)`.
- Pair counts: exact combinatorial counts `n*(n-1)/2`; same-address and same-first-number pairs computed from subgroup counts rather than enumerating row pairs.
- Singleton audit: entity IDs used only to join each Source-1 row to its own supplied truth row; IDs were not predictive features.
- Confirmation/frozen holdouts: not touched.
- External identity data: none.
- Runtime: 26.30 s end-to-end in this container after releasing heavy intermediates before loading truth; Source-1 CSV read 4.17 s.

## Baseline
F005 / PR #57 reported:
- normalized repeated-name collision rate 0.392484 overall, 0.443978 India, 0.358124 US;
- 8,869,036 unordered same-name pairs;
- 8,324,084 first-number-comparable pairs;
- 8,288,072 first-number conflicts, conflict rate 0.995674;
- >20-frequency groups produce 89.33% of same-name pair burden;
- singleton collision rate 39.2561% vs non-singleton 39.2479%.

## Results
| Metric | F005 reported | F005R independent | Difference |
|---|---:|---:|---:|
| Raw lowercase+trim collision rate | 0.383091 | 0.3830913336 | +0.0000003336 |
| Repo-style normalized collision rate | 0.392484 | 0.3924835771 | -0.0000004229 |
| India normalized collision rate | 0.443978 | 0.4439779526 | -0.0000000474 |
| US normalized collision rate | 0.358124 | 0.3581241930 | +0.0000001930 |
| Same-name unordered pairs | 8,869,036 | 8,869,036 | **0** |
| Number-comparable pairs | 8,324,084 | 8,324,084 | **0** |
| First-number conflicts | 8,288,072 | 8,288,072 | **0** |
| First-number conflict rate | 0.995674 | 0.9956737582 | -0.0000002418 |
| Groups with frequency >20, share | 4.45% | 4.4488337% | rounding only |
| Pair burden from frequency >20 groups | 89.33% | 89.3289192% | rounding only |
| Singleton collision rate | 0.392561 | 0.3925612794 | +0.0000002794 |
| Non-singleton collision rate | 0.392479 | 0.3924789808 | -0.0000000192 |

Additional exact checks:
- normalized repeated-name groups: **180,744**;
- anchors in those groups: **866,141**;
- same normalized-address pairs inside same-name groups: **0**;
- different normalized-address same-name pairs: **8,869,036**;
- India first-number conflict: 2,775,128 / 2,808,570 = **0.9880928729**;
- US first-number conflict: 5,512,944 / 5,515,514 = **0.9995340416**;
- singleton-minus-non-singleton collision difference: **+0.0082299 percentage points**.

All headline count claims reproduced exactly. Rate differences are solely the expected consequence of F005 reporting rounded decimals.

## Error analysis / adversarial checks
1. **Normalization parity:** independently confirmed the two F005 assumptions that matter for parity: zero non-ASCII names and 554 non-ASCII addresses. The exact count results reproduce, making a hidden normalization mismatch unlikely.
2. **Pair arithmetic:** same-name pair totals were recomputed from frequency groups, while number conflict was recomputed from per-group first-number multiplicities. The exact counts match F005 without enumerating its pairwise implementation.
3. **Singleton join:** the truth file contains exactly 2,206,821 unique Source-1 rows, matching Source-1. The independent singleton count is 123,247, consistent with the established corpus audit.
4. **Country slices:** US and India counts independently sum to the full population and reproduce F005's group/pair statistics.
5. **No metric leakage:** this is a corpus forensic replication only; no candidate or matcher score is produced, so no official F0.5 gain is claimed.

## Interpretation
F005's main forensic conclusion is reliable: exact/common normalized names create a very large hard-negative family, and **first-address-number conflict is almost universal when both rows expose a number**. This supports using number conflict/common-name frequency as candidate ambiguity evidence and strengthens the rationale for R007/M003-style number-aware work.

The singleton sub-hypothesis is also robustly negative. Common-name collision alone is effectively useless as an anchor-only singleton gate; the overall gap is only +0.00823 percentage points.

## Risks
- This validates Source-1 hard-negative structure, not how often the current CatBoost actually commits these false positives.
- It does not measure positive-link number stability because S2/S3 target files are unavailable in this runtime.
- It does not justify weakening exact-name retrieval; doing so could hurt recall.

## Recommendation
**PROMOTE the F005 forensic result as independently replicated.** Follow up with an unchanged-candidate matcher experiment that adds normalized-name frequency/commonness interactions with address-number conflict, and with targeted hard-negative mining from high-frequency same-name groups. Keep any retrieval change gated on paired recall/oracle measurements.