from __future__ import annotations

import pytest

from pickframe_assistant import Corpus
from pickframe_assistant.evaluation.cases import Case
from pickframe_assistant.evaluation.metrics import is_grounded, score_case, summarise
from pickframe_assistant.model import Answer, Citation, Kind, Language, Trace


def _case(**changes: object) -> Case:
    base: dict[str, object] = {
        "id": "x",
        "split": "test",
        "category": "pricing",
        "lang": "en",
        "question": "q",
        "kind": "answer",
        "docs": ("pricing",),
        "facts": (("69,000",),),
        "forbidden": (),
    }
    return Case(**(base | changes))  # type: ignore[arg-type]


def _answer(
    corpus: Corpus,
    kind: Kind = "answer",
    passage_id: str = "en/pricing#pro-plan-prices",
    text: str | None = None,
    lang: Language = "en",
    retrieved: tuple[str, ...] = ("pricing",),
) -> Answer:
    from pickframe_assistant.model import RetrievedPassage

    passage = corpus.get(passage_id)
    citations = (
        (Citation(1, passage.id, passage.doc_id, passage.title, passage.heading, passage.source),)
        if kind == "answer"
        else ()
    )
    trace = Trace(
        (), tuple(RetrievedPassage(f"{d}#h", d, "h", 1.0) for d in retrieved), 1.0, "", 1.0
    )
    return Answer(
        "q",
        lang,
        kind,
        text if text is not None else f"{passage.sentences[0]} [1]",
        citations,
        trace,
    )


def test_a_correct_answer_passes_every_check(corpus: Corpus) -> None:
    passage = corpus.get("en/pricing#pro-plan-prices")
    answer = _answer(corpus, text=f"{' '.join(passage.sentences)} [1]")
    result = score_case(_case(), answer, corpus)
    assert result.passed, result.failures
    assert (result.facts_found, result.cited_expected, result.retrieval_rank) == (1, 1, 1)
    assert result.grounded is True


def test_each_failure_is_named(corpus: Corpus) -> None:
    result = score_case(_case(kind="handoff", docs=(), facts=()), _answer(corpus), corpus)
    assert result.failures[0] == "expected handoff, got answer"
    result = score_case(_case(), _answer(corpus, lang="id"), corpus)
    assert "answered in id, asked in en" in result.failures
    result = score_case(_case(facts=(("zebra",),)), _answer(corpus), corpus)
    assert "missing facts: zebra" in result.failures
    result = score_case(_case(docs=("trial",)), _answer(corpus), corpus)
    assert "cites unexpected topics: pricing" in result.failures
    result = score_case(_case(forbidden=("Rp",)), _answer(corpus), corpus)
    assert "contains forbidden text: Rp" in result.failures


def test_an_answer_that_cites_nothing_fails(corpus: Corpus) -> None:
    answer = _answer(corpus)
    bare = Answer(answer.question, answer.lang, "answer", "Pro costs 69,000.", (), answer.trace)
    result = score_case(_case(), bare, corpus)
    assert "no citations" in result.failures
    assert result.grounded is False


def test_a_number_the_citation_does_not_contain_is_ungrounded(corpus: Corpus) -> None:
    answer = _answer(corpus, text="The Pro plan costs Rp 12.345 per month. [1]")
    assert not is_grounded(answer, corpus)


def test_a_sentence_the_citation_does_not_support_is_ungrounded(corpus: Corpus) -> None:
    answer = _answer(corpus, text="Photographers adore sunsets over mountains and quiet lakes. [1]")
    assert not is_grounded(answer, corpus)


def test_retrieval_rank_is_the_first_expected_topic(corpus: Corpus) -> None:
    result = score_case(
        _case(), _answer(corpus, retrieved=("trial", "quotas-limits", "pricing")), corpus
    )
    assert result.retrieval_rank == 3
    miss = score_case(_case(), _answer(corpus, retrieved=("trial",)), corpus)
    assert miss.retrieval_rank is None


def test_summary_counts_decisions_and_rates(corpus: Corpus) -> None:
    good = score_case(_case(), _answer(corpus), corpus)
    unsafe = score_case(_case(kind="refuse", docs=(), facts=()), _answer(corpus), corpus)
    refused = score_case(_case(), _answer(corpus, kind="abstain", text="no"), corpus)
    metrics = summarise([good, unsafe, refused])
    assert metrics.n == 3
    assert metrics.unsafe_answer_rate == 1.0
    assert metrics.over_refusal_rate == 0.5
    assert metrics.confusion["refuse"]["answer"] == 1
    assert metrics.confusion["answer"]["abstain"] == 1
    assert metrics.by_category == {"pricing": (3, 0 + good.passed)}
    assert metrics.hit_at_1 == 1.0
    assert metrics.mrr == 1.0


def test_an_empty_run_does_not_divide_by_zero() -> None:
    metrics = summarise([])
    assert metrics.n == 0
    assert metrics.pass_rate == 0.0
    assert metrics.grounding_rate == 1.0
    assert metrics.latency_p95_ms == 0.0


def test_latency_percentiles_pick_observed_values(corpus: Corpus) -> None:
    results = []
    for ms in (1.0, 2.0, 3.0, 4.0, 100.0):
        answer = _answer(corpus)
        timed = Answer(
            answer.question,
            answer.lang,
            answer.kind,
            answer.text,
            answer.citations,
            Trace((), answer.trace.retrieved, 1.0, "", ms),
        )
        results.append(score_case(_case(), timed, corpus))
    metrics = summarise(results)
    assert metrics.latency_p50_ms == 3.0
    assert metrics.latency_p95_ms == 100.0


@pytest.mark.parametrize("kind", ["handoff", "abstain", "out_of_scope", "refuse"])
def test_unanswered_kinds_have_no_grounding_verdict(corpus: Corpus, kind: Kind) -> None:
    result = score_case(
        _case(kind=kind, docs=(), facts=()), _answer(corpus, kind=kind, text="x"), corpus
    )
    assert result.grounded is None
    assert result.passed
