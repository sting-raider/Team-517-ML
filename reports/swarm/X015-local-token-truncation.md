# X015 recovery — exact tokenizer length audit

The separate X015 research branch identified a transport blocker for the exact
pinned model tokenizer. The integration machine can load that tokenizer, so we
sampled the supplied test text locally without any external entity lookup.

`tools/experiments/x015_token_length_audit.py` uses the exact M017
`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` revision
`1427fd652930e4ba29e8149678df786c240d8825`, the production
`serialize(name,address)` function, and no truncation during measurement.
For each country, it keeps up to 5,000 pairs from a deterministic hash sample
of the frozen cap-32 candidate file. This includes pairs the matcher rejected.

| Country | Sampled pairs | p99 tokens | Max tokens | Above 160 |
|---|---:|---:|---:|---:|
| US | 5,000 | 77 | 112 | 0 |
| India | 5,000 | 124 | 178 | 1 |
| France | 5,000 | 88 | 117 | 0 |

The parallel audit of the first V6-predicted target per sampled Source 1 row
also finds 0/5,000 US, 1/5,000 India, and 0/5,000 France pairs above 160.
The aggregates are in `reports/swarm/X015-local-candidate-token-lengths.json`
and `reports/swarm/X015-local-token-lengths.json`. This rules out **widespread
French pair truncation** as an explanation for the public-score gap. The
sample is not a proof that no rare record truncates.

The separately pinned multilingual E5 encoder uses a 128-token limit on
individual serialized records. In a deterministic sample of 5,000 Source 1
records per country, no record exceeds 128; the maxima are 57 US, 90 India,
and 52 France. The exact tokenizer, revision, code, and aggregate report are
recorded in `reports/swarm/X015-local-dense-token-lengths.json`. This also
argues against widespread retrieval-side truncation.
