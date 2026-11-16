"""The evaluator is tested against systems whose behaviour is known in advance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pickframe_assistant import Assistant, Corpus
from pickframe_assistant.evaluation import gates
from pickframe_assistant.evaluation.cases import Case
from pickframe_assistant.evaluation.references import (
    AlwaysAbstain,
    OracleSystem,
    RandomRetrieval,
    RetrieveAndDump,
)
from pickframe_assistant.evaluation.runner import ALL, Evaluation, evaluate

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def run(assistant: Assistant, cases: list[Case], corpus: Corpus) -> Evaluation:
    return evaluate(assistant, cases, corpus)


def test_the_oracle_scores_everything(cases: list[Case], corpus: Corpus) -> None:
    metrics = evaluate(OracleSystem(cases, corpus), cases, corpus).metrics()
    assert metrics.pass_rate == 1.0
    assert metrics.unsafe_answer_rate == metrics.over_refusal_rate == 0.0
    assert metrics.grounding_rate == 1.0
    assert metrics.hit_at_1 == 1.0


def test_always_abstain_is_safe_and_useless(cases: list[Case], corpus: Corpus) -> None:
    metrics = evaluate(AlwaysAbstain(), cases, corpus).metrics()
    assert metrics.unsafe_answer_rate == 0.0
    assert metrics.over_refusal_rate == 1.0
    assert metrics.fact_recall == 0.0
    assert metrics.pass_rate < 0.2


def test_retrieve_and_dump_is_caught_as_unsafe(
    assistant: Assistant, cases: list[Case], corpus: Corpus
) -> None:
    metrics = evaluate(RetrieveAndDump(assistant), cases, corpus).metrics()
    assert metrics.unsafe_answer_rate > 0.8
    assert metrics.pass_rate < evaluate(assistant, cases, corpus).metrics().pass_rate


def test_random_retrieval_collapses(cases: list[Case], corpus: Corpus) -> None:
    metrics = evaluate(RandomRetrieval(corpus), cases, corpus).metrics()
    assert metrics.pass_rate < 0.1
    assert metrics.hit_at_3 < 0.3


def test_random_retrieval_is_repeatable(corpus: Corpus) -> None:
    first = [RandomRetrieval(corpus, seed=3).answer("Berapa harga Pro?").text for _ in range(2)]
    assert first[0] == first[1]


def test_the_assistant_beats_every_baseline_on_the_test_split(
    assistant: Assistant, cases: list[Case], corpus: Corpus, run: Evaluation
) -> None:
    mine = run.metrics("test").pass_rate
    for system in (AlwaysAbstain(), RetrieveAndDump(assistant), RandomRetrieval(corpus)):
        assert mine > evaluate(system, cases, corpus).metrics("test").pass_rate


def test_splits_partition_the_cases(run: Evaluation) -> None:
    assert run.metrics("dev").n + run.metrics("test").n == run.metrics(ALL).n == len(run.results)


def test_the_assistant_never_invents_text(run: Evaluation) -> None:
    assert run.metrics().grounding_rate == 1.0
    assert run.metrics().language_match == 1.0


def test_it_is_deterministic(assistant: Assistant, cases: list[Case], corpus: Corpus) -> None:
    again = evaluate(assistant, cases, corpus)
    first = evaluate(assistant, cases, corpus)
    assert [(r.case.id, r.answer.text) for r in again.results] == [
        (r.case.id, r.answer.text) for r in first.results
    ]


def test_the_committed_baseline_is_the_current_behaviour(run: Evaluation) -> None:
    baseline = gates.read_baseline(ROOT / "evals" / "baseline.json")
    assert baseline == gates.snapshot(run)
    assert gates.check(run, baseline) == []


def test_the_gate_catches_a_regression(run: Evaluation) -> None:
    baseline = gates.snapshot(run)
    baseline["splits"]["test"]["pass_rate"] = 0.9
    baseline["splits"]["dev"]["unsafe_answer_rate"] = -0.1
    problems = gates.check(run, baseline)
    assert any("test: pass_rate fell" in p for p in problems)
    assert any("dev: unsafe_answer_rate rose" in p for p in problems)


def test_the_gate_asks_for_a_new_baseline_when_cases_change(run: Evaluation) -> None:
    baseline = gates.snapshot(run)
    baseline["splits"]["dev"]["n"] += 1
    assert "refresh it with --update-baseline" in gates.check(run, baseline)[0]


def test_an_unknown_baseline_version_is_rejected(run: Evaluation) -> None:
    assert "baseline version 9" in gates.check(run, {"version": 9})[0]


def test_floors_and_ceilings_hold_whatever_the_baseline_says(
    assistant: Assistant, cases: list[Case], corpus: Corpus
) -> None:
    bad = evaluate(RetrieveAndDump(assistant), cases, corpus)
    problems = gates.check(bad, {"version": 1, "splits": {}})
    assert any("below the floor" in p for p in problems)
    assert any("above the ceiling" in p for p in problems)


def test_the_baseline_round_trips(tmp_path: Path, run: Evaluation) -> None:
    path = tmp_path / "baseline.json"
    gates.write_baseline(run, path)
    assert json.loads(path.read_text(encoding="utf-8")) == gates.snapshot(run)
    assert gates.read_baseline(path) == gates.snapshot(run)
