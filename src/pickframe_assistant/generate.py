"""Turns retrieved passages into an answer. The default generator never writes a word of its own.

`ExtractiveGenerator` picks the sentences that cover the most of what was asked and quotes them,
each with a [n] marker. Because it can only quote, it cannot state a price the knowledge base does
not contain. A language model can be plugged in behind the same `Generator` protocol (see llm.py);
the evaluation harness holds both to the same checks.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Protocol

from pickframe_assistant.knowledge import Passage
from pickframe_assistant.model import Language

_MARKER: Final = re.compile(r"\[(\d+)\]")
_CONTEXT_SHARE: Final = 0.4


@dataclass(frozen=True)
class GenerationRequest:
    question: str
    lang: Language
    # Retrieved passages, best first.
    passages: Sequence[Passage]
    query_terms: Sequence[str]
    weights: Mapping[str, float]
    # Each passage's retrieval score as a share of the best one, so sentences from the top
    # passage win when two sentences cover the question equally well.
    relevance: Sequence[float]
    tokenize: Callable[[str], list[str]]


@dataclass(frozen=True)
class Generated:
    """`text` cites `sources` as [1], [2], ... in order."""

    text: str
    sources: tuple[Passage, ...]


class Generator(Protocol):
    name: str

    def generate(self, request: GenerationRequest) -> Generated | None:
        """The answer, or None when the passages do not support one."""
        ...


def renumber(text: str, used: Sequence[int]) -> str:
    """Rewrites [k] markers from original passage numbers to 1.. in order of first use."""
    mapping = {original: new for new, original in enumerate(used, start=1)}
    return _MARKER.sub(lambda m: f"[{mapping.get(int(m.group(1)), int(m.group(1)))}]", text)


def cited_numbers(text: str) -> list[int]:
    """Marker numbers in order of first appearance."""
    seen: list[int] = []
    for match in _MARKER.finditer(text):
        number = int(match.group(1))
        if number not in seen:
            seen.append(number)
    return seen


@dataclass(frozen=True)
class _Candidate:
    rank: int
    position: int
    sentence: str
    own: frozenset[str]
    context: frozenset[str]
    prior: float


class ExtractiveGenerator:
    """Greedy set cover: keep adding the sentence covering the most still-missing query weight."""

    name = "extractive"

    def __init__(
        self, max_sentences: int = 4, min_gain: float = 0.06, co_relevance: float = 0.85
    ) -> None:
        self._max_sentences = max_sentences
        self._min_gain = min_gain
        self._co_relevance = co_relevance

    def generate(self, request: GenerationRequest) -> Generated | None:
        total = sum(request.weights[t] for t in set(request.query_terms))
        if total <= 0:
            return None
        candidates = self._candidates(request)
        uncovered = set(request.query_terms)
        chosen: list[_Candidate] = []
        while len(chosen) < self._max_sentences:
            best: tuple[float, _Candidate] | None = None
            for candidate in candidates:
                if candidate in chosen:
                    continue
                if (
                    chosen
                    and candidate.rank != chosen[0].rank
                    and not self._co_relevant(request, candidate.rank)
                ):
                    continue
                gain = candidate.prior * self._weight(request, uncovered, candidate) / total
                # Earlier passages and earlier sentences win ties.
                if best is None or gain > best[0] + 1e-12:
                    best = (gain, candidate)
            if best is None or best[0] <= 0 or (chosen and best[0] < self._min_gain):
                break
            chosen.append(best[1])
            uncovered -= best[1].own
        if not chosen:
            return None
        chosen.sort(key=lambda c: (c.rank, c.position))
        return self._compose(request, chosen)

    def _co_relevant(self, request: GenerationRequest, rank: int) -> bool:
        """Only passages almost as relevant as the best one may add to an answer."""
        return request.relevance[rank] >= self._co_relevance

    @staticmethod
    def _weight(request: GenerationRequest, uncovered: set[str], candidate: _Candidate) -> float:
        """What a sentence is worth: the weight of the still-missing terms it states itself, plus
        a smaller share for those only its heading names."""
        own = sum(request.weights[t] for t in uncovered & candidate.own)
        context = sum(request.weights[t] for t in uncovered & (candidate.context - candidate.own))
        return own + _CONTEXT_SHARE * context

    @staticmethod
    def _candidates(request: GenerationRequest) -> list[_Candidate]:
        out: list[_Candidate] = []
        for rank, passage in enumerate(request.passages):
            context = frozenset(request.tokenize(passage.heading))
            prior = 0.5 + 0.5 * request.relevance[rank]
            for position, sentence in enumerate(passage.sentences):
                own = frozenset(request.tokenize(sentence))
                out.append(_Candidate(rank, position, sentence, own, context, prior))
        return out

    @staticmethod
    def _compose(request: GenerationRequest, chosen: list[_Candidate]) -> Generated:
        sources: list[Passage] = []
        parts: list[str] = []
        for rank in dict.fromkeys(c.rank for c in chosen):
            passage = request.passages[rank]
            sources.append(passage)
            sentences = " ".join(c.sentence for c in chosen if c.rank == rank)
            parts.append(f"{sentences} [{len(sources)}]")
        return Generated(" ".join(parts), tuple(sources))
