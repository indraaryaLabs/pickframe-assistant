"""The evaluation report: one static page, laid out as a photographer's proof sheet.

Every labelled case is a frame on a contact sheet. A passed case is circled in grease pencil, a
failed one is crossed out, and clicking a frame shows the question, the answer, and what the
assistant retrieved. The page needs no network: fonts, styles and data ship next to it.
"""

from __future__ import annotations

import html
import json
import re
import shutil
from collections.abc import Sequence
from dataclasses import asdict
from importlib import resources
from pathlib import Path
from typing import Any, Final

from pickframe_assistant.assistant import Assistant
from pickframe_assistant.evaluation.cases import Case, canon, contains
from pickframe_assistant.evaluation.metrics import CaseResult, Metrics, System
from pickframe_assistant.evaluation.references import (
    AlwaysAbstain,
    OracleSystem,
    RandomRetrieval,
    RetrieveAndDump,
)
from pickframe_assistant.evaluation.runner import Evaluation, evaluate
from pickframe_assistant.model import KINDS, Kind

REPO_URL: Final = "https://github.com/indraaryaLabs/pickframe-assistant"
STRIP: Final = 12
ASSETS: Final = ("report.css", "report.js", "archivo-latin-wdth-normal.woff2", "Archivo-OFL.txt")

KIND_LABEL: Final[dict[Kind, str]] = {
    "answer": "answer",
    "handoff": "hand off",
    "abstain": "abstain",
    "out_of_scope": "out of scope",
    "refuse": "refuse",
}
_KIND_ICON: Final[dict[Kind, str]] = {
    "answer": "M5 7h14M5 12h14M5 17h9",
    "handoff": "M4 12h10M10 8l4 4-4 4M19 5v14",
    "abstain": "M8.5 9.5a3.7 3.7 0 1 1 5.2 3.4c-1 .5-1.7 1.1-1.7 2.3M12 19v.01",
    "out_of_scope": "M12 5a7 7 0 1 0 0 14 7 7 0 0 0 0-14ZM7 17 17 7",
    "refuse": "M9 4h6l5 5v6l-5 5H9l-5-5V9ZM8 12h8",
}
_RING: Final = "M52 9C80 8 95 28 92 52S70 94 44 91 6 72 9 46 28 10 56 11C66 11 72 14 77 18"
_CROSS: Final = "M14 17L86 84M85 14L16 86"

_DEFINITIONS: Final[tuple[tuple[str, str, str], ...]] = (
    ("pass_rate", "Pass rate", "Cases where every check passed: decision, language, facts, citations, grounding."),
    ("kind_accuracy", "Right decision", "Answer, hand off, abstain, out of scope or refuse, chosen correctly."),
    ("macro_f1", "Macro F1", "F1 averaged over the five decisions, so rare ones count as much as common ones."),
    ("fact_recall", "Fact recall", "Facts the answers needed that were stated. An unanswered question scores zero."),
    ("hit_at_3", "Hit at 3", "A passage from the right topic was among the top three retrieved."),
    ("citation_precision", "Citation precision", "Cited passages that belong to a topic allowed to answer."),
    ("grounding_rate", "Grounded", "Answers whose numbers and sentences are all supported by their citations."),
    ("language_match", "Language match", "Replies written in the language of the question."),
    ("unsafe_answer_rate", "Unsafe answers", "Questions the bot should not answer that it answered anyway. Lower is better."),
    ("over_refusal_rate", "Over-refusals", "Answerable questions it declined. Lower is better."),
)  # fmt: skip

_REFERENCES: Final[tuple[tuple[str, str], ...]] = (
    ("oracle", "Knows the labels and quotes the right sentences. The ceiling."),
    ("retrieve-and-dump", "Search only: the best passage is the answer, nothing is ever refused."),
    ("always-abstain", "Never answers. Safe, and useless."),
    ("random-retrieval", "Cites a random passage. The floor."),
)

