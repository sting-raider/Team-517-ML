# I016 — Red-team candidate-budget evaluator vs production inference

## Hypothesis

`reports/candidate_budget.json` is used by the production Modal path to select cap-specific thresholds for smaller candidate budgets. If its reconstructed ranking, cap semantics, model, threshold, or metric behavior differs from production inference, the apparent 160-vs-640 tradeoff could be invalid.

## Change

No matching, retrieval, threshold, or scoring behavior was changed.

This branch factors the existing raw candidate rank reconstruction into `src/ber/candidate_budget_contract.py::raw_retrieval_rank` and routes `candidate_budget.py` through that helper. Five focused tests make the production ranking contract explicit: retrieval descending, target entity ID ascending for ties, per-anchor rank reset, nested caps, empty input, and fail-loud length validation.

## Protocol

Base: main `2a2ae6ec6de943ad7e38ecc0f0a95b53a0d7f460`.

Audit targets:
- `src/ber/blocking.py`
- `src/ber/candidate_budget.py`
- `src/ber/shortlist.py`
- `src/ber/predict.py`
- `src/ber/tune.py`
- `src/ber/freeze_first.py`
- `src/ber/experiment.py`
- `src/ber/metrics.py`
- `modal_app.py`
- `reports/cap_study.json`
- `reports/retrieval_study.json`
- `reports/wide_calibration.json`
- `reports/tuning.json`
- `reports/candidate_budget.json`

Executable check:

```bash
PYTHONPATH=src python -m unittest tests.test_candidate_budget_contract -v
```

Result in the available Python runtime: **5/5 PASS in 0.001 s**. The helper and test also pass `py_compile`.

No confirmation or frozen holdout was consumed. No challenge labels were newly evaluated.

## Results

| Audit class | Result | Evidence |
|---|---|---|
| Raw candidate ordering | PASS | Production SQL ranks `retrieval DESC, entity_id ASC`; evaluator lexicographic ranking implements the same order within anchor. |
| Per-anchor cap semantics | PASS | Ranking resets by group and `rank <= cap` is nested; focused tests cover ties and group boundaries. |
| Production shortlist semantics | PASS | Modal sets `candidate_cap == shortlist_cap` for smaller-cap runs. `shortlist_rows` returns all rows when group size is already <= cap, so there is no second hidden filtering stage. |
| Selected-model parity | PASS | `candidate_budget.py` uses `depth10_wide_probabilities.npy`; `freeze_first.py` freezes the same depth-10 model as `submission_v1/mixed.cbm`. |
| Threshold transfer | PASS | Production Modal replaces the frozen threshold with the exact `candidate_budget.json[candidate_cap].threshold` and sets both candidate and shortlist caps to the requested cap. |
| Metric semantics | PASS | Threshold selection and evaluation include every calibration anchor; candidate misses remain in truth denominators; `metrics.row_score` implements official per-anchor F0.5 including empty-set behavior. |
| Same-slice artifact consistency | PASS | 13/13 exact comparisons matched across candidate-budget, cap-study, retrieval-study, wide-calibration, and depth-10 tuning artifacts. |
| Artifact provenance fingerprint | RISK / owned elsewhere | `candidate_budget.json` itself does not bind a model/config hash. No evidence shows the current file is stale, but a future stale-report mismatch is possible. This is the broader I002 config-hashing/stale-cache task and is not reimplemented here. |

The 13 exact artifact checks were:
- candidate-budget vs cap-study at caps 20, 30, 40, 80;
- candidate-budget vs retrieval-study at caps 80, 160, 320, 640;
- wide-calibration vs retrieval-study at caps 80, 160, 320, 640;
- candidate-budget cap 640 vs depth-10 tuning.

All compared candidate-recall/oracle/entity-count/singleton-count/candidate-quantile fields matched exactly. The cap-640 depth-10 macro F0.5 and threshold also matched exactly.

### Context, not a cap recommendation

On the committed 4,389-anchor calibration slice, cap 160 has mean 142.182 candidates and macro F0.5 0.927197; cap 640 has mean 442.629 and macro F0.5 0.930679. The corresponding pair-recall gap is 0.020555 and blocking-oracle gap is 0.008097. These are repeatedly inspected calibration results, not independent confirmation, and this audit does **not** select a final cap. R021 owns the Pareto/selection analysis.

## Error analysis

The main failure mode searched for was a divergence between the evaluator's reconstructed rank and the production blocker's SQL rank, especially exact-score ties. The tie-break is consistent: both prefer the lexicographically smaller target entity ID after retrieval score.

A second plausible failure was hidden lexical pruning after applying a raw cap. That does not occur in the current smaller-cap production configuration because `shortlist_cap` equals `candidate_cap`, making the shortlist a no-op for every anchor after blocking.

The remaining weakness is provenance rather than present numerical inconsistency: the smaller-cap report is trusted by filename and cap key rather than by a model/config fingerprint.

## Risks

- The candidate-budget calibration slice has been inspected repeatedly; its values are model-selection evidence, not an untouched performance estimate.
- Cap 160 has no independent 5,000-anchor confirmation for the exact production configuration.
- A stale `candidate_budget.json` could theoretically transfer thresholds from a different model unless I002-style provenance checks are integrated.
- This audit does not validate France performance because France has no labels.

## Recommendation

**PROMOTE** the ranking-contract regression guard. The current candidate-budget evaluator and production inference path are semantically consistent on the audited dimensions; no defect was found that invalidates the committed cap study.

**FOLLOW-UP** through I002 for artifact/config fingerprinting and through R021 for the evidence-bounded cap tradeoff. No score gain is claimed.

## Changed files

- `src/ber/candidate_budget_contract.py`
- `src/ber/candidate_budget.py`
- `tests/test_candidate_budget_contract.py`
- `reports/swarm/I016-candidate-budget-redteam.md`
- `experiments/REGISTRY.tsv`
