# R027: address-number-conditioned name-character rescue

**Decision: HOLD, not enough to close the leaderboard gap.** On the same 4,389
development-calibration anchors and complete training inventory, the current
v3 cap160 blocker misses 850 of 15,276 labeled pairs. A third retrieval channel
that requires a shared address number and uses name-character postings can
recover some of them without materially increasing the candidate budget.

| Retrieval | Pair recall | Blocker oracle macro F0.5 | Mean candidates |
|---|---:|---:|---:|
| v3 lexical + name-character | 0.944357 | 0.980461 | 148.049 |
| Same first address number | 0.946517 | 0.981139 | 148.067 |
| Any shared address number | 0.947761 | 0.981716 | 148.141 |

The any-number channel raises India's oracle from 0.969196 to 0.971862. The
frozen v3 matcher at its unchanged 0.625 threshold scores 0.949121 on the
original candidates and 0.949599 on the any-number candidates, a +0.000478
calibration gain. This is exploratory calibration evidence, not confirmation.

The channel uses the 58,846,343 existing train character postings; 10,320,219
searchable train records contain 14,943,246 distinct address-number memberships.
An indexable composite-key implementation is checked in as a prototype, but it
has **not** been benchmarked or promoted. No new confirmation or leaderboard
submission was consumed. The full aggregate receipts and diagnostic code are
in `reports/r027_*.json` and `modal_r027.py`; record-level data stays private.

The large remaining gap needs a more complementary method, particularly a way
to link fragments that are similar to each other but not directly to Source 1.
