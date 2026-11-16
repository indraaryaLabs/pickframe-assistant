"""Command line: ask a question, score the assistant, or check the knowledge base."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from pickframe_assistant.assistant import Assistant
from pickframe_assistant.evaluation import gates
from pickframe_assistant.evaluation.cases import Case, case_problems, load_cases
from pickframe_assistant.evaluation.metrics import System
from pickframe_assistant.evaluation.references import (
    AlwaysAbstain,
    OracleSystem,
    RandomRetrieval,
    RetrieveAndDump,
)
from pickframe_assistant.evaluation.runner import ALL, Evaluation, evaluate
from pickframe_assistant.generate import Generator
from pickframe_assistant.knowledge import KnowledgeError, default_knowledge_dir, load_corpus
from pickframe_assistant.llm import LLMConfig, LLMError, OpenAICompatibleGenerator
from pickframe_assistant.model import Answer, Language

SYSTEMS = ("assistant", "oracle", "always-abstain", "retrieve-and-dump", "random-retrieval")
_SHOWN_METRICS = (
    ("pass_rate", "pass rate"),
    ("kind_accuracy", "right decision"),
    ("macro_f1", "macro F1"),
    ("fact_recall", "fact recall"),
    ("hit_at_3", "hit@3"),
    ("citation_precision", "citation precision"),
    ("grounding_rate", "grounded"),
    ("language_match", "language match"),
    ("unsafe_answer_rate", "unsafe answers"),
    ("over_refusal_rate", "over-refusals"),
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pickframe-assistant",
        description="A grounded support assistant for PickFrame, and the harness that scores it.",
    )
    parser.add_argument(
        "--knowledge", type=Path, help="knowledge base folder (default: ./knowledge)"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    ask = commands.add_parser("ask", help="ask one question")
    ask.add_argument("question")
    ask.add_argument("--lang", choices=("id", "en"), help="answer language (default: detected)")
    ask.add_argument("--json", action="store_true", help="print the full answer as JSON")
    ask.add_argument("--trace", action="store_true", help="show what was retrieved and why")
    ask.add_argument("--llm", action="store_true", help="write the answer with a language model")

    run = commands.add_parser("eval", help="score a system on the labelled cases")
    run.add_argument("--system", choices=SYSTEMS, default="assistant")
    run.add_argument("--split", choices=("dev", "test", ALL), default=ALL)
    run.add_argument("--evals", type=Path, help="folder with cases.jsonl and baseline.json")
    run.add_argument("--llm", action="store_true", help="use the language model generator")
    run.add_argument("--check", action="store_true", help="fail if a gated score regressed")
    run.add_argument("--update-baseline", action="store_true", help="accept the current scores")
    run.add_argument("--report", type=Path, metavar="DIR", help="write the HTML report to DIR")
    run.add_argument("--failures", action="store_true", help="list the cases that failed")

    commands.add_parser("check", help="validate the knowledge base and the labelled cases")
    return parser


def _generator(use_llm: bool) -> Generator | None:
    return OpenAICompatibleGenerator(LLMConfig.from_env()) if use_llm else None


def _evals_dir(arg: Path | None, knowledge: Path | None) -> Path:
    return arg or (knowledge or default_knowledge_dir()).parent / "evals"


def _print_answer(answer: Answer, trace: bool) -> None:
    print(answer.text)
    if answer.citations:
        print()
        for c in answer.citations:
            print(f"  [{c.n}] {c.title} - {c.heading}  ({c.source})")
    if trace:
        t = answer.trace
        print(f"\n  decision: {answer.kind} ({t.decision}); language: {answer.lang}")
        print(f"  terms: {', '.join(t.query_terms) or '-'}; coverage {t.coverage:.2f}")
        for r in t.retrieved:
            print(f"  {r.score:7.2f}  {r.passage_id}")


def _make_system(name: str, assistant: Assistant, cases: Sequence[Case]) -> System:
    if name == "oracle":
        return OracleSystem(list(cases), assistant.corpus)
    if name == "always-abstain":
        return AlwaysAbstain()
    if name == "retrieve-and-dump":
        return RetrieveAndDump(assistant)
    if name == "random-retrieval":
        return RandomRetrieval(assistant.corpus)
    return assistant


def _print_metrics(evaluation: Evaluation, splits: Sequence[str]) -> None:
    print(f"system: {evaluation.system}")
    print(f"{'':22}" + "".join(f"{s:>9}" for s in splits))
    print(f"{'cases':22}" + "".join(f"{evaluation.metrics(s).n:>9}" for s in splits))
    for key, label in _SHOWN_METRICS:
        row = "".join(f"{getattr(evaluation.metrics(s), key):>9.1%}" for s in splits)
        print(f"{label:22}{row}")


def _print_failures(evaluation: Evaluation, split: str) -> None:
    failed = [r for r in evaluation.split(split) if not r.passed]
    print(f"\n{len(failed)} failed in {split}:")
    for r in failed:
        print(f"  {r.case.id}  {r.case.question}")
        print(f"        {'; '.join(r.failures)}")


def _cmd_ask(args: argparse.Namespace) -> int:
    assistant = Assistant(load_corpus(args.knowledge), generator=_generator(args.llm))
    lang: Language | None = args.lang
    answer = assistant.answer(args.question, lang)
    if args.json:
        print(json.dumps(asdict(answer), ensure_ascii=False, indent=2))
    else:
        _print_answer(answer, args.trace)
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    corpus = load_corpus(args.knowledge)
    evals = _evals_dir(args.evals, args.knowledge)
    cases = load_cases(evals / "cases.jsonl")
    problems = case_problems(cases, corpus)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 2
    assistant = Assistant(corpus, generator=_generator(args.llm))
    evaluation = evaluate(_make_system(args.system, assistant, cases), cases, corpus)
    splits = ("dev", "test") if args.split == ALL else (args.split,)
    _print_metrics(evaluation, splits)
    if args.failures:
        for split in splits:
            _print_failures(evaluation, split)
    baseline_path = evals / "baseline.json"
    if args.update_baseline:
        gates.write_baseline(evaluation, baseline_path)
        print(f"\nbaseline written to {baseline_path}")
    gated = args.system == "assistant" and not args.llm and baseline_path.exists()
    gate = gates.check(evaluation, gates.read_baseline(baseline_path)) if gated else None
    if args.report:
        from pickframe_assistant.evaluation.report import write_report

        write_report(args.report, assistant, cases, evaluation, gate)
        print(f"\nreport written to {args.report / 'index.html'}")
    if args.check:
        if gate is None:
            print("--check needs the default assistant and a baseline.json", file=sys.stderr)
            return 2
        if gate:
            print("\nregression gate FAILED:", file=sys.stderr)
            print("\n".join(f"  - {f}" for f in gate), file=sys.stderr)
            return 1
        print("\nregression gate passed")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    corpus = load_corpus(args.knowledge)
    cases = load_cases(_evals_dir(None, args.knowledge) / "cases.jsonl")
    problems = case_problems(cases, corpus)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print(f"ok: {len(corpus.passages)} passages, {len(cases)} cases")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    handlers = {"ask": _cmd_ask, "eval": _cmd_eval, "check": _cmd_check}
    try:
        return handlers[args.command](args)
    except (KnowledgeError, LLMError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
