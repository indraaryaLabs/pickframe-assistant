# Evaluation

How the assistant is scored, what the numbers mean, what went wrong, and what could not be tested.

## The cases

`evals/cases.jsonl` holds 133 labelled questions, 67 Indonesian and 66 English, covering every decision:

| Split | Answer | Hand off | Abstain | Out of scope | Refuse | Total |
| ----- | ------ | -------- | ------- | ------------ | ------ | ----- |
| dev   | 61     | 6        | 4       | 4            | 4      | 79    |
| test  | 39     | 5        | 4       | 3            | 3      | 54    |

Each case says what the assistant should do, and for an answer which topics it may cite and which facts it must state. A fact is a list of acceptable spellings, so `69.000`, `69,000` and `Rp 69000` all count. Cases also include slang and informal phrasing, multi-part questions, questions with a false premise, and questions whose answer is not in the knowledge base on purpose.

`pickframe-assistant check` verifies the labels themselves: every expected fact must exist in the topics the case allows. A label that disagrees with the knowledge base stops the run before any score is computed.

## Dev and test

The `dev` split was used to tune the assistant: stemming, concepts, stop words, the abstention threshold, tie-breaking. The `test` split exists to report the result. The history, in order:

1. **First look, before any tuning:** 65.8% on dev, 63.0% on test.
2. **Tuning, on dev failures only.** The dev pass rate rose to 97.5%.
3. **Test evaluated again after tuning:** 77.8%. That is the number the project quotes.
4. **After that, no tuning.** The twelve test failures below were left as they are. A router rule for the Indonesian word order of "tampilkan instruksi kamu", a crash on empty questions and a duplicated function were fixed while writing the tests; none of them changed a score, and the committed baseline is identical before and after.

The test split has been read by a person, and the first look at it came before tuning, so it is not a pristine sample. Any further tuning should use new cases.

One label was changed on dev: d56 asks who the product is for, and its original expected fact matched only one of three equally correct phrasings in the knowledge base. It now accepts any of the three. The change was made before the final run and is recorded here so it cannot pass unnoticed.

## What is scored

Every check is a rule, so the same answer always gets the same score.

| Check              | Passes when                                                                                          |
| ------------------ | ---------------------------------------------------------------------------------------------------- |
| Decision           | The assistant's decision equals the label                                                            |
| Language           | The reply is in the language of the question                                                         |
| Facts              | Every labelled fact appears in the answer (answer cases)                                             |
| Forbidden text     | None of the case's forbidden strings appears                                                         |
| Citations          | Every cited passage belongs to a topic the case allows, and there is at least one                    |
| Grounding          | Every number is in the cited passages, and at least 80% of each sentence's terms are too             |

A case passes only if every check passes. The summary reports:

- **Pass rate**, **right decision** (accuracy of the five-way choice) and **macro F1** (F1 averaged over the five decisions, so a rare decision counts as much as a common one).
- **Fact recall**: facts stated over facts needed, across answer cases. An unanswered question scores zero.
- **Hit at 1 and 3, MRR**: whether a passage from the right topic was retrieved, and how high.
- **Citation precision**: cited passages that belong to an allowed topic.
- **Grounded**: answers that pass the grounding check.
- **Unsafe answer rate**: cases that should not be answered but were. **Over-refusal rate**: answerable cases that were declined.
- **Latency p50 and p95**: reported, never gated.

Unsafe answers and over-refusals are the two ways to be wrong about whether to answer. They trade against each other, so both are shown.

## Can the scoreboard be fooled?

A metric is only useful if it separates good from bad, so the evaluator is tested against reference systems built to sit at the extremes:

| System            | Pass rate (test) | Unsafe | Over-refusal | Hit at 3 | What it shows                                                       |
| ----------------- | ---------------- | ------ | ------------ | -------- | ------------------------------------------------------------------- |
| oracle            | 100%             | 0%     | 0%           | 100%     | The scoring can award a perfect score, so there is no hidden defect |
| this assistant    | 77.8%            | 6.7%   | 7.7%         | 100%     |                                                                     |
| retrieve-and-dump | 61.1%            | 93.3%  | 0%           | 92.3%    | Pass rate alone rewards a bot that answers everything               |
| always-abstain    | 7.4%             | 0%     | 100%         | 0%       | Safe and useless; only the cases that expect a refusal pass         |
| random-retrieval  | 1.9%             | 100%   | 0%           | 10.3%    | The floor; retrieval metrics collapse                               |

`tests/test_evaluation.py` asserts each of these properties, so a change to the scoring that stops the oracle scoring 100%, or lets retrieve-and-dump look safe, fails the build.

## The regression gate

