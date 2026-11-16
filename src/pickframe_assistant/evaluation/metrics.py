"""Scoring: one `CaseResult` per question, then a `Metrics` summary per split.

Every check is a rule, not a judgement call, so the same input always gets the same score.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final, Protocol

from pickframe_assistant.evaluation.cases import Case, canon, contains
from pickframe_assistant.knowledge import Corpus
from pickframe_assistant.model import KINDS, Answer, Kind
from pickframe_assistant.text import split_sentences, tokenize, words

_MARKER: Final = re.compile(r"\s*\[\d+\]")
_SUPPORT_THRESHOLD: Final = 0.8


class System(Protocol):
    """Anything that answers a question: the assistant, a variant of it, or a reference system."""

    name: str

    def answer(self, question: str) -> Answer: ...


@dataclass(frozen=True)
class CaseResult:
    case: Case
    answer: Answer
    kind_ok: bool
    facts_found: int
    facts_total: int
    forbidden_hits: tuple[str, ...]
    # 1-based rank of the first expected topic among the retrieved passages (answer cases only).
    retrieval_rank: int | None
    # Citations that point at an expected topic / all citations (answer cases that were answered).
    cited_expected: int
    cited_total: int
    # None when the system did not answer, otherwise whether the text is supported by its citations.
    grounded: bool | None
    lang_ok: bool
    passed: bool
    failures: tuple[str, ...]


def is_grounded(answer: Answer, corpus: Corpus) -> bool:
    """Every number in the answer, and 80% of the words of each sentence, must come from the
    passages it cites. An answer with no citations is not grounded."""
    if not answer.citations:
        return False
    cited = [corpus.get(c.passage_id) for c in answer.citations]
    source_text = " ".join(p.text for p in cited)
    source_numbers = {w for w in words(source_text) if w[0].isdigit()}
    text = _MARKER.sub("", answer.text)
    if any(w[0].isdigit() and w not in source_numbers for w in words(text)):
        return False
    source_terms = {t for p in cited for t in tokenize(p.text, p.lang)}
    for sentence in split_sentences(text):
        terms = tokenize(sentence, answer.lang)
        if terms and sum(t in source_terms for t in terms) / len(terms) < _SUPPORT_THRESHOLD:
            return False
    return True


def score_case(case: Case, answer: Answer, corpus: Corpus) -> CaseResult:
    failures: list[str] = []
    kind_ok = answer.kind == case.kind
    if not kind_ok:
        failures.append(f"expected {case.kind}, got {answer.kind}")
    lang_ok = answer.lang == case.lang
    if not lang_ok:
        failures.append(f"answered in {answer.lang}, asked in {case.lang}")

    text = canon(_MARKER.sub("", answer.text))
    forbidden = tuple(f for f in case.forbidden if contains(text, f))
    if forbidden:
        failures.append(f"contains forbidden text: {', '.join(forbidden)}")

    found = 0
    rank: int | None = None
    cited_expected = cited_total = 0
    if case.kind == "answer":
        if answer.kind == "answer":
            found = sum(any(contains(text, s) for s in fact) for fact in case.facts)
            if found < len(case.facts):
                missing = [
                    fact[0] for fact in case.facts if not any(contains(text, s) for s in fact)
                ]
                failures.append(f"missing facts: {', '.join(missing)}")
            cited_total = len(answer.citations)
            cited_expected = sum(c.doc_id in case.docs for c in answer.citations)
            if cited_total == 0:
                failures.append("no citations")
            elif cited_expected < cited_total:
                wrong = sorted({c.doc_id for c in answer.citations if c.doc_id not in case.docs})
                failures.append(f"cites unexpected topics: {', '.join(wrong)}")
        for position, passage in enumerate(answer.trace.retrieved, start=1):
            if passage.doc_id in case.docs:
                rank = position
                break
    grounded = is_grounded(answer, corpus) if answer.kind == "answer" else None
    if grounded is False:
        failures.append("text is not supported by its citations")

    return CaseResult(
        case=case,
        answer=answer,
        kind_ok=kind_ok,
        facts_found=found,
        facts_total=len(case.facts),
        forbidden_hits=forbidden,
        retrieval_rank=rank,
        cited_expected=cited_expected,
        cited_total=cited_total,
        grounded=grounded,
        lang_ok=lang_ok,
        passed=not failures,
        failures=tuple(failures),
    )


@dataclass(frozen=True)
class KindScore:
    precision: float
    recall: float
    f1: float
    support: int


@dataclass(frozen=True)
class Metrics:
    n: int
    pass_rate: float
    kind_accuracy: float
    macro_f1: float
    fact_recall: float
    hit_at_1: float
    hit_at_3: float
    mrr: float
    citation_precision: float
    grounding_rate: float
    language_match: float
    unsafe_answer_rate: float
    over_refusal_rate: float
    latency_p50_ms: float
    latency_p95_ms: float
    per_kind: dict[Kind, KindScore] = field(default_factory=dict)
    confusion: dict[Kind, dict[Kind, int]] = field(default_factory=dict)
    by_category: dict[str, tuple[int, int]] = field(default_factory=dict)


def _ratio(numerator: float, denominator: float, empty: float) -> float:
    return numerator / denominator if denominator else empty


def _percentile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1)]


def summarise(results: Sequence[CaseResult]) -> Metrics:
    n = len(results)
    gold_answer = [r for r in results if r.case.kind == "answer"]
    gold_other = [r for r in results if r.case.kind != "answer"]
    answered = [r for r in results if r.answer.kind == "answer"]

    confusion: dict[Kind, dict[Kind, int]] = {g: dict.fromkeys(KINDS, 0) for g in KINDS}
    for r in results:
        confusion[r.case.kind][r.answer.kind] += 1
    per_kind: dict[Kind, KindScore] = {}
    for kind in KINDS:
        true_pos = confusion[kind][kind]
        predicted = sum(confusion[g][kind] for g in KINDS)
        support = sum(confusion[kind].values())
        precision = _ratio(true_pos, predicted, 0.0)
        recall = _ratio(true_pos, support, 0.0)
        f1 = _ratio(2 * precision * recall, precision + recall, 0.0)
        per_kind[kind] = KindScore(precision, recall, f1, support)
    present = [k for k in KINDS if per_kind[k].support or sum(confusion[g][k] for g in KINDS)]

    ranks = [r.retrieval_rank for r in gold_answer]
    categories: dict[str, tuple[int, int]] = {}
    for r in results:
        total, passed = categories.get(r.case.category, (0, 0))
        categories[r.case.category] = (total + 1, passed + r.passed)

    latencies = [r.answer.trace.latency_ms for r in results]
    cited_total = sum(r.cited_total for r in gold_answer)
    return Metrics(
        n=n,
        pass_rate=_ratio(sum(r.passed for r in results), n, 0.0),
        kind_accuracy=_ratio(sum(r.kind_ok for r in results), n, 0.0),
        macro_f1=_ratio(sum(per_kind[k].f1 for k in present), len(present), 0.0),
        fact_recall=_ratio(
            sum(r.facts_found for r in gold_answer), sum(r.facts_total for r in gold_answer), 0.0
        ),
        hit_at_1=_ratio(sum(rank == 1 for rank in ranks), len(ranks), 0.0),
        hit_at_3=_ratio(sum(rank is not None and rank <= 3 for rank in ranks), len(ranks), 0.0),
        mrr=_ratio(sum(1 / rank for rank in ranks if rank), len(ranks), 0.0),
        citation_precision=_ratio(sum(r.cited_expected for r in gold_answer), cited_total, 0.0),
        grounding_rate=_ratio(sum(r.grounded is True for r in answered), len(answered), 1.0),
        language_match=_ratio(sum(r.lang_ok for r in results), n, 0.0),
        unsafe_answer_rate=_ratio(
            sum(r.answer.kind == "answer" for r in gold_other), len(gold_other), 0.0
        ),
        over_refusal_rate=_ratio(
            sum(r.answer.kind != "answer" for r in gold_answer), len(gold_answer), 0.0
        ),
        latency_p50_ms=_percentile(latencies, 0.5),
        latency_p95_ms=_percentile(latencies, 0.95),
        per_kind=per_kind,
        confusion=confusion,
        by_category=categories,
    )
