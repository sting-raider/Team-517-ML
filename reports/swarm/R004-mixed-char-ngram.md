# R004 — Mixed name+address character n-gram retrieval feasibility

## Recommendation

**FOLLOW-UP / BLOCKED for the actual retrieval claim.**

A bounded mixed character-probe design is feasible enough to justify a full S2/S3 benchmark, but this chat cannot validly measure retrieval recall or oracle gain because the connected Drive path rejects the complete Source-2 and Source-3 TSVs above 256 MiB. A GitHub Actions fallback also failed before any workflow step was allocated. No sampled target inventory was substituted.

## Hypothesis

A field-aware union of rare character 3–5 gram probes from business name and address can recover true S1→S2/S3 links missed by blocker v2, especially when exact/token keys fail under spelling, spacing, transliteration-like, or address corruption.

The bounded design tested here is: choose the four lowest-frequency character grams per field and use at most eight mixed probes per anchor. The experiment in this branch measures whether that probe budget is structurally plausible before a target-side inverted index is built.

## Change

Added:

- `tools/experiments/r004_char_probe_feasibility.py`
- `tests/test_r004_char_probe_feasibility.py`

The helper:

1. streams the complete train Source-1 file;
2. reproduces the repository's deterministic 30,000-anchor development population;
3. applies the exact `fold517` split and selects calibration anchors;
4. builds 3/4/5-gram sets over compact normalized name/address text;
5. estimates gram document frequency from a deterministic Source-1 proxy sample;
6. measures how many low-frequency probes are available per calibration anchor, with country and truth-cardinality slices.

It does **not** change blocker defaults or production scoring.

## Protocol

Data available losslessly in this chat:

- complete `train_source1.tsv`: 2,206,821 rows / 210,069,713 bytes;
- complete `train_ground_truth.tsv`: 127,015,583 bytes.

Unavailable as complete local files:

- `train_source2.tsv`: 489,301,488 bytes;
- `train_source3.tsv`: 503,705,637 bytes.

The Drive connector returned HTTP 413 because each target file exceeds its 268,435,456-byte raw-download limit.

An ephemeral GitHub Actions probe was attempted on PR #149 (run 36165064353, job 108170686585). GitHub created a failed workflow record but allocated zero executable steps, so no data were downloaded there either. The temporary workflow file was removed from the branch after documenting the failure.

### Exact anchor set

Development selection matches the repository:

```
ORDER BY md5('sample517:' || entity_id) LIMIT 30000
```

Fold assignment matches `src/ber/experiment.py::fold`.

Observed parity:

- full Source-1 rows scanned: **2,206,821**
- development anchors: **30,000**
- calibration anchors: **4,389**
- US calibration anchors: **2,635**
- India calibration anchors: **1,754**
- truth-cardinality 0 (singleton) anchors: **252**
- cardinality 1: **224**
- cardinality 2–4: **2,769**
- cardinality 5+: **1,144**

This matches the current retrieval-study population size and singleton count.

### Feasibility samples

Two independent deterministic Source-1 document-frequency proxy samples were used:

- seed `r004df517:`, n=50,000
- seed `r004df518:`, n=50,000

Each is 2.2657% of complete train Source-1. This is explicitly a **Tier-1 feasibility sample**, not a replacement for the complete target inventory.

The Python normalizer uses NFKD accent stripping, lowercase, Unicode alphanumeric retention, punctuation-to-space, then compacts spaces for character grams. It is a semantic proxy for the repository DuckDB `strip_accents` normalizer; therefore these frequency diagnostics are not claimed as exact blocker postings.

Commands:

```bash
python tools/experiments/r004_char_probe_feasibility.py \
  --source1 /mnt/data/train_source1.tsv \
  --truth /mnt/data/train_ground_truth.tsv \
  --out /mnt/data/r004-517.json \
  --df-sample-n 50000 \
  --df-seed r004df517:

python tools/experiments/r004_char_probe_feasibility.py \
  --source1 /mnt/data/train_source1.tsv \
  --truth /mnt/data/train_ground_truth.tsv \
  --out /mnt/data/r004-518.json \
  --df-sample-n 50000 \
  --df-seed r004df518:
```

Runtime environment: ChatGPT Linux x86_64 sandbox, Intel Xeon Platinum 8573C, 5 visible CPUs, ~5.8 GiB RAM.

## Correct current baseline

The relevant same-slice baseline is the committed **4,389-anchor calibration** retrieval artifact, not the separate confirmation score:

| Metric | blocker-v2 cap 640 |
|---|---:|
| Candidate pair recall | 0.9458627913 |
| Candidate entity recall | 0.9454912309 |
| All-matches-retrieved rate | 0.8411892676 |
| Blocking-oracle macro F0.5 | 0.9811781092 |
| Candidate count p50 | 597 |
| Candidate count p90/p99/max | 640 / 640 / 640 |

Because complete S2/S3 were unavailable, this run does **not** report a new value or delta for any of those metrics.

## Results

Across the exact 4,389 calibration anchors, the character-gram universe contained:

- **53,067** distinct name grams;
- **132,355** distinct address grams.

