from __future__ import annotations

from pathlib import Path

import pytest

from pickframe_assistant import Assistant, Corpus, load_corpus
from pickframe_assistant.evaluation.cases import Case, load_cases

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def corpus() -> Corpus:
    return load_corpus(ROOT / "knowledge")


@pytest.fixture(scope="session")
def assistant(corpus: Corpus) -> Assistant:
    return Assistant(corpus)


@pytest.fixture(scope="session")
def cases() -> list[Case]:
    return load_cases(ROOT / "evals" / "cases.jsonl")


@pytest.fixture
def tiny_kb(tmp_path: Path) -> Path:
    """A two-language knowledge base small enough to reason about by hand."""
    for lang, title, heading, text in (
        ("id", "Harga", "Harga Pro", "Paket Pro berharga Rp 69.000 per bulan. Gratis untuk Free."),
        ("en", "Price", "Pro price", "The Pro plan costs Rp 69,000 per month. Free costs nothing."),
    ):
        folder = tmp_path / lang
        folder.mkdir()
        (folder / "pricing.md").write_text(
            f"---\nid: pricing\ntitle: {title}\nlang: {lang}\nsource: https://example.test\n"
            f"checked: 2026-01-01\n---\n\n## {heading}\n{text}\n",
            encoding="utf-8",
        )
    return tmp_path
