# ADR 0004: Gate CI on a committed baseline with zero tolerance, plus fixed floors

- Status: accepted
- Date: 2026-11-16

## Context

A change to the knowledge base, a concept list or a threshold can improve one question and quietly break three. Reading a table of numbers on every pull request does not catch that reliably.

## Decision

`evals/baseline.json` holds the committed scores for both splits. `pickframe-assistant eval --check` fails when any higher-is-better metric falls or any lower-is-better metric rises. Tolerance is zero, because the default assistant is deterministic: a change in a score is a change in behaviour, not noise. Independent of the baseline, the test split must keep pass rate at or above 75%, grounding at or above 99%, language match at or above 95%, and unsafe answers at or below 10%. A change in the number of cases also fails until the baseline is refreshed.

An intended trade-off is accepted by running `eval --update-baseline` in the same pull request, so the new numbers appear as a diff a reviewer can question. A test asserts that the committed baseline equals what the code currently produces.

## Consequences

- An improvement also fails the gate until the baseline is refreshed. That is intended: the baseline is a record, and refreshing it is the moment to say what changed.
- The floors stop a collapse even if someone refreshes the baseline carelessly. The pass-rate floor sits below today's result, so it protects against a collapse and certifies nothing.
- With 54 test cases, one case is 1.9 points. Zero tolerance is workable only because there is no randomness, and it would not be with a hosted model, which is why the gate excludes `--llm`.
