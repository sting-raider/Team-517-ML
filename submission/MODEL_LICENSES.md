# Selected V13 model provenance and licenses

The archive includes fine-tuned checkpoints trained only on the organizer's supplied training records and labels. They are used locally inside the pipeline, without a hosted inference API. The checkpoint hash inventory is in `reproduction_manifest.json`.

| Component | Initialization and exact revision | Parameters | License |
|---|---|---:|---|
| INT005 retrieval encoder | `intfloat/multilingual-e5-small`, `614241f622f53c4eeff9890bdc4f31cfecc418b3` | 117,653,760 | MIT |
| M017 pair cross-encoder | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, `1427fd652930e4ba29e8149678df786c240d8825` | 117,641,089 | Apache 2.0 |
| INT003 depth-10 CatBoost | Trained from scratch on supplied data; 57 features | Tree model, 29.6 MB checkpoint | Apache 2.0 (CatBoost implementation); MIT (Team 517 pipeline and trained artifact) |

The two neural models total 235,294,849 parameters, comfortably below 8 billion. Training reports included with each checkpoint record initialization, revision, seed, completed steps, and parameter counts. We modified the neural weights through supervised fine-tuning; these are not the untouched base weights.

Official model cards (pinned revisions):

- https://huggingface.co/intfloat/multilingual-e5-small/blob/614241f622f53c4eeff9890bdc4f31cfecc418b3/README.md
- https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1/blob/1427fd652930e4ba29e8149678df786c240d8825/README.md

Full license texts and original model cards are included under `licenses/`. RapidFuzz and its optional v3.3.3 C++ dependency are MIT; CatBoost, Transformers, PyTorch, DuckDB, NumPy, Faiss, SentencePiece, pandas, and Modal retain their upstream licenses. No upstream ownership is claimed. Dependency installation may access package repositories; it does not query any external business identity source.
