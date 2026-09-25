# Persistent project priorities

- Optimize official per-entity macro F0.5 and unseen-country robustness first.
- The user explicitly prioritizes results over reducing local computation. Do not
  select a lower-scoring configuration merely to save laptop time. Scalability and
  the deadline remain feasibility constraints; compare measured quality and cost.
- Available hardware: one RTX 3060 6 GB/i7-12700H laptop (16 GB RAM verified here),
  two teammates' RTX 4080 12 GB/i9-13900HX laptops, and approximately $650 AWS credits.
  AWS resources have not been provisioned or charged by this pipeline.
- The 30-candidate shortlist was a historical throughput experiment. Its partial
  test export was stopped after the user clarified the quality priority. It is not
  the selected final submission. Configuration selection now maximizes measured
  calibration macro score, followed by independent confirmation.
- Use only the supplied entity records. No external business, registration,
  geocoding, or entity-resolution lookups. Pretrained model licenses and provenance
  must be recorded; the supplied rules require MIT/Apache 2.0 and at most 8B parameters.
- Keep original datasets, PDFs, archives, row-level diagnostics, model binaries,
  and generated predictions out of Git. Push code and aggregate experiment reports
  to the user-authorized `sting-raider/Team-517-ML` repository.
- Preserve a separate confirmation sample. Scores from repeatedly inspected
  development partitions are development evidence, not untouched estimates.
