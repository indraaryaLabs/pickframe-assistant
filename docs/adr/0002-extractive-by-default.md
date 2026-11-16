# ADR 0002: The default generator quotes sentences and writes nothing of its own

- Status: accepted
- Date: 2026-11-16

## Context

A support assistant that states a wrong price or promises a refund the terms do not offer is worse than none. A language model can paraphrase well, and it can also invent. It also costs money and needs a key, which a portfolio project that anyone should be able to run for free cannot assume.

## Decision

The default generator chooses sentences from the retrieved passages and quotes them, each followed by a `[n]` marker for its passage. It picks them by greedy set cover over the question's weighted terms. A language model is available behind the same `Generator` protocol (`--llm`), and receives the same passages and the instruction to cite them or answer `NO_ANSWER`.

## Consequences

- The default generator cannot say something the knowledge base does not say. Grounding is 100% by construction, and the evaluation checks it rather than assuming it.
- Answers read as quoted sentences, which is less fluent than a paraphrase, and sometimes include a sentence that is true but not the one asked about.
- A good answer needs the right sentence to exist, so the knowledge base is written in standalone sentences ([authoring guide](../knowledge-authoring.md)).
- The language model is optional and is held to the same checks: a reply with no valid citation becomes an abstain, and the evaluation verifies that its numbers and sentences are supported by what it cited. The regression gate applies to the default generator only, because a hosted model is not deterministic.