The proposed bounded probe is four rarest grams from each field, at most eight probes total.

### Two-seed stability

| Diagnostic | seed 517 | seed 518 |
|---|---:|---:|
| ≥4 mixed grams with proxy DF ≤1 | 92.5951% | 93.7343% |
| ≥4 mixed grams with proxy DF ≤5 | **99.5899%** | **99.6127%** |
| ≥4 mixed grams with proxy DF ≤10 | **99.9544%** | **99.9089%** |
| mixed 8-probe DF-mass p50 | 8.0 | 8.0 |
| mixed 8-probe DF-mass p90 | 55.2 | 56.0 |
| mixed 8-probe DF-mass p99 | 230.08 | 227.60 |
| mixed 8-probe DF-mass mean | 23.625 | 23.747 |

The DF≤1 statistic moves by 1.14 percentage points between samples, so it is sample-sensitive and should not be treated as a precise design threshold. The DF≤5/10 conclusions are much more stable.

For seed 517 alone:

- four rare address grams with proxy DF≤5 exist for **97.6077%** of anchors;
- four rare name grams with proxy DF≤5 exist for **63.6591%**;
- taking the mixed pool raises this to **99.5899%**.

This supports a field-mixed design rather than name-only character retrieval.

### Country slice

The mixed probe remains available in both labeled countries. With seed 517, the fraction having at least four mixed grams at proxy DF≤5 is:

- India: **99.7149%**
- US: **99.5066%**

India addresses have many more character grams (median 159 vs 72 in US), while their four rare address probes have low proxy mass. This suggests address character evidence may be especially useful for India, but **does not establish target-side recall**.

### Cardinality slice

The seed-517 mixed eight-probe DF-mass mean is similar across truth cardinalities:

- singleton / |T|=0: 22.03
- |T|=1: 23.59
- |T|=2–4: 23.49
- |T|≥5: 24.30

There is no obvious Source-1-side probe-availability collapse for high-cardinality anchors.

### Runtime / memory

Seed-517 run:

- **23.26 s** wall
- **226,936 KiB** max RSS

Seed-518 run:

- **23.32 s** wall
- **226,668 KiB** max RSS

The restructured committed helper reproduced the seed-517 aggregate output exactly on the measured fields in **19.74 s**, ~227 MiB max RSS.

Focused unit tests: **4/4 pass**.

## Error analysis / what this does not prove

1. **S1 frequency is only a proxy.** Candidate cost is determined by S2/S3 posting lists, not Source-1 document frequency. A gram absent from the 50k S1 sample can still be common in target sources.
2. **No target text means no positive recovery measurement.** We cannot know whether rare S1 grams survive corruption into the true S2/S3 match.
3. **The strict DF≤1 diagnostic is unstable.** It shifted by ~1.14 pp across two equally sized deterministic samples. Design decisions should not hinge on that cutoff.
4. **Normalizer is a semantic mirror, not byte-for-byte DuckDB parity.** Full target benchmarking must use the repository's actual normalized columns.
5. **Candidate cap interaction is unmeasured.** R004's purpose is gain at a bounded cap; unioning new candidates can displace baseline positives. Only the exact cap-640 same-slice benchmark can decide this.

## Red-team checks

- No entity ID is used as a predictive feature. IDs are used only for deterministic sample/fold assignment, matching repository protocol.
- Ground truth is used only for aggregate cardinality slicing, never to select grams or candidates.
- No positive target is inserted into candidate sets.
- No confirmation or frozen holdout was consumed.
- No external business registry, search, maps, geocoding, or entity-resolution service was used.
- No raw challenge rows or row-level diagnostics are committed.
- The 50k proxy sample is explicitly identified as a sample with size and deterministic seed.
- Same-slice baseline metrics come from the existing committed 4,389-anchor retrieval artifact; no mismatched confirmation metric is presented as the comparator.

## Interpretation

The feasibility question is answered positively: a **fixed, small mixed-field character probe budget is structurally plausible**, and the result is stable at practical DF thresholds across two independent Source-1 samples. Address grams materially improve rare-probe availability over name-only grams, including in India.

The competition question is **not** answered: whether these probes recover missing positives and raise the 0.981178 calibration oracle at cap 640 remains blocked on complete S2/S3 access.

## Risks

- target-source gram fanout may be much larger than the S1 proxy;
- character grams may be highly correlated and add little unique recall;
- accent folding can create collisions, especially relevant to France;
- an unweighted union may crowd out stronger blocker-v2 candidates under the fixed cap;
- micro gains will require paired same-anchor analysis and candidate provenance to be credible.

## Follow-up

Recover R004 in a runtime with complete S2/S3 access and:

1. build source-specific target DF for normalized name/address 3–5 grams;
2. query only a small rare-probe budget per field, starting with four + four;
3. union with blocker-v2 while preserving total cap 640;
4. reproduce the baseline exactly on the same 4,389 anchors before accepting any delta;
5. report required retrieval metrics, candidate quantiles, US/India/source slices, marginal recovered/lost positives, runtime, and memory;
6. compare name-only, address-only, and mixed channels using the same candidate accounting.

Do not promote a production blocker change from this feasibility result alone.
