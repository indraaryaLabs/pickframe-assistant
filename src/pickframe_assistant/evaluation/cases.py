"""Labelled evaluation cases.

Each line of `evals/cases.jsonl` is one case:

    {"id": "d01", "split": "dev", "category": "pricing", "lang": "id",
     "question": "Berapa harga paket Pro per bulan?",
     "kind": "answer",                 what the assistant should do
     "docs": ["pricing"],              topics a correct answer is allowed to cite
     "facts": [["69.000"]],            every inner list is one fact; any one spelling of it will do
     "forbidden": []}                  text that must not appear in the answer

`dev` cases may be used to tune the assistant. `test` cases are only looked at to report results.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from pickframe_assistant.knowledge import Corpus
from pickframe_assistant.model import KINDS, LANGUAGES, Kind, Language
from pickframe_assistant.text import words

SPLITS: Final = ("dev", "test")


def canon(text: str) -> str:
    """Words and numbers in a form where 69.000, 69,000 and Rp 69000 compare equal."""
    return " ".join(words(text))


def contains(haystack_canon: str, needle: str) -> bool:
    """Whole-token containment, so the number 69000 is not found inside 169000."""
    return f" {canon(needle)} " in f" {haystack_canon} "


@dataclass(frozen=True)
class Case:
    id: str
    split: str
    category: str
    lang: Language
    question: str
    kind: Kind
    docs: tuple[str, ...]
    facts: tuple[tuple[str, ...], ...]
    forbidden: tuple[str, ...]


class CaseError(ValueError):
    pass


def load_cases(path: Path) -> list[Case]:
    cases: list[Case] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            cases.append(
                Case(
                    id=str(raw["id"]),
                    split=str(raw["split"]),
                    category=str(raw["category"]),
                    lang=cast(Language, raw["lang"]),
                    question=str(raw["question"]),
                    kind=cast(Kind, raw["kind"]),
                    docs=tuple(raw.get("docs", ())),
                    facts=tuple(tuple(fact) for fact in raw.get("facts", ())),
                    forbidden=tuple(raw.get("forbidden", ())),
                )
            )
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise CaseError(f"{path}:{number}: {error!r}") from error
    return cases


def case_problems(cases: Iterable[Case], corpus: Corpus) -> list[str]:
    """Checks that the labels are well formed and that every expected fact is really in the
    topics the case points at, so a wrong label cannot hide behind a passing score."""
    problems: list[str] = []
    seen: set[str] = set()
    for case in cases:
        where = f"case {case.id}"
        if case.id in seen:
            problems.append(f"{where}: duplicate id")
        seen.add(case.id)
        if case.split not in SPLITS:
            problems.append(f"{where}: unknown split {case.split!r}")
        if case.lang not in LANGUAGES:
            problems.append(f"{where}: unknown language {case.lang!r}")
            continue
        if case.kind not in KINDS:
            problems.append(f"{where}: unknown kind {case.kind!r}")
            continue
        if case.kind != "answer":
            if case.docs or case.facts:
                problems.append(f"{where}: only answer cases have docs and facts")
            continue
        if not case.docs or not case.facts:
            problems.append(f"{where}: an answer case needs docs and facts")
            continue
        known = corpus.doc_ids(case.lang)
        for doc in case.docs:
            if doc not in known:
                problems.append(f"{where}: unknown topic {doc!r} for {case.lang}")
        text = canon(" ".join(corpus.doc_text(doc, case.lang) for doc in case.docs if doc in known))
        for fact in case.facts:
            if not any(contains(text, spelling) for spelling in fact):
                problems.append(f"{where}: fact {list(fact)!r} is not in {list(case.docs)!r}")
    return problems
