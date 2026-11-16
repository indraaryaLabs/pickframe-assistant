"""The assistant: route, retrieve, decide whether the knowledge base really covers the question,
then generate an answer with citations, or say clearly why it will not answer."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from pickframe_assistant.bm25 import BM25Index, Hit
from pickframe_assistant.generate import (
    ExtractiveGenerator,
    Generated,
    GenerationRequest,
    Generator,
)
from pickframe_assistant.knowledge import Corpus, Passage
from pickframe_assistant.model import (
    LANGUAGES,
    Answer,
    Citation,
    Kind,
    Language,
    RetrievedPassage,
    Trace,
)
from pickframe_assistant.router import route
from pickframe_assistant.text import DOMAIN_TERMS, Analyzer, detect_language, vocabulary, words

_TIE_BAND: Final = 0.05
# A number the knowledge base never mentions is a claim in the question, not a missing topic.
_UNSEEN_NUMBER_WEIGHT: Final = 0.25

MESSAGES: Final[dict[tuple[Kind, Language], str]] = {
    ("handoff", "id"): (
        "Pertanyaan ini menyangkut akun, pembayaran, atau kode milik Anda, jadi perlu dicek "
        "langsung oleh tim PickFrame. Hubungi tim lewat tombol Pesan sekarang (WhatsApp) di "
        "halaman Harga, dan sertakan email akun serta bukti pembayaran bila ada."
    ),
    ("handoff", "en"): (
        "This is about your own account, payment, or code, so the PickFrame team needs to look "
        "at it directly. Contact the team through the Pesan sekarang (WhatsApp) button on the "
        "Pricing page, and include your account email and proof of payment if you have it."
    ),
    ("abstain", "id"): (
        "Saya tidak menemukan jawabannya di basis pengetahuan PickFrame, dan saya tidak mau "
        "menebak. Tanyakan langsung ke tim PickFrame lewat WhatsApp di halaman Harga."
    ),
    ("abstain", "en"): (
        "I could not find the answer in the PickFrame knowledge base, and I would rather not "
        "guess. Ask the PickFrame team directly through WhatsApp on the Pricing page."
    ),
    ("out_of_scope", "id"): (
        "Saya hanya menjawab pertanyaan seputar PickFrame, misalnya paket, harga, kuota, galeri, "
        "dan dokumen."
    ),
    ("out_of_scope", "en"): (
        "I only answer questions about PickFrame, such as plans, prices, quotas, galleries, and "
        "documents."
    ),
    ("refuse", "id"): (
        "Saya tidak bisa mengikuti instruksi itu. Saya hanya menjawab pertanyaan tentang "
        "PickFrame berdasarkan basis pengetahuan resmi."
    ),
    ("refuse", "en"): (
        "I cannot follow that instruction. I only answer questions about PickFrame from the "
        "official knowledge base."
    ),
}


@dataclass(frozen=True)
class AssistantConfig:
    """The numbers that shape behaviour. `answer_threshold` was tuned on the dev split only."""

    top_k: int = 5
    # A passage is used for the answer when it scores at least this fraction of the best one.
    relative_cutoff: float = 0.5
    max_passages: int = 3
    # The share of the question's (idf-weighted) terms the used passages must contain.
    answer_threshold: float = 0.50


class Assistant:
    name = "assistant"

    def __init__(
        self,
        corpus: Corpus,
        config: AssistantConfig | None = None,
        generator: Generator | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.corpus = corpus
        self.config = config or AssistantConfig()
        self.generator: Generator = generator or ExtractiveGenerator()
        self._clock = clock
        self._passages: dict[Language, tuple[Passage, ...]] = {}
        self._indexes: dict[Language, BM25Index] = {}
        self._analyzers: dict[Language, Analyzer] = {}
        for lang in LANGUAGES:
            passages = corpus.for_language(lang)
            analyzer = Analyzer(
                lang, vocabulary(f"{p.title} {p.heading} {p.text}" for p in passages)
            )
            self._passages[lang] = passages
            self._analyzers[lang] = analyzer
            self._indexes[lang] = BM25Index([self._indexed_terms(p, analyzer) for p in passages])

    @staticmethod
    def _indexed_terms(passage: Passage, analyze: Analyzer) -> list[str]:
        # The heading says what a passage is about, so it counts twice. The title is shared by every
        # passage of a topic, so it counts once.
        heading = analyze(passage.heading)
        return heading + heading + analyze(passage.title) + analyze(passage.text)

    @staticmethod
    def _rank(hits: list[Hit]) -> list[Hit]:
        """Passages within 5% of each other's score are a tie, and a tie goes to the earlier
        section, which by convention is the topic's overview."""
        if not hits:
            return hits
        best = hits[0].score
        return sorted(hits, key=lambda h: (-round(h.score / best / _TIE_BAND), h.index))

    def top_passages(
        self, question: str, k: int = 1, lang: Language | None = None
    ) -> list[Passage]:
        """The best-scoring passages, with no routing and no decision about answering."""
        language = lang or detect_language(question)
        hits = self._indexes[language].search(self._analyzers[language](question), k)
        return [self._passages[language][h.index] for h in hits]

    def answer(self, question: str, lang: Language | None = None) -> Answer:
        started = self._clock()
        language = lang or detect_language(question)

        def finish(
            kind: Kind,
            text: str,
            citations: tuple[Citation, ...],
            terms: tuple[str, ...],
            retrieved: tuple[RetrievedPassage, ...],
            coverage: float,
            decision: str,
        ) -> Answer:
            trace = Trace(terms, retrieved, coverage, decision, (self._clock() - started) * 1000)
            return Answer(question, language, kind, text, citations, trace)

        routed = route(question)
        if routed.kind is not None:
            return finish(
                routed.kind,
                MESSAGES[(routed.kind, language)],
                (),
                (),
                (),
                0.0,
                f"router rule {routed.rule}",
            )

        index = self._indexes[language]
        passages = self._passages[language]
        analyze = self._analyzers[language]
        terms = tuple(dict.fromkeys(analyze(question)))
        hits = self._rank(index.search(terms, self.config.top_k))
        retrieved = tuple(
            RetrievedPassage(
                passages[h.index].id,
                passages[h.index].doc_id,
                passages[h.index].heading,
                round(h.score, 4),
            )
            for h in hits
        )
        if not terms or not hits:
            return self._decline(
                finish, question, terms, retrieved, 0.0, language, "nothing matched"
            )

        floor = hits[0].score * self.config.relative_cutoff
        used = [passages[h.index] for h in hits if h.score >= floor][: self.config.max_passages]
        used_indexes = [h.index for h in hits if h.score >= floor][: self.config.max_passages]
        weights = {t: index.idf(t) for t in terms}
        coverage_weights = {
            t: w * (_UNSEEN_NUMBER_WEIGHT if t[0].isdigit() and t not in index.vocabulary else 1.0)
            for t, w in weights.items()
        }
        covered = set().union(*(index.terms(i) for i in used_indexes))
        coverage = sum(coverage_weights[t] for t in terms if t in covered) / sum(
            coverage_weights.values()
        )

        if coverage < self.config.answer_threshold:
            return self._decline(
                finish,
                question,
                terms,
                retrieved,
                coverage,
                language,
                f"coverage {coverage:.2f} is below {self.config.answer_threshold:.2f}",
            )

        generated = self.generator.generate(
            GenerationRequest(
                question,
                language,
                used,
                terms,
                weights,
                [min(1.0, hits[i].score / hits[0].score) for i in range(len(used))],
                analyze,
            )
        )
        if generated is None:
            return self._decline(
                finish,
                question,
                terms,
                retrieved,
                coverage,
                language,
                "the generator found no answer",
            )
        return finish(
            "answer",
            generated.text,
            self._citations(generated),
            terms,
            retrieved,
            coverage,
            f"coverage {coverage:.2f} by {self.generator.name}",
        )

    @staticmethod
    def _citations(generated: Generated) -> tuple[Citation, ...]:
        return tuple(
            Citation(n, p.id, p.doc_id, p.title, p.heading, p.source)
            for n, p in enumerate(generated.sources, start=1)
        )

    @staticmethod
    def _decline(
        finish: Callable[..., Answer],
        question: str,
        terms: tuple[str, ...],
        retrieved: tuple[RetrievedPassage, ...],
        coverage: float,
        language: Language,
        reason: str,
    ) -> Answer:
        about_pickframe = "pickframe" in words(question) or any(t in DOMAIN_TERMS for t in terms)
        kind: Kind = "abstain" if about_pickframe else "out_of_scope"
        return finish(kind, MESSAGES[(kind, language)], (), terms, retrieved, coverage, reason)
