from __future__ import annotations

import re
from pathlib import Path

import pytest

from pickframe_assistant.knowledge import (
    Corpus,
    KnowledgeError,
    consistency_problems,
    default_knowledge_dir,
    load_corpus,
)


def test_the_real_knowledge_base_loads_in_both_languages(corpus: Corpus) -> None:
    assert corpus.doc_ids("id") == corpus.doc_ids("en")
    assert len(corpus.for_language("id")) == len(corpus.for_language("en")) > 30
    assert consistency_problems(corpus) == []


def test_every_passage_names_its_public_source(corpus: Corpus) -> None:
    for passage in corpus.passages:
        assert passage.source.startswith("https://pickframe.satuarah.click/")
        assert passage.checked == "2026-11-16"


def test_the_knowledge_base_holds_nothing_private(corpus: Corpus) -> None:
    text = " ".join(p.text for p in corpus.passages).casefold()
    for forbidden in ("@gmail", "wa.me", "password:", "api key", "supabase", "token:"):
        assert forbidden not in text
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text), "an email address"
    assert not re.search(r"(?:\+62|\b08)\d[\d\s-]{7,}", text), "a phone number"


def test_passages_are_read_with_ids_and_sentences(tiny_kb: Path) -> None:
    corpus = load_corpus(tiny_kb)
    passage = corpus.for_language("en")[0]
    assert passage.id == "en/pricing#pro-price"
    assert passage.sentences == ("The Pro plan costs Rp 69,000 per month.", "Free costs nothing.")
    assert corpus.get(passage.id) is passage
    assert "69,000" in corpus.doc_text("pricing", "en")
    with pytest.raises(KeyError):
        corpus.get("nope")


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("no front matter\n", "must start with"),
        ("---\nid: pricing\n", "never closed"),
        ("---\nid pricing\n---\n## H\nx\n", "without a colon"),
        ("---\nid: pricing\n---\n## H\nx\n", "missing title"),
        (
            "---\nid: other\ntitle: T\nlang: en\nsource: s\nchecked: c\n---\n## H\nx\n",
            "does not match the file name",
        ),
        (
            "---\nid: pricing\ntitle: T\nlang: id\nsource: s\nchecked: c\n---\n## H\nx\n",
            "but the folder is",
        ),
        (
            "---\nid: pricing\ntitle: T\nlang: en\nsource: s\nchecked: c\n---\ntext first\n## H\nx\n",
            "before the first",
        ),
        ("---\nid: pricing\ntitle: T\nlang: en\nsource: s\nchecked: c\n---\n", "no ## sections"),
        (
            "---\nid: pricing\ntitle: T\nlang: en\nsource: s\nchecked: c\n---\n## H\n",
            "is empty",
        ),
    ],
)
def test_malformed_files_are_rejected_with_the_file_name(
    tiny_kb: Path, content: str, message: str
) -> None:
    (tiny_kb / "en" / "pricing.md").write_text(content, encoding="utf-8")
    with pytest.raises(KnowledgeError, match=message) as error:
        load_corpus(tiny_kb)
    assert "pricing.md" in str(error.value)


def test_a_topic_missing_from_one_language_is_reported(tiny_kb: Path) -> None:
    (tiny_kb / "en" / "pricing.md").rename(tiny_kb / "en" / "other.md")
    text = (
        (tiny_kb / "en" / "other.md")
        .read_text(encoding="utf-8")
        .replace("id: pricing", "id: other")
    )
    (tiny_kb / "en" / "other.md").write_text(text, encoding="utf-8")
    with pytest.raises(KnowledgeError, match="sections in id but None in en"):
        load_corpus(tiny_kb)


def test_duplicate_passage_ids_are_reported(tiny_kb: Path) -> None:
    path = tiny_kb / "en" / "pricing.md"
    path.write_text(path.read_text(encoding="utf-8") + "\n## Pro price\nAgain.\n", encoding="utf-8")
    with pytest.raises(KnowledgeError, match="duplicate passage id"):
        load_corpus(tiny_kb)


def test_missing_folders_have_helpful_errors(tmp_path: Path) -> None:
    with pytest.raises(KnowledgeError, match="knowledge folder not found"):
        load_corpus(tmp_path / "missing")
    with pytest.raises(KnowledgeError, match="language folder not found"):
        load_corpus(tmp_path)


def test_the_environment_can_point_at_another_knowledge_base(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PICKFRAME_KNOWLEDGE", str(tmp_path))
    assert default_knowledge_dir() == tmp_path
    monkeypatch.delenv("PICKFRAME_KNOWLEDGE")
    assert default_knowledge_dir().name == "knowledge"
