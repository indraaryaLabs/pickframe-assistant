from __future__ import annotations

import math

from pickframe_assistant.bm25 import BM25Index


def test_the_matching_document_ranks_first() -> None:
    index = BM25Index([["price", "pro"], ["gallery", "photo"], ["price", "studio", "studio"]])
    hits = index.search(["gallery"], 5)
    assert [h.index for h in hits] == [1]
    assert index.search(["price", "studio"], 5)[0].index == 2


def test_documents_without_a_matching_term_are_not_returned() -> None:
    assert BM25Index([["a"], ["b"]]).search(["zzz"], 5) == []


def test_k_limits_the_result_and_ties_keep_document_order() -> None:
    index = BM25Index([["x"], ["x"], ["x"]])
    assert [h.index for h in index.search(["x"], 2)] == [0, 1]


def test_a_rarer_term_weighs_more() -> None:
    index = BM25Index([["common", "rare"], ["common"], ["common"], ["common"]])
    assert index.idf("rare") > index.idf("common")
    assert index.idf("never-seen") > index.idf("rare")


def test_idf_matches_the_formula() -> None:
    index = BM25Index([["a"], ["b"]])
    assert index.idf("a") == math.log(1 + (2 - 1 + 0.5) / (1 + 0.5))


def test_empty_index_and_introspection() -> None:
    assert BM25Index([]).search(["a"], 3) == []
    index = BM25Index([["a", "b"], ["c"]])
    assert len(index) == 2
    assert index.vocabulary == {"a", "b", "c"}
    assert index.terms(0) == {"a", "b"}
