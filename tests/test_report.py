from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from pickframe_assistant import Assistant, Corpus
from pickframe_assistant.evaluation.cases import Case
from pickframe_assistant.evaluation.report import ASSETS, write_report
from pickframe_assistant.evaluation.runner import Evaluation, evaluate


@pytest.fixture(scope="module")
def site(
    assistant: Assistant,
    cases: list[Case],
    corpus: Corpus,
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, Evaluation]:
    out = tmp_path_factory.mktemp("site")
    evaluation = evaluate(assistant, cases, corpus)
    write_report(out, assistant, cases, evaluation, gate=[])
    return out, evaluation


def test_the_report_ships_everything_it_needs(site: tuple[Path, Evaluation]) -> None:
    out, _ = site
    assert (out / "index.html").is_file()
    assert (out / "results.json").is_file()
    for name in ASSETS:
        assert (out / "assets" / name).is_file()


def test_the_page_loads_nothing_from_the_network(site: tuple[Path, Evaluation]) -> None:
    out, _ = site
    page = (out / "index.html").read_text(encoding="utf-8")
    urls = re.findall(r'(?:src|href)="([^"#][^"]*)"', page)
    external = [u for u in urls if re.match(r"(https?:)?//", u)]
    assert external == ["https://github.com/indraaryaLabs/pickframe-assistant"]
    css = (out / "assets" / "report.css").read_text(encoding="utf-8")
    assert "http" not in css.replace("http://www.w3.org", "")


def test_every_case_has_a_frame_and_a_record(site: tuple[Path, Evaluation]) -> None:
    out, evaluation = site
    page = (out / "index.html").read_text(encoding="utf-8")
    for result in evaluation.results:
        assert f'id="frame-{result.case.id}"' in page
    data = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert [c["id"] for c in data["cases"]] == [r.case.id for r in evaluation.results]
    assert data["metrics"]["test"]["n"] == evaluation.metrics("test").n


def test_the_embedded_payload_parses_and_matches_results(site: tuple[Path, Evaluation]) -> None:
    out, evaluation = site
    page = (out / "index.html").read_text(encoding="utf-8")
    match = re.search(
        r'<script type="application/json" id="report-data">(.*?)</script>', page, re.S
    )
    assert match
    payload = json.loads(match.group(1))
    assert payload["threshold"] == 0.5
    assert len(payload["cases"]) == len(evaluation.results)
    failed = {c["id"] for c in payload["cases"] if not c["passed"]}
    assert failed == {r.case.id for r in evaluation.results if not r.passed}
    first = payload["cases"][0]
    assert {"id", "question", "facts", "citations", "retrieved", "coverage"} <= first.keys()


def test_the_payload_cannot_close_its_script_tag(
    assistant: Assistant, cases: list[Case], corpus: Corpus, tmp_path: Path
) -> None:
    hostile = Case(
        "d99", "dev", "refuse", "en", "</script><img src=x onerror=alert(1)>", "refuse", (), (), ()
    )
    evaluation = evaluate(assistant, [*cases, hostile], corpus)
    write_report(tmp_path, assistant, [*cases, hostile], evaluation)
    page = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "<img src=x" not in page
    assert page.count("</script>") == 2


def test_the_markup_is_well_formed_enough_to_parse(site: tuple[Path, Evaluation]) -> None:
    out, _ = site
    stack: list[str] = []
    void = {"meta", "link", "input", "br", "img", "path", "use"}

    class Checker(HTMLParser):
        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag not in void:
                stack.append(tag)

        def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            return

        def handle_endtag(self, tag: str) -> None:
            if tag in void:
                return
            assert stack, f"unexpected </{tag}>"
            assert stack.pop() == tag

    Checker().feed((out / "index.html").read_text(encoding="utf-8"))
    assert stack == []


def test_a_gate_verdict_is_shown(
    assistant: Assistant, cases: list[Case], corpus: Corpus, tmp_path: Path
) -> None:
    evaluation = evaluate(assistant, cases, corpus)
    verdicts = {}
    for name, gate in (("pass", []), ("fail", ["x"]), ("none", None)):
        write_report(tmp_path / name, assistant, cases, evaluation, gate)
        verdicts[name] = (tmp_path / name / "index.html").read_text(encoding="utf-8")
    assert "verdict-pass" in verdicts["pass"]
    assert "failed (1)" in verdicts["fail"]
    assert "not checked" in verdicts["none"]


def test_the_report_states_its_own_limits(site: tuple[Path, Evaluation]) -> None:
    out, _ = site
    page = (out / "index.html").read_text(encoding="utf-8")
    assert "Read this before trusting a number" in page
    assert "held out from tuning" in page
    assert "used for tuning, so it flatters" in page


def test_every_failed_case_is_listed_with_a_reason(site: tuple[Path, Evaluation]) -> None:
    out, evaluation = site
    page = (out / "index.html").read_text(encoding="utf-8")
    for result in evaluation.results:
        if not result.passed:
            assert f'data-case="{result.case.id}"' in page
