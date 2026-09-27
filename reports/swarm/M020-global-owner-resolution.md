# M020 — Global predicted-owner resolution

The V5/V6 pair matcher scores each Source 1–target pair independently. A target
can consequently be emitted under several Source 1 entities even though the
supplied training truth assigns each target to at most one owner. On V6 test
predictions, 66,942 target IDs have multiple predicted owners and 100,072 edges
are surplus assignments. France accounts for 50,547 conflicting targets and
81,726 surplus edges.

M020 is a set-level postprocessor. For each conflicting target with a nonempty
address, it compares its normalized address to each predicted owner's normalized
address using RapidFuzz token-sort ratio. If the top ratio is at least 80 and
exceeds the second-best ratio by at least 10, it retains the top owner and
removes the other assignments. It never adds a match or candidate. The rule
uses only supplied test text; IDs are join keys and deterministic tie breakers,
not predictive features. The code is `src/ber/resolve_owner.py`.

## Labeled structural gate

`tools/experiments/m020_owner_label_gate.py` evaluates the address decision on
all supplied labeled training targets whose normalized name has 2–20 Source 1
competitors. It considers only target groups where the true owner is in the
competitor set. This is a **proxy for ambiguous ownership**, not a full replay
of V5 model predictions. At the 80/10 gate, the address winner is the true
owner in **337,356 / 337,356** eligible US/India groups: 242,093 US and 95,263
India. The looser 70/10 gate errs in 5 of 399,274 groups. Detailed counts and
runtime are in `reports/m020_owner_label_gate.json`.

The frozen 3,051-anchor INT006 development holdout contains zero predicted
target conflicts passing this margin. It therefore cannot give a meaningful
paired macro F0.5 estimate for this global step. The exact rule was added to
the cached-pair evaluator to establish that fact; it is not advertised as a
held-out score improvement. Full-population test behavior must be evaluated by
a leaderboard upload without treating the public scalar as labels.

## Test output variant

Applying 80/10 to V6 removes **48,114** predicted edges: France 44,323,
India 2,085, US 1,706. It affects 31,581 Source 1 rows and preserves all
1,732,544 rows and the frozen cap-32 candidate set. The separate output is
`output/submission_v8_owner80/matching_results.tsv`; its SHA-256 is
`f3892589588bbda2c6dbcf71d3f630ae72a5c9331a608937eb93dbba6303fd82`.
The organizer full two-file validator passes with the frozen candidate file. No
public score is known yet.

This is promising because it attacks a global constraint absent from the pair
model, especially in France. The proxy benchmark may overstate its precision
on actual neural conflicts or the unlabeled French slice, so V8 remains an
experimental submission until its public result is observed.
