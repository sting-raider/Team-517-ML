# I013 — Experiment report

## Hypothesis

A strict report renderer that validates experiment metadata and emits the AGENTS.md-required structure will reduce incomplete and incomparable swarm handoffs without affecting model behavior.

## Change

Added `src/ber/reporting.py` with fail-closed schema validation, deterministic Markdown rendering, optional 15-column registry-row generation, and a CLI. Added `tests/test_reporting.py` for deterministic output, malformed records, recommendation validation, registry sanitization, and end-to-end CLI behavior.

## Protocol

Tier 0/1 infrastructure validation only. Tests use synthetic metadata fixtures. No challenge records, confirmation anchors, leaderboard feedback, or model outputs were consumed.

Data slice: synthetic fixtures only

Branch/commit: `agent/i/I013-auto-report` / `7376c6e1ec89f5ea792ca5fe1bfe6bf24aa55e12`

Commands:

```bash
PYTHONPATH=src python -m unittest tests.test_reporting -v
PYTHONPATH=src python -m ber.reporting --input experiment.json --output report.md --registry-row-out row.tsv
```

Compliance: No challenge data, external business data, predictions, model binaries, or holdout labels were used.

## Results

- Baseline: standardized_report_validator=absent
- New result: standardized_report_validator=5/5 tests PASS
- Delta: NA
- Runtime: 0.899s for 5 local unittest/CLI checks
- Secondary metrics:
  - cli_smoke: PASS
  - deterministic_render: PASS
  - registry_columns: 15
  - unit_tests_passed: 5

## Error analysis

- Missing required fields fail before rendering instead of silently producing partial reports.
- Unsupported recommendation values fail closed.
- Registry-row generation strips tabs/newlines from fields so one experiment cannot corrupt TSV structure.
- The renderer deliberately does not validate whether a claimed metric was scientifically measured correctly.

## Interpretation

The utility standardizes the handoff surface and makes report completeness mechanically testable while remaining isolated from retrieval, matching, scoring, and holdout policy. It is useful infrastructure, not a competition-score improvement.

## Risks

- A well-formed report can still contain a bad experiment; scientific validity remains the agent's responsibility.
- Upstream benchmark JSON schemas are still evolving, so automatic wiring should wait until those PRs stabilize.
- This experiment does not measure end-to-end researcher time saved across the swarm.

## Recommendation

**PROMOTE**

## Follow-up tasks

- After I001/I008 schemas stabilize, add an adapter that converts their machine-readable outputs into this record shape without weakening validation.