_e = html.escape
_MARKER: Final = re.compile(r"\s*\[\d+\]")


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _reference_systems(assistant: Assistant, cases: Sequence[Case]) -> list[System]:
    return [
        OracleSystem(list(cases), assistant.corpus),
        RetrieveAndDump(assistant),
        AlwaysAbstain(),
        RandomRetrieval(assistant.corpus),
    ]


def _case_payload(result: CaseResult) -> dict[str, Any]:
    case, answer = result.case, result.answer
    text = canon(_MARKER.sub("", answer.text))
    facts = [
        {"label": fact[0], "found": any(contains(text, s) for s in fact)} for fact in case.facts
    ]
    return {
        "id": case.id,
        "split": case.split,
        "category": case.category,
        "lang": case.lang,
        "question": case.question,
        "expected": case.kind,
        "got": answer.kind,
        "passed": result.passed,
        "failures": list(result.failures),
        "facts": facts,
        "answer": answer.text,
        "citations": [asdict(c) for c in answer.citations],
        "retrieved": [{"id": r.passage_id, "score": r.score} for r in answer.trace.retrieved],
        "coverage": answer.trace.coverage,
        "decision": answer.trace.decision,
    }


def _frame(result: CaseResult, index: int) -> str:
    case = result.case
    passed = result.passed
    label = f"{case.id}, {case.category}, {'passed' if passed else 'failed'}: {case.question}"
    path, kind = (_RING, "ring") if passed else (_CROSS, "cross")
    return (
        f'<button class="frame" type="button" id="frame-{_e(case.id)}" data-id="{_e(case.id)}" '
        f'data-split="{_e(case.split)}" data-passed="{str(passed).lower()}" '
        f'data-category="{_e(case.category)}" aria-pressed="false" aria-label="{_e(label)}">'
        f'<svg class="kind" viewBox="0 0 24 24" aria-hidden="true"><use href="#k-{case.kind}"/></svg>'
        f'<span class="num">{_e(case.id)}</span>'
        f'<svg class="mark {kind}" viewBox="0 0 100 100" aria-hidden="true" style="--i:{index}">'
        f'<path pathLength="1" d="{path}"/></svg></button>'
    )


def _sheet(results: Sequence[CaseResult]) -> str:
    strips: list[str] = []
    for start in range(0, len(results), STRIP):
        chunk = results[start : start + STRIP]
        frames = "".join(_frame(r, start + i) for i, r in enumerate(chunk))
        edge = (
            f'<div class="edge" aria-hidden="true"><span>PF-ASSIST 400 &#9656; {_e(chunk[0].case.id)}'
            f" to {_e(chunk[-1].case.id)}</span><span>roll {start // STRIP + 1}</span></div>"
        )
        strips.append(f'<div class="strip">{edge}<div class="frames">{frames}</div></div>')
    return "\n".join(strips)


def _sprite() -> str:
    symbols = "".join(
        f'<symbol id="k-{kind}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="{_KIND_ICON[kind]}"/></symbol>'
        for kind in KINDS
    )
    return f'<svg width="0" height="0" style="position:absolute" aria-hidden="true">{symbols}</svg>'


def _legend() -> str:
    kinds = "".join(
        f'<li><span class="swatch"><svg viewBox="0 0 24 24" aria-hidden="true"><use href="#k-{k}"/></svg>'
        f"</span>{KIND_LABEL[k]}</li>"
        for k in KINDS
    )
    marks = (
        '<li><svg viewBox="0 0 100 100" aria-hidden="true"><path d="' + _RING + '" fill="none" '
        'stroke="#c9a200" stroke-width="9" stroke-linecap="round"/></svg>passed</li>'
        '<li><svg viewBox="0 0 100 100" aria-hidden="true"><path d="' + _CROSS + '" fill="none" '
        'stroke="#e04a50" stroke-width="10" stroke-linecap="round"/></svg>failed</li>'
    )
    return f'<ul class="legend" aria-label="Legend">{marks}{kinds}</ul>'


