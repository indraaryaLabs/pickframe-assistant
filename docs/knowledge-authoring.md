# Writing and changing the knowledge base

The assistant knows only what is in `knowledge/`. Adding a fact there is the only way to teach it something, and it is deliberately not possible to teach it in code.

## Rules

1. **Public and product-level only.** Every fact must be on one of PickFrame's public pages, and the page goes in `source`. Nothing about how the product is built, how it is secured, or how it is operated. No phone numbers, email addresses, keys or internal names. See [ADR 0005](adr/0005-public-safe-knowledge.md).
2. **One topic per file, same topics in both languages.** `knowledge/id/pricing.md` and `knowledge/en/pricing.md` must have the same sections in the same order. `pickframe-assistant check` and the loader reject a mismatch.
3. **A section is one passage, and each sentence stands alone.** The generator quotes sentences, so a sentence that starts with "It" or "This plan" is useless on its own. Say "The Pro plan" every time.
4. **Say the number, with its unit, in the sentence.** "Pro has 50 projects, 50 galleries and 250 invoices per month", not "see the table".
5. **Put the overview first.** On a tie the earlier section wins, so the first section of a topic should be the one that answers the general question.
6. **Write what is not true when people ask.** "PickFrame has no automatic renewal and stores no cards" answers a question that would otherwise abstain.

## File format

```markdown
---
id: refund
title: Guarantee and refunds
lang: en
source: https://pickframe.satuarah.click/terms
checked: 2026-11-16
---

## The 14-day guarantee
A 14-day guarantee applies to the first paid plan purchase. ...

## After a refund is approved
...
```

`id` must equal the file name, and `lang` must equal the folder. Anything before the first `##`, an empty section, or a duplicate heading is an error. A heading becomes the passage id: `## The 14-day guarantee` is `en/refund#the-14-day-guarantee`.

## Changing a fact

1. Edit both languages in the same commit and update `checked`.
2. Run `pickframe-assistant check`. It verifies that every expected fact in `evals/cases.jsonl` still exists in the topics its case points at, so a changed price fails here, naming the case, instead of silently scoring as a failure.
3. Fix the labels that the change made wrong. This is the one time a label may be edited, and the reason belongs in the commit message.
4. Run `pickframe-assistant eval --check`. If scores changed because a fact changed, refresh the baseline with `--update-baseline` in the same pull request and say why.

## Adding a topic

Create the file in both languages and add cases for it. A topic without cases is invisible to the evaluation: the assistant may answer from it, and nothing measures whether it answers well. Add at least one answer case, and one case that is near it but should abstain.

## Adding cases

Add lines to `evals/cases.jsonl` (the format is at the top of `evaluation/cases.py`). Two rules keep the numbers honest:

- New cases go into the `test` split until they have been used for tuning, and then they are dev cases. Never move a case between splits to improve a number.
- A case that the assistant fails is not removed or rewritten to pass. If the label is wrong, fix the label and record why in the commit message and in [evaluation.md](evaluation.md).
