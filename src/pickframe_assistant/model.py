"""The data types that cross module boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

Language = Literal["id", "en"]
LANGUAGES: Final[tuple[Language, ...]] = ("id", "en")

# What the assistant decided to do with a question.
#   answer        a grounded answer with citations
#   handoff       needs a person: the asker's own account or payment, or a request for action
#   abstain       about PickFrame, but the knowledge base does not say, so it refuses to guess
#   out_of_scope  not about PickFrame
#   refuse        an attempt to override the assistant's rules
Kind = Literal["answer", "handoff", "abstain", "out_of_scope", "refuse"]
KINDS: Final[tuple[Kind, ...]] = ("answer", "handoff", "abstain", "out_of_scope", "refuse")


@dataclass(frozen=True)
class Citation:
    """A passage the answer relies on. `n` matches the [n] marker in the answer text."""

    n: int
    passage_id: str
    doc_id: str
    title: str
    heading: str
    source: str


@dataclass(frozen=True)
class RetrievedPassage:
    passage_id: str
    doc_id: str
    heading: str
    score: float


@dataclass(frozen=True)
class Trace:
    """Why the assistant did what it did. Shown in the CLI and in the evaluation report."""

    query_terms: tuple[str, ...]
    retrieved: tuple[RetrievedPassage, ...]
    coverage: float
    decision: str
    latency_ms: float


@dataclass(frozen=True)
class Answer:
    question: str
    lang: Language
    kind: Kind
    text: str
    citations: tuple[Citation, ...]
    trace: Trace
