# ADR 0001: Retrieve with BM25 and a vocabulary-guided analyzer, not with embeddings

- Status: accepted
- Date: 2026-11-16

## Context

The assistant must find the passages that answer a question, in Indonesian and English, for free. The knowledge base is small, about sixty passages per language, and its vocabulary is narrow: plans, prices, quotas, galleries, documents. Embeddings would need a model to download or an API to pay for, and would make a ranking hard to explain when it is wrong.

## Decision

Use Okapi BM25, one index per language. Close the vocabulary gap with an analyzer instead of a model: Indonesian and English synonyms map to shared concepts, a few two-word phrases are merged, and Indonesian affixes are removed only when the result is a word the knowledge base already contains.

## Consequences

- No runtime dependencies, no download, no network. A run is deterministic, so the evaluation gate can have zero tolerance.
- Every ranking can be explained from the matched terms and their weights, and the report shows scores and terms for each case.
- Recall depends on the concept lists. A question that uses a word nobody mapped will miss, and a vague question can land on the wrong topic; several known failures are of this kind.
- The concept lists are maintained by hand. Each new topic may need new entries, and the evaluation is what shows when it does.
- If the knowledge base grows to hundreds of topics, or questions turn paraphrastic, this decision should be revisited. The `Assistant` takes its index internally, so a dense or hybrid retriever could replace it while the evaluation stays unchanged, which would also say whether it helped.