def _filters(cases: Sequence[Case]) -> str:
    def radios(name: str, options: Sequence[tuple[str, str]]) -> str:
        items = "".join(
            f'<label><input type="radio" name="{name}" value="{value}"'
            f"{' checked' if i == 0 else ''}>{_e(text)}</label>"
            for i, (value, text) in enumerate(options)
        )
        return items

    n = {s: sum(c.split == s for c in cases) for s in ("dev", "test")}
    categories = "".join(
        f'<option value="{_e(c)}">{_e(c.replace("_", " "))}</option>'
        for c in sorted({c.category for c in cases})
    )
    return (
        '<form class="toolbar" id="filters" aria-label="Filter the sheet">'
        f"<fieldset><legend>Split</legend>{radios('split', [('all', f'All {len(cases)}'), ('dev', f'Dev {n["dev"]}'), ('test', f'Test {n["test"]}')])}</fieldset>"
        f"<fieldset><legend>Result</legend>{radios('result', [('all', 'Any result'), ('passed', 'Passed'), ('failed', 'Failed')])}</fieldset>"
        '<label class="visually-select"><span class="sr">Category</span>'
        f'<select name="category"><option value="all">All categories</option>{categories}</select></label>'
        "</form>"
    )


def _vitals(evaluation: Evaluation, gate: list[str] | None) -> str:
    dev, test = evaluation.metrics("dev"), evaluation.metrics("test")
    passed = round(test.pass_rate * test.n)
    if gate is None:
        verdict, css = "not checked", ""
    elif gate:
        verdict, css = f"failed ({len(gate)})", "verdict-fail"
    else:
        verdict, css = "passed", "verdict-pass"
    return (
        '<dl class="vitals">'
        f"<div><dt>Held-out test cases passed</dt><dd>{_pct(test.pass_rate)}"
        f"<small>{passed} of {test.n}</small></dd></div>"
        f"<div><dt>Dev cases passed</dt><dd>{_pct(dev.pass_rate)}"
        f"<small>used for tuning, so it flatters</small></dd></div>"
        f"<div><dt>Unsafe answers on test</dt><dd>{_pct(test.unsafe_answer_rate)}"
        f"<small>should have been refused</small></dd></div>"
        f'<div><dt>Regression gate</dt><dd class="{css}">{verdict}'
        f"<small>against the committed baseline</small></dd></div></dl>"
    )


def _metrics_table(evaluation: Evaluation) -> str:
    dev, test = evaluation.metrics("dev"), evaluation.metrics("test")
    rows = "".join(
        f'<tr><th scope="row">{label}<span class="def">{text}</span></th>'
        f'<td class="num">{_pct(getattr(dev, key))}</td><td class="num">{_pct(getattr(test, key))}</td></tr>'
        for key, label, text in _DEFINITIONS
    )
    return (
        '<div class="scroll"><table><caption>Every score is a rule applied to the answer, '
        "never a judgement call.</caption><thead><tr><th>Metric</th>"
        f'<th class="num">Dev ({dev.n})</th><th class="num">Test ({test.n})</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div>"
    )


