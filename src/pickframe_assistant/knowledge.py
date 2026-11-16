"""Loads the knowledge base: Markdown files with a small front matter, one folder per language.

knowledge/<lang>/<topic>.md

    ---
    id: pricing            (must match the file name)
    title: Plan prices
    lang: en               (must match the folder)
    source: https://...    (the public page the facts come from)
    checked: 2026-11-16    (the day the source was last compared with this file)
    ---

    ## A heading
    Self-contained sentences. Each `##` section is one retrievable passage.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pickframe_assistant.model import LANGUAGES, Language
from pickframe_assistant.text import split_sentences

_REQUIRED: Final = ("id", "title", "lang", "source", "checked")
_ENV_VAR: Final = "PICKFRAME_KNOWLEDGE"


class KnowledgeError(ValueError):
    """The knowledge base is malformed. The message names the file."""


@dataclass(frozen=True)
class Passage:
    id: str
    doc_id: str
    title: str
    heading: str
    text: str
    lang: Language
    source: str
    checked: str

    @property
    def sentences(self) -> tuple[str, ...]:
        return tuple(split_sentences(self.text))


@dataclass(frozen=True)
class Corpus:
    passages: tuple[Passage, ...]

    def for_language(self, lang: Language) -> tuple[Passage, ...]:
        return tuple(p for p in self.passages if p.lang == lang)

    def doc_ids(self, lang: Language) -> frozenset[str]:
        return frozenset(p.doc_id for p in self.for_language(lang))

    def doc_text(self, doc_id: str, lang: Language) -> str:
        return "\n".join(p.text for p in self.for_language(lang) if p.doc_id == doc_id)

    def get(self, passage_id: str) -> Passage:
        for passage in self.passages:
            if passage.id == passage_id:
                return passage
        raise KeyError(passage_id)


def default_knowledge_dir() -> Path:
    """`$PICKFRAME_KNOWLEDGE`, or the `knowledge/` folder next to `src/` in a checkout."""
    override = os.environ.get(_ENV_VAR)
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "knowledge"


def _slug(heading: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", heading.casefold()).strip("-")


def _split_front_matter(path: Path, raw: str) -> tuple[dict[str, str], str]:
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        raise KnowledgeError(f"{path}: the file must start with a --- front matter block")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise KnowledgeError(f"{path}: the front matter block is never closed") from None
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if not sep:
            raise KnowledgeError(f"{path}: front matter line without a colon: {line!r}")
        meta[key.strip()] = value.strip()
    missing = [key for key in _REQUIRED if not meta.get(key)]
    if missing:
        raise KnowledgeError(f"{path}: front matter is missing {', '.join(missing)}")
    return meta, "\n".join(lines[end + 1 :])


def _sections(path: Path, body: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    for line in body.splitlines():
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif line.strip():
            if not sections:
                raise KnowledgeError(f"{path}: text before the first ## heading")
            sections[-1][1].append(line.strip())
    if not sections:
        raise KnowledgeError(f"{path}: the file has no ## sections")
    result: list[tuple[str, str]] = []
    for heading, parts in sections:
        if not parts:
            raise KnowledgeError(f"{path}: the section {heading!r} is empty")
        result.append((heading, " ".join(parts)))
    return result


def _load_file(path: Path, lang: Language) -> Iterable[Passage]:
    meta, body = _split_front_matter(path, path.read_text(encoding="utf-8"))
    if meta["lang"] != lang:
        raise KnowledgeError(f"{path}: lang is {meta['lang']!r} but the folder is {lang!r}")
    if meta["id"] != path.stem:
        raise KnowledgeError(f"{path}: id {meta['id']!r} does not match the file name")
    for heading, text in _sections(path, body):
        yield Passage(
            id=f"{lang}/{meta['id']}#{_slug(heading)}",
            doc_id=meta["id"],
            title=meta["title"],
            heading=heading,
            text=text,
            lang=lang,
            source=meta["source"],
            checked=meta["checked"],
        )


def load_corpus(root: Path | None = None) -> Corpus:
    """Reads every language folder under `root` and checks the whole base for consistency."""
    base = root or default_knowledge_dir()
    if not base.is_dir():
        raise KnowledgeError(
            f"{base}: knowledge folder not found. Run from a checkout of the repository "
            f"or set {_ENV_VAR}."
        )
    passages: list[Passage] = []
    for lang in LANGUAGES:
        folder = base / lang
        if not folder.is_dir():
            raise KnowledgeError(f"{folder}: language folder not found")
        for path in sorted(folder.glob("*.md")):
            passages.extend(_load_file(path, lang))
    corpus = Corpus(tuple(passages))
    problems = consistency_problems(corpus)
    if problems:
        raise KnowledgeError("; ".join(problems))
    return corpus


def consistency_problems(corpus: Corpus) -> list[str]:
    """Duplicate ids, and topics that are not present, with the same sections, in every language."""
    problems: list[str] = []
    seen: set[str] = set()
    for passage in corpus.passages:
        if passage.id in seen:
            problems.append(f"duplicate passage id {passage.id}")
        seen.add(passage.id)
    sections = {
        lang: {
            doc: sum(1 for p in corpus.for_language(lang) if p.doc_id == doc)
            for doc in corpus.doc_ids(lang)
        }
        for lang in LANGUAGES
    }
    first, *others = LANGUAGES
    for other in others:
        for doc in sorted(set(sections[first]) | set(sections[other])):
            a, b = sections[first].get(doc), sections[other].get(doc)
            if a != b:
                problems.append(f"topic {doc!r} has {a} sections in {first} but {b} in {other}")
    return problems
