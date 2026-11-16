from __future__ import annotations

import json
from pathlib import Path

import pytest

from pickframe_assistant import Corpus
from pickframe_assistant.evaluation.cases import (
    Case,
    CaseError,
    canon,
    case_problems,
    contains,
    load_cases,
)
from pickframe_assistant.model import KINDS


def test_every_label_is_consistent_with_the_knowledge_base(
    cases: list[Case], corpus: Corpus
) -> None:
    assert case_problems(cases, corpus) == []


def test_the_case_set_covers_every_decision_in_both_languages_and_splits(cases: list[Case]) -> None:
    assert {c.kind for c in cases} == set(KINDS)
    assert {c.lang for c in cases} == {"id", "en"}
    for split in ("dev", "test"):
        in_split = [c for c in cases if c.split == split]
        assert len(in_split) >= 50
        assert {c.kind for c in in_split} == set(KINDS)


def test_ids_are_unique_and_prefixed_by_split(cases: list[Case]) -> None:
    assert len({c.id for c in cases}) == len(cases)
    assert all(c.id.startswith(c.split[0]) for c in cases)


def test_numbers_compare_equal_however_they_are_written() -> None:
    text = canon("Pro costs Rp 69.000, or 69,000.")
    assert contains(text, "69.000")
    assert contains(text, "Rp 69000")
    assert not contains(canon("Rp 169.000"), "69.000")


def _case(**changes: object) -> Case:
    base: dict[str, object] = {
        "id": "x1",
        "split": "dev",
        "category": "pricing",
        "lang": "en",
        "question": "q",
        "kind": "answer",
        "docs": ("pricing",),
        "facts": (("69,000",),),
        "forbidden": (),
    }
    return Case(**(base | changes))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"split": "val"}, "unknown split"),
        ({"lang": "fr"}, "unknown language"),
        ({"kind": "shrug"}, "unknown kind"),
        ({"docs": ()}, "needs docs and facts"),
        ({"facts": ()}, "needs docs and facts"),
        ({"docs": ("nope",)}, "unknown topic"),
        ({"facts": (("999.999",),)}, "is not in"),
        ({"kind": "abstain"}, "only answer cases"),
    ],
)
def test_a_bad_label_is_reported(corpus: Corpus, changes: dict[str, object], message: str) -> None:
    problems = case_problems([_case(**changes)], corpus)
    assert problems
    assert message in problems[0]
    assert all(p.startswith("case x1") for p in problems)


def test_a_duplicate_id_is_reported(corpus: Corpus) -> None:
    assert "duplicate id" in " ".join(case_problems([_case(), _case()], corpus))


def test_alternative_spellings_of_a_fact_pass_if_any_is_present(corpus: Corpus) -> None:
    assert case_problems([_case(facts=(("999", "69,000"),))], corpus) == []


def test_cases_load_from_jsonl_and_skip_blank_lines(tmp_path: Path) -> None:
    line = {
        "id": "d1",
        "split": "dev",
        "category": "c",
        "lang": "en",
        "question": "q",
        "kind": "refuse",
    }
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps(line) + "\n\n", encoding="utf-8")
    [case] = load_cases(path)
    assert (case.id, case.kind, case.docs, case.facts) == ("d1", "refuse", (), ())


@pytest.mark.parametrize("content", ["{not json}\n", '{"id": "d1"}\n'])
def test_a_malformed_case_names_its_line(tmp_path: Path, content: str) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(CaseError, match=r"cases\.jsonl:1"):
        load_cases(path)
