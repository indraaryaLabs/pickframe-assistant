"""Runs a system over the cases."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pickframe_assistant.evaluation.cases import Case
from pickframe_assistant.evaluation.metrics import (
    CaseResult,
    Metrics,
    System,
    score_case,
    summarise,
)
from pickframe_assistant.knowledge import Corpus

ALL: str = "all"


@dataclass(frozen=True)
class Evaluation:
    system: str
    results: tuple[CaseResult, ...]

    def split(self, name: str) -> tuple[CaseResult, ...]:
        if name == ALL:
            return self.results
        return tuple(r for r in self.results if r.case.split == name)

    def metrics(self, name: str = ALL) -> Metrics:
        return summarise(self.split(name))


def evaluate(system: System, cases: Sequence[Case], corpus: Corpus) -> Evaluation:
    results = tuple(score_case(case, system.answer(case.question), corpus) for case in cases)
    return Evaluation(system.name, results)
