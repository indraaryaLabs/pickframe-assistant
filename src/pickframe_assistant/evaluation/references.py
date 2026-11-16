"""Reference systems with known behaviour, used to check the evaluator itself.

A scoreboard is only worth trusting if it can tell a good system from a bad one. These systems are
built to sit at the extremes, and the tests assert that the metrics put them there:

* `OracleSystem` knows the labels and quotes the right sentences: it must score 100%.
* `AlwaysAbstain` never answers: it must lose every answer case and never be unsafe.
* `RetrieveAndDump` answers every question with the top passage and never refuses: it must be
  caught as unsafe on questions that should not be answered.
* `RandomRetrieval` cites a random passage: retrieval metrics must collapse.
"""

from __future__ import annotations

import random

from pickframe_assistant.assistant import MESSAGES, Assistant
from pickframe_assistant.evaluation.cases import Case, canon, contains
from pickframe_assistant.knowledge import Corpus, Passage
from pickframe_assistant.model import (
    Answer,
    Citation,
    Kind,
    Language,
    RetrievedPassage,
    Trace,
)
from pickframe_assistant.text import detect_language


def _trace(passages: list[Passage], decision: str) -> Trace:
    retrieved = tuple(RetrievedPassage(p.id, p.doc_id, p.heading, 0.0) for p in passages)
    return Trace((), retrieved, 0.0, decision, 0.0)


def _answer(question: str, lang: Language, kind: Kind, text: str, cited: list[Passage]) -> Answer:
    citations = tuple(
        Citation(n, p.id, p.doc_id, p.title, p.heading, p.source) for n, p in enumerate(cited, 1)
    )
    return Answer(question, lang, kind, text, citations, _trace(cited, "reference system"))


def _quote(passage: Passage, n: int) -> str:
    return f"{passage.text} [{n}]"


class OracleSystem:
    name = "oracle"

    def __init__(self, cases: list[Case], corpus: Corpus) -> None:
        self._cases = {case.question: case for case in cases}
        self._corpus = corpus

    def answer(self, question: str) -> Answer:
        case = self._cases[question]
        if case.kind != "answer":
            return _answer(question, case.lang, case.kind, MESSAGES[(case.kind, case.lang)], [])
        chosen: dict[str, list[str]] = {}
        order: list[Passage] = []
        for fact in case.facts:
            for passage in self._corpus.for_language(case.lang):
                if passage.doc_id not in case.docs:
                    continue
                sentence = next(
                    (s for s in passage.sentences if any(contains(canon(s), x) for x in fact)),
                    None,
                )
                if sentence is None:
                    continue
                if passage not in order:
                    order.append(passage)
                chosen.setdefault(passage.id, [])
                if sentence not in chosen[passage.id]:
                    chosen[passage.id].append(sentence)
                break
        text = " ".join(f"{' '.join(chosen[p.id])} [{n}]" for n, p in enumerate(order, 1))
        return _answer(question, case.lang, "answer", text, order)


class AlwaysAbstain:
    name = "always-abstain"

    def answer(self, question: str) -> Answer:
        lang = detect_language(question)
        return _answer(question, lang, "abstain", MESSAGES[("abstain", lang)], [])


class RetrieveAndDump:
    """Plain search with no routing and no abstaining: whatever ranks first is the answer."""

    name = "retrieve-and-dump"

    def __init__(self, assistant: Assistant) -> None:
        self._assistant = assistant

    def answer(self, question: str) -> Answer:
        lang = detect_language(question)
        top = self._assistant.top_passages(question, k=1, lang=lang)
        if not top:
            return _answer(question, lang, "abstain", MESSAGES[("abstain", lang)], [])
        return _answer(question, lang, "answer", _quote(top[0], 1), top)


class RandomRetrieval:
    name = "random-retrieval"

    def __init__(self, corpus: Corpus, seed: int = 7) -> None:
        self._corpus = corpus
        self._random = random.Random(seed)

    def answer(self, question: str) -> Answer:
        lang = detect_language(question)
        passage = self._random.choice(self._corpus.for_language(lang))
        return _answer(question, lang, "answer", _quote(passage, 1), [passage])