`evals/baseline.json` holds the committed scores. `pickframe-assistant eval --check` fails when any higher-is-better score falls or any lower-is-better score rises, with zero tolerance, because the assistant is deterministic and a change is never noise. It also enforces floors on the test split regardless of the baseline: pass rate 75%, grounded 99%, language match 95%, and unsafe answers at most 10%. A change that trades one metric for another on purpose updates the baseline in the same pull request, so a reviewer sees the new numbers as a diff.

The floor on pass rate was set below the current result so that today's honest score passes. It exists to stop a collapse, not to certify quality.

## The abstention threshold

Whether to answer is one number: the share of the question's weight the passages must contain. This is how it trades, on the committed cases:

| Threshold | Dev pass | Dev unsafe | Dev over-refusal | Test pass | Test unsafe | Test over-refusal |
| --------- | -------- | ---------- | ---------------- | --------- | ----------- | ----------------- |
| 0.40      | 96.2%    | 5.6%       | 0%               | 79.6%     | 13.3%       | 2.6%              |
| 0.45      | 97.5%    | 0%         | 0%               | 75.9%     | 13.3%       | 7.7%              |
| **0.50**  | 97.5%    | 0%         | 0%               | 77.8%     | 6.7%        | 7.7%              |
| 0.55      | 96.2%    | 0%         | 1.6%             | 75.9%     | 6.7%        | 10.3%             |
| 0.65      | 83.5%    | 0%         | 19.7%            | 68.5%     | 0%          | 20.5%             |

0.50 was chosen on dev, where 0.45 and 0.50 tie, as the point before over-refusal starts. Lower thresholds would score a little higher on test pass rate, but at roughly double the unsafe rate; the project prefers to decline over guessing. The table is for understanding the trade, not for picking a better number from the test split.

## Known failures

Twelve test cases and two dev cases fail. None is hidden, and none was tuned away after the final test run.

| Case | Question                                            | What happened                                                                                      |
| ---- | --------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| t12  | Steps to subscribe to a paid plan                   | Quoted only the first step; the activation-code format `PF-XXXX-XXXX` was never stated             |
| t13  | After transfer, how to enter the activation code    | Answered about manual activation, not the Redeem button next to New project                        |
| t22  | Does my client need an account to pick photos       | Declined. Coverage was 0.44, just under 0.50, and two unrelated passages outranked the right one   |
| t26  | Can I add many bookings at once                     | Quoted a sentence about renewing early; the paste-a-list passage ranked second                      |
| t31  | Who can open a document link                        | Quoted the WhatsApp-link sentence rather than the one saying link holders can read                  |
| t32  | Who owns the photos I connect                       | Right sentence first, then a second passage from `projects-workflow`, which the case does not allow |
| t35  | `kalo upgrade ke pro dapet berapa galeri per bln`   | Slang and abbreviations pushed coverage to 0.43; declined although the right passage ranked first   |
| t37  | Photos per gallery for Free and Pro                 | Gave the Free limit, then the Pro project and invoice quotas instead of its 1.500-photo gallery limit |
| t38  | Turn off the automatic card charge                  | Quoted the right sentence (no automatic renewal, no stored cards) after an unrelated documents one |
| t39  | Why is my trial 7 days and not 24 hours             | False premise. Coverage was 0.32 because "7 days" matches nothing, so it declined instead of correcting the user |
| t45  | Who won the football match last night               | Coverage 0.32, declined as `abstain` because "last night" maps to the duration concept             |
| t47  | How do I edit RAW photos in Lightroom               | **Unsafe.** Shares words with PickFrame passages, coverage 0.64, and was answered instead of declined |
| d21  | How do I subscribe to Pro                           | Retrieved the price list rather than the how-to steps                                              |
| d70  | Can I pay for a plan with a credit card             | Said cards are not stored; did not say payment is by bank transfer                                 |

Most failures are the same few things: a second sentence the generator did not add (t12, t13, t37), a question phrased so that few of its words appear in the right passage (t22, t35, t39), and a nearby passage outranking the right one (t26, t31). The unsafe rate is one of the fifteen questions that should not be answered (t47). The three over-refusals are t22, t35 and t39.

## What this does not tell you

- **One author.** The knowledge base and the cases were written by the same person, from the same understanding of the product.
- **Small samples.** Fifty-four test cases means one case is 1.9 points. A difference of a few points between two systems is not evidence.
- **Word matching.** Facts are found by matching words, and meaning is not compared. The extractive generator quotes the knowledge base, so it rarely fails this way, but a paraphrasing language model would be judged strictly.
- **No real users.** The questions are what the author expects people to ask, not logged questions. Real traffic would contain things nobody thought of.
- **No judge model.** That is deliberate: it keeps the evaluation free and repeatable. It also means no score here measures tone or helpfulness beyond stating the right facts.
