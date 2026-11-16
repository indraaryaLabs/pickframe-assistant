# ADR 0003: Score with rules, split dev from test, and test the evaluator itself

- Status: accepted
- Date: 2026-11-16

## Context

An evaluation that cannot be trusted is worse than none, because it produces confidence. Three things commonly go wrong: a model judging a model is not repeatable and costs money; tuning against the cases you report inflates the result; and a metric that cannot tell good from bad passes unnoticed.

## Decision

- **Rules, not a judge.** Each case is checked for the decision, the language, the facts, forbidden text, the allowed citations and grounding. Facts are lists of accepted spellings matched on whole tokens, with numbers normalised, so `69.000` equals `69,000` and is not found inside `169.000`.
- **Dev and test.** Tuning uses the dev split. The test split is for reporting. The history of what was looked at, and when, is written down in [evaluation.md](../evaluation.md).
- **Validated labels.** `check` rejects a case whose expected fact is not in the topics it points at.
- **Reference systems.** An oracle, an always-abstain bot, a search-only bot that never refuses, and a random retriever are run through the same scoring. Tests assert that they land at 100%, near zero, unsafe, and at the floor.
- **Two error rates.** Unsafe answers and over-refusals are reported separately, because one can be bought with the other.

## Consequences

- Scores are repeatable and free, and a failure points at a named rule.
- Matching words cannot judge meaning. A correct answer in different words is marked wrong, and a quoting generator is the system least likely to hit that.
- The dev/test split is only as strong as the discipline around it. One person wrote both, and the test split has been read; [evaluation.md](../evaluation.md) says so. Fresh cases are needed before tuning again.
- The reference systems mean that a change to the scoring that makes the oracle imperfect, or the search-only bot look safe, fails the build.
