# Architecture decision records

| Record                                         | Decision                                                                |
| ---------------------------------------------- | ----------------------------------------------------------------------- |
| [0001](0001-bm25-over-embeddings.md)           | Retrieve with BM25 and a vocabulary-guided analyzer, not with embeddings |
| [0002](0002-extractive-by-default.md)          | The default generator quotes sentences and writes nothing of its own     |
| [0003](0003-rule-based-evaluation.md)          | Score with rules, split dev from test, and test the evaluator itself     |
| [0004](0004-regression-gate.md)                | Gate CI on a committed baseline with zero tolerance, plus fixed floors   |
| [0005](0005-public-safe-knowledge.md)          | Build the knowledge base from public pages and keep it product-level     |