def _reference_table(evaluation: Evaluation, others: Sequence[Evaluation]) -> str:
    descriptions = dict(_REFERENCES)
    ordered = [e for name, _ in _REFERENCES for e in others if e.system == name]

    def row(e: Evaluation, text: str, css: str = "") -> str:
        m = e.metrics("test")
        return (
            f'<tr class="{css}"><th scope="row">{_e(e.system)}<span class="def">{_e(text)}</span></th>'
            f'<td class="num">{_pct(m.pass_rate)}</td><td class="num">{_pct(m.unsafe_answer_rate)}</td>'
            f'<td class="num">{_pct(m.over_refusal_rate)}</td><td class="num">{_pct(m.hit_at_3)}</td></tr>'
        )

    body = row(ordered[0], descriptions[ordered[0].system])
    body += row(evaluation, "The system on trial.", "self")
    body += "".join(row(e, descriptions[e.system]) for e in ordered[1:])
    return (
        '<div class="scroll"><table><caption>Test split.</caption><thead><tr><th>System</th>'
        '<th class="num">Pass rate</th><th class="num">Unsafe answers</th>'
        '<th class="num">Over-refusals</th><th class="num">Hit at 3</th></tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


def _category_table(evaluation: Evaluation) -> str:
    dev, test = evaluation.metrics("dev"), evaluation.metrics("test")
    names = sorted(set(dev.by_category) | set(test.by_category))

    def cell(metrics: Metrics, name: str) -> str:
        total, passed = metrics.by_category.get(name, (0, 0))
        return f'<td class="num">{passed} / {total}</td>' if total else '<td class="num">-</td>'

    rows = "".join(
        f'<tr><th scope="row">{_e(n.replace("_", " "))}</th>{cell(dev, n)}{cell(test, n)}</tr>'
        for n in names
    )
    return (
        '<div class="scroll"><table><caption>Cases passed out of cases asked.</caption>'
        '<thead><tr><th>Category</th><th class="num">Dev</th><th class="num">Test</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div>"
    )


def _confusion(evaluation: Evaluation) -> str:
    test = evaluation.metrics("test")
    head = "".join(f'<th class="num" scope="col">{KIND_LABEL[k]}</th>' for k in KINDS)
    rows = ""
    for expected in KINDS:
        total = sum(test.confusion[expected].values()) or 1
        cells = ""
        for got in KINDS:
            count = test.confusion[expected][got]
            kind = "diag" if expected == got else "off"
            weight = count / total
            cells += (
                f'<td data-cell="{kind}" style="--w:{weight:.2f}">{count or ""}</td>'
                if count
                else "<td></td>"
            )
        rows += f'<tr><th scope="row">{KIND_LABEL[expected]}</th>{cells}</tr>'
    return (
        '<div class="scroll"><table class="matrix"><caption>Test split. Rows are what the case '
        "expected, columns are what the assistant did.</caption>"
        f"<thead><tr><th>Expected</th>{head}</tr></thead><tbody>{rows}</tbody></table></div>"
    )


def _failures(evaluation: Evaluation) -> str:
    failed = [r for r in evaluation.split("test") if not r.passed] + [
        r for r in evaluation.split("dev") if not r.passed
    ]
    if not failed:
        return "<p>Every case passed.</p>"
    rows = "".join(
        f'<tr><td><a href="#{_e(r.case.id)}" data-case="{_e(r.case.id)}">{_e(r.case.id)}</a></td>'
        f"<td>{_e(r.case.split)}</td><td>{_e(r.case.question)}</td>"
        f"<td>{KIND_LABEL[r.case.kind]} &rarr; {KIND_LABEL[r.answer.kind]}</td>"
        f"<td>{_e('; '.join(r.failures))}</td></tr>"
        for r in failed
    )
    return (
        '<div class="scroll"><table><thead><tr><th>Case</th><th>Split</th><th>Question</th>'
        f"<th>Expected &rarr; got</th><th>Why</th></tr></thead><tbody>{rows}</tbody></table></div>"
    )


def render(
    assistant: Assistant,
    cases: Sequence[Case],
    evaluation: Evaluation,
    references: Sequence[Evaluation],
    gate: list[str] | None,
) -> str:
    payload = json.dumps(
        {
            "threshold": assistant.config.answer_threshold,
            "cases": [_case_payload(r) for r in evaluation.results],
        },
        ensure_ascii=False,
    ).replace("<", "\\u003c")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PickFrame Assistant: evaluation proof sheet</title>
<meta name="description" content="How well a grounded support assistant for PickFrame answers {len(cases)} labelled questions, and where it fails.">
<link rel="stylesheet" href="assets/report.css">
<style>.sr{{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}}</style>
</head>
<body>
{_sprite()}
<div class="wrap">
<header class="masthead">
<div>
<h1>PickFrame Assistant, on the proof sheet</h1>
<p class="lede">{len(cases)} labelled questions, each one a frame. A ring means the assistant got it right; a cross means it did not. Click any frame to see the question, the answer, and what the search found. Every number on this page comes from rules, not opinions.</p>
</div>
{_vitals(evaluation, gate)}
</header>

<div class="layout">
<section id="sheet" aria-labelledby="sheet-title">
<h2 id="sheet-title">Contact sheet</h2>
{_filters(cases)}
{_sheet(evaluation.results)}
{_legend()}
</section>
<aside class="panel" aria-live="polite" aria-label="Selected case">
<div id="panel-body"><p class="empty">Select a frame to see the case.</p></div>
</aside>
</div>

<section class="block" aria-labelledby="scores">
<h2 id="scores">Scores</h2>
<p>The dev split was used to tune the assistant, so its scores flatter it. The test split was only read after tuning, so the test column is the one to quote.</p>
{_metrics_table(evaluation)}
</section>

<section class="block" aria-labelledby="refs">
<h2 id="refs">Can the scoreboard tell good from bad?</h2>
<p>A scoreboard is only worth trusting if it can tell a perfect system from a useless one. These reference systems have known behaviour, and the evaluator is checked against them on every test run.</p>
{_reference_table(evaluation, references)}
</section>

<section class="block" aria-labelledby="failed">
<h2 id="failed">What went wrong</h2>
<p>Every failed case, test split first. Open one on the sheet for the passages behind it.</p>
{_failures(evaluation)}
</section>

<section class="block" aria-labelledby="cats">
<h2 id="cats">By kind of question</h2>
{_category_table(evaluation)}
</section>

<section class="block" aria-labelledby="matrix">
<h2 id="matrix">What it decided</h2>
{_confusion(evaluation)}
</section>

<section class="block" aria-labelledby="limits">
<h2 id="limits">Read this before trusting a number</h2>
<ul class="notes">
<li>One person wrote the knowledge base and the cases. The test split is held out from tuning, not independent of the author.</li>
<li>With {evaluation.metrics("test").n} test cases, one case moves a score by about {100 / max(1, evaluation.metrics("test").n):.1f} points. Compare systems by the failed cases, not by small gaps.</li>
<li>Facts are checked by matching words, so a correct answer worded very differently from the labels would be marked wrong. The extractive generator quotes the knowledge base, so it rarely is.</li>
<li>The knowledge base comes from PickFrame's public pages. The live site is the authority.</li>
</ul>
</section>
<footer>Built by <a href="{REPO_URL}">pickframe-assistant</a>. <a href="results.json">results.json</a> has every answer and trace.</footer>
</div>
<script type="application/json" id="report-data">{payload}</script>
<script src="assets/report.js" defer></script>
</body>
</html>
"""


def write_report(
    out: Path,
    assistant: Assistant,
    cases: Sequence[Case],
    evaluation: Evaluation,
    gate: list[str] | None = None,
) -> None:
    """Writes index.html, results.json and the assets folder into `out`."""
    references = [
        evaluate(system, cases, assistant.corpus) for system in _reference_systems(assistant, cases)
    ]
    assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    package = resources.files("pickframe_assistant.evaluation") / "assets"
    for name in ASSETS:
        with resources.as_file(package / name) as source:
            shutil.copyfile(source, assets / name)
    (out / "index.html").write_text(
        render(assistant, cases, evaluation, references, gate), encoding="utf-8"
    )
    results = {
        "system": evaluation.system,
        "threshold": assistant.config.answer_threshold,
        "metrics": {s: _metrics_json(evaluation.metrics(s)) for s in ("dev", "test")},
        "cases": [_case_payload(r) for r in evaluation.results],
    }
    (out / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _metrics_json(metrics: Metrics) -> dict[str, Any]:
    return asdict(metrics)
