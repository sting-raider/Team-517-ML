# R023 — Hard frequency-cliff suppression of exact blocker keys

**Issue:** #107  
**Branch:** `agent/r/R023-frequency-cliff`  
**Baseline:** main `2a2ae6ec6de943ad7e38ecc0f0a95b53a0d7f460`  
**Recommendation:** **FOLLOW-UP**

## Hypothesis

Blocker v2 applies one hard posting-frequency eligibility rule, `freq <= 1000`, to every key family. That includes the two strongest exact-evidence families:

- `n:` compact normalized full business name, retrieval bonus **+50**
- `a:` compact normalized full address, retrieval bonus **+40**

If a pooled S2+S3 exact key has frequency 1000, it is eligible and can dominate the ranking. At frequency 1001 the same key is removed from both the index and query evidence. The hypothesis is that this discontinuity can suppress useful exact evidence and, under a bounded candidate cap, cause rank inversions that no downstream matcher can repair.

R023 asks only whether the structural failure mode is real. It does **not** claim that such keys occur often enough in the complete target inventory to improve challenge metrics.

## Change

Added an analysis-only helper:

- `src/ber/frequency_cliff.py`

and focused synthetic regression tests:

- `tests/test_frequency_cliff.py`

The helper mirrors blocker-v2's scalar score formula and hard cutoff. It also exposes an opt-in family-aware cutoff function for later experiments. Nothing is wired into production retrieval and the default blocker behavior is unchanged.

## Protocol

### Production behavior audited

On current main, `src/ber/blocking.py`:

1. creates pooled S2+S3 posting frequencies per hashed `(country, key)`;
2. builds the searchable index with `WHERE f.freq<=1000`;
3. applies the same `f.freq<=1000` condition to anchor query keys;
4. scores each matching key as:

```text
bonus(kind) + ln(10000001 / freq)
```

with bonuses:

| Key family | Meaning | Bonus |
|---|---|---:|
| `n:` | exact compact normalized full name | 50 |
| `a:` | exact compact normalized full address | 40 |
| `w:` | name token | 0 |
| `h:/z:/u:/v:/d:` | mixed/address/numeric evidence | 8 |

Final candidates are globally ranked over S2 and S3 and capped.

### Deterministic boundary audit

R023 evaluates the exact scoring expression at posting frequencies 999, 1000, and 1001. For 1001 it separately reports:

- the **current** result: ineligible / no hit;
- the **counterfactual smooth** score: what the unchanged logarithmic formula would have produced absent the hard cutoff.

### Synthetic cap-rank case

Two already-retrievable synthetic candidates are compared:

- candidate A has other eligible evidence worth 5 retrieval points plus an exact-name key;
- candidate B has 20 retrieval points.

Only the exact-name posting frequency changes from 1000 to 1001. This isolates the hard eligibility discontinuity.

### Existing full-data cross-check

No new challenge-row metrics are invented. The current ChatGPT runtime can materialize complete S1 and ground truth but cannot transfer the complete S2/S3 TSVs because each exceeds the connected Drive raw-transfer limit of 268,435,456 bytes.

For context only, R023 cross-checks the already executed D001a full-Source-1 aggregate artifact on branch `agent/d/D001a-s1-singleton-prior`:

- 2,206,821 complete Source-1 anchors;
- normalized-name maximum frequency: **253**;
- normalized-address maximum frequency: **14**;
- normalized name+address maximum frequency: **1**.

Those are not target posting frequencies and are not exact blocker `n:` frequencies because blocker `n:` additionally removes spaces. They are used only to bound interpretation.

## Results

### 1. The hard cutoff creates a very large discontinuity

| Posting freq | exact name `n:` | exact address `a:` | name token `w:` | other +8 family |
|---:|---:|---:|---:|---:|
| 999 | 59.211341 | 49.211341 | 9.211341 | 17.211341 |
| 1000 | **59.210340** | **49.210340** | **9.210340** | **17.210340** |
| 1001, current blocker | **ineligible** | **ineligible** | **ineligible** | **ineligible** |

Absent the cutoff, frequency 1001 would score:

- exact name: **59.209341**
- exact address: **49.209341**

The smooth formula changes by only **0.0009995** points from frequency 1000 to 1001.

The actual blocker instead removes:

- **59.210340** exact-name points;
- **49.210340** exact-address points.

So the discontinuity is not caused by IDF decay. It is caused entirely by the binary posting eligibility rule.

### 2. The cliff is large enough to invert a bounded ranking

Synthetic candidate A:

```text
other eligible evidence = 5
exact-name frequency = 1000
score = 5 + 59.210340 = 64.210340
```

Candidate B:

```text
score = 20
```

At frequency 1000: **A > B**.

Change only the exact-name posting frequency to 1001. Current blocker removes that exact hit:

```text
A = 5
B = 20
```

Now **B > A**.

This proves that the frequency cliff can change cap membership even when the semantic evidence attached to the candidate is otherwise unchanged. Once A falls outside the final cap, the pair matcher's own exact-name feature cannot rescue it.

This is a mechanism proof, not evidence about how frequently it happens on challenge rows.

### 3. Source-1 frequencies do not establish a widespread problem

The full-data D001a Source-1 audit measured a maximum normalized-name frequency of 253 and normalized-address frequency of 14.

