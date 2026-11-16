from __future__ import annotations

from pickframe_assistant import Assistant
from pickframe_assistant.generate import (
    ExtractiveGenerator,
    GenerationRequest,
    cited_numbers,
    renumber,
)
from pickframe_assistant.text import Analyzer, vocabulary


def _request(assistant: Assistant, question: str, k: int = 1) -> GenerationRequest:
    passages = assistant.top_passages(question, k=k, lang="en")
    analyze: Analyzer = assistant._analyzers["en"]
    terms = list(dict.fromkeys(analyze(question)))
    index = assistant._indexes["en"]
    return GenerationRequest(
        question,
        "en",
        passages,
        terms,
        {t: index.idf(t) for t in terms},
        [1.0] * len(passages),
        analyze,
    )


def test_the_extractive_generator_only_quotes(assistant: Assistant) -> None:
    request = _request(assistant, "How long is the free trial?")
    generated = ExtractiveGenerator().generate(request)
    assert generated is not None
    body = generated.text.rsplit(" [", 1)[0]
    source = " ".join(p.text for p in generated.sources)
    for sentence in body.split(". "):
        assert sentence.rstrip(".") in source


def test_a_question_with_no_weighted_terms_has_no_answer(assistant: Assistant) -> None:
    request = _request(assistant, "How long is the free trial?")
    empty = GenerationRequest(
        request.question, "en", request.passages, [], {}, request.relevance, request.tokenize
    )
    assert ExtractiveGenerator().generate(empty) is None


def test_a_sentence_that_covers_nothing_is_not_quoted(assistant: Assistant) -> None:
    request = _request(assistant, "zzzz qqqq")
    assert ExtractiveGenerator().generate(request) is None


def test_the_sentence_limit_is_respected(assistant: Assistant) -> None:
    request = _request(
        assistant, "What are the plan prices quota limits for projects galleries invoices?"
    )
    generated = ExtractiveGenerator(max_sentences=1).generate(request)
    assert generated is not None
    assert generated.text.count(".") <= 2


def test_markers_are_numbered_in_order_of_first_use() -> None:
    assert cited_numbers("A [3]. B [1] [3].") == [3, 1]
    assert renumber("A [3]. B [1] [3].", [3, 1]) == "A [1]. B [2] [1]."
    assert renumber("A [9]", [3]) == "A [9]"


def test_vocabulary_is_what_stemming_is_checked_against() -> None:
    assert "gallery" in vocabulary(["Client gallery"])
