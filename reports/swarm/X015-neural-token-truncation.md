# X015 — neural tokenizer truncation and France transfer risk

## Hypothesis

The exact pinned multilingual encoder/cross-encoder tokenizers used by INT006 may truncate Source-1 text disproportionately for France or long-address records, creating a specific unseen-country transfer risk that character-count audits cannot resolve.

## Intended protocol

- stack on PR #268 head `fdff7866c4419f4fb645aa8d45a2a15696b8b729`;
- scan complete `train_source1.tsv` and `test_source1.tsv`, no sampling;
- reproduce `dense_training.serialize(name, address)` exactly;
- use the exact pinned tokenizers:
  - `intfloat/multilingual-e5-small` @ `614241f622f53c4eeff9890bdc4f31cfecc418b3`, dense `max_length=128`;
  - `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` @ `1427fd652930e4ba29e8149678df786c240d8825`, pair `max_length=160`;
- report complete-population token-length/truncation aggregates by US/India train/test and France test;
- no S2/S3 proxy, labels, leaderboard feedback, or France accuracy inference.

## Capability result

**BLOCKED. No tokenizer metric is claimed.**

The complete raw Source-1 files were successfully transferred from the supplied Drive in this session:

- train Source-1: 210,069,713 bytes;
- test Source-1: 175,022,086 bytes.

The exact neural code was inspected on PR #268. It confirms the serializer and pinned model revisions above, and uses Hugging Face `AutoTokenizer` with truncation at 128 for dense encoding and 160 for cross-encoder pairs.

The local execution environment does not provide `transformers`, `tokenizers`, `sentencepiece`, or a SentencePiece CLI/library. Installing the pinned PR dependency versions failed before package resolution because this runtime cannot resolve PyPI. I then attempted a direct-artifact fallback rather than changing tokenization semantics. Public Hugging Face metadata confirms the dense tokenizer is `XLMRobertaTokenizer`; both tokenizer JSON artifacts are Xet-backed. The available web/download surfaces could inspect the metadata but could not retrieve the Xet artifact into the compute runtime.

Because exact subword boundaries are the quantity under test, replacing the pinned tokenizer with whitespace counts, character lengths, another XLM-R tokenizer, or a home-grown approximation would answer a different question. No such surrogate was used.

## Executed checks

1. Drive authorization and raw-file transfer: **PASS** for both required Source-1 files.
2. PR #268 source audit for exact serializer, model IDs, revisions, and max lengths: **PASS**.
3. Local import probe for `transformers`, `tokenizers`, `sentence_transformers`: **FAIL / packages unavailable**.
4. Exact dependency installation attempt: **BLOCKED by network/DNS before package resolution**.
5. Direct pinned-tokenizer artifact path: **BLOCKED by inaccessible Hugging Face Xet redirect/artifact transfer**.
6. Search for preinstalled SentencePiece binaries/libraries/wheels: **none found**.

## Risks / interpretation

This is an execution blocker only. It provides no evidence for or against France tokenizer truncation. Character-length or whitespace-token distributions would not be a valid substitute because the hypothesis specifically concerns the pinned multilingual subword tokenizers.

## Recommendation

**BLOCKED / FOLLOW-UP.** Recover X015 in the existing private Modal environment or any authorized runtime that already has PR #268's pinned Hugging Face stack/model cache. Reuse this exact issue scope and complete Source-1 files; do not repeat the Drive transfer work and do not substitute an approximate tokenizer.

Lease released after this checkpoint.