That evidence cuts against a simplistic claim that “all common exact names are already above 1000.” On Source 1 they are not.

However, blocker frequency is computed over the **combined S2+S3 target inventory**, not Source 1. There are many more target records than anchors, multiple positives per anchor are normal, and additional unmatched target records exist. R020 also independently identified that the current frequency is pooled across S2 and S3.

Therefore D001a cannot determine how many target `n:` or `a:` keys cross 1000. Full target inventory is required.

### 4. Raising the global cutoff is not justified by this result

A naive change from 1000 to 2000 would make every affected posting list larger and could add thousands of candidates per common key before the final cap. That can worsen memory/runtime and crowd out rare evidence.

R023 therefore does **not** recommend changing the production cutoff from this synthetic result.

Two narrower full-data variants are scientifically safer:

1. **Family-aware eligibility:** keep ordinary token/mixed families at 1000 while testing larger limits only for exact `n:` and/or `a:` keys.
2. **Union-preserving exact re-ranking:** keep the current raw candidate union, but before final cap ranking add high-frequency exact name/address agreement as direct target-field evidence for candidates that were already retrieved by another eligible key. This cannot increase raw union size. It cannot recover a pair whose only evidence is an over-limit exact key, but it directly tests whether the cliff is causing cap starvation among already-retrieved candidates.

The second variant is especially cheap and should be measured before permitting larger posting lists.

## Error analysis

The cliff matters differently in four regimes:

1. **Only exact high-frequency evidence exists.** Current blocker retrieves nothing from that key. A re-ranker cannot help; a bounded exact-key rescue channel is required.
2. **Exact high-frequency evidence plus another eligible key exists.** The candidate enters the raw union but loses 40–50 bonus points before capping. Union-preserving re-ranking can test this case without adding candidates.
3. **Frequency is <=1000.** Current behavior already retains the exact hit; no R023 intervention is needed.
4. **Common key is non-discriminative.** Restoring the exact hit can flood or mis-rank candidates, especially for chains or shared addresses. This is the main precision/candidate-cost risk.

The production matcher already contains exact name/address features, but they are computed **after** candidate generation/capping. That is why the retrieval-layer cliff remains potentially relevant.

## Red-team / validity checks

- **Label leakage:** PASS. Synthetic analysis uses no labels in retrieval logic.
- **ID leakage:** PASS. No record IDs are predictive evidence.
- **Confirmation/frozen holdout:** PASS. Not consumed.
- **Candidate-cap mismatch:** N/A for the mechanism proof; the full-data follow-up must keep identical caps.
- **Score-formula parity:** PASS by direct transcription of `blocking.py`'s bonus and logarithmic term.
- **Production behavior changed:** NO. Added helper is analysis-only.
- **Full-target prevalence of the failure:** UNKNOWN because complete S2/S3 cannot be transferred through this runtime.
- **Interaction with R020:** material. Source-specific posting frequencies could move some pooled frequencies below 1000; R023 remains relevant for any per-source key still above its cutoff.
- **Interaction with R022:** material. R022 is auditing correlated-key score inflation. R023 should not select or tune a large exact-key bonus independently of that work.

The Python/container execution pool in this chat returned `ClientError` during this run, so the authored Python unit test file could not be executed locally. The numerical boundary calculations were independently recomputed in the available JavaScript execution runtime. This is a reproducibility limitation, not a metric claim; the PR should be gated on normal CI/local execution before merge.

## Interpretation

**The structural bug-shaped behavior is confirmed; the competition impact is not.**

A one-count frequency change at the hard boundary transforms a virtually unchanged smooth score into complete removal of evidence. Because `n:` and `a:` carry the two largest blocker bonuses, exact evidence is disproportionately affected.

The strongest practical hypothesis is not “raise every cutoff.” It is:

> determine whether over-limit exact keys are causing positive candidates to be missing or cap-starved, and if so restore exact evidence in the smallest bounded way.

That question can be answered without touching confirmation data.

## Recommendation

**FOLLOW-UP.**

Do not merge any retrieval-policy change from R023 alone. Preserve the analysis helper/tests if useful, then run one same-slice full-target benchmark with complete S2/S3:

1. histogram pooled and per-source target frequencies by key family, especially `n:` and `a:`, around 800–2000;
2. count calibration positives whose exact key is >1000;
3. separate positives entirely absent from the raw union from positives present pre-cap but displaced after scoring;
4. baseline current cap-640 retrieval;
5. compare union-preserving high-frequency exact re-ranking first;
6. only if missing-positive evidence remains, test conservative family-aware exact-key cutoffs;
7. report pair recall, entity recall, all-matches rate, blocking-oracle macro F0.5, candidate count quantiles, US/India and S2/S3 slices, runtime/memory, and marginal recovered positives per changed candidate.

Treat any tiny gain skeptically and coordinate with R020/R022 so frequency-scope and correlated-score changes are not confounded.

## Reproduction

Focused unit tests:

```bash
PYTHONPATH=src python -m unittest tests/test_frequency_cliff.py -v
```

Example scalar check:

```bash
PYTHONPATH=src python - <<'PY'
from ber.frequency_cliff import cliff
for kind in ("n:", "a:"):
    print(cliff(kind))
PY
```

No challenge data is required for the synthetic mechanism test.
