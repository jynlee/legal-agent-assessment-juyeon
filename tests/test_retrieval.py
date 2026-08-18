from legal_agent_assessment.contracts import Citation, RetrievalHit
from legal_agent_assessment.retrieval import (
    build_bm25_query,
    build_knn_query,
    reciprocal_rank_fusion,
    source_to_citation,
    source_to_retrieval_hit,
)


def test_build_bm25_query_searches_across_text_and_title_fields() -> None:
    query = build_bm25_query("약사법 제1조", size=50)

    assert query["size"] == 50
    fields = query["query"]["multi_match"]["fields"]
    assert query["query"]["multi_match"]["query"] == "약사법 제1조"
    assert "text^1" in fields
    assert "title^0.5" in fields
    assert "case_name^0.5" in fields
    assert "law_name^0.5" in fields


def test_build_knn_query_uses_script_score_not_the_knn_clause() -> None:
    vector = tuple(0.1 for _ in range(1536))

    query = build_knn_query(vector, size=50)

    assert query["size"] == 50
    script = query["query"]["script_score"]["script"]
    assert script["lang"] == "knn"
    assert script["source"] == "knn_score"
    assert script["params"]["field"] == "embedding"
    assert script["params"]["space_type"] == "cosinesimil"
    assert script["params"]["query_value"] == list(vector)
    # No `method` block anywhere -- this index has none (mapping design
    # Decision 6), so the `knn` query clause (which requires one) must not
    # appear.
    assert "knn" not in query["query"]


def test_reciprocal_rank_fusion_combines_two_lists_by_rank() -> None:
    bm25 = ["a", "b", "c"]
    knn = ["b", "a", "d"]

    fused = reciprocal_rank_fusion([bm25, knn], k=60)

    fused_ids = [chunk_id for chunk_id, _score in fused]
    # "a": 1/61 + 1/62 ; "b": 1/62 + 1/61 -- both appear once in each list at
    # ranks {1,2} and {2,1}, so their totals are equal. "c" and "d" each
    # appear in exactly one list at rank 3, so both are last and equal to
    # each other, but strictly behind "a"/"b".
    assert set(fused_ids[:2]) == {"a", "b"}
    assert set(fused_ids[2:]) == {"c", "d"}


def test_reciprocal_rank_fusion_ranks_a_chunk_in_both_lists_above_one_in_only_one() -> None:
    bm25 = ["x", "y"]
    knn = ["y", "z"]

    fused = reciprocal_rank_fusion([bm25, knn], k=60)

    fused_ids = [chunk_id for chunk_id, _score in fused]
    # "y" appears in both lists (rank 2 and rank 1); "x" and "z" each appear
    # in only one list. "y"'s combined score must beat either single-list
    # top-ranked entry.
    assert fused_ids[0] == "y"


def test_reciprocal_rank_fusion_returns_scores_matching_the_documented_formula() -> None:
    fused = reciprocal_rank_fusion([["only"]], k=60)

    assert fused == [("only", 1 / 61)]


def test_reciprocal_rank_fusion_handles_an_empty_list() -> None:
    assert reciprocal_rank_fusion([[], []], k=60) == []


def test_reciprocal_rank_fusion_defaults_every_list_to_equal_weight() -> None:
    bm25 = ["a"]
    knn = ["b"]

    assert reciprocal_rank_fusion([bm25, knn], k=60) == reciprocal_rank_fusion(
        [bm25, knn], k=60, weights=(1.0, 1.0)
    )


def test_reciprocal_rank_fusion_applies_per_list_weights() -> None:
    # "only-in-bm25" ranks 1st in bm25 and is absent from knn; "only-in-knn"
    # ranks 2nd in knn and is absent from bm25. At equal weight bm25's rank-1
    # entry wins (1/61 > 1/62). A high enough knn weight must be able to flip
    # that ordering -- this is what lets a strong single-retriever signal
    # outrank a weak one instead of RRF's rank-consensus default punishing it.
    bm25 = ["only-in-bm25"]
    knn = ["something-else", "only-in-knn"]

    equal = reciprocal_rank_fusion([bm25, knn], k=60, weights=(1.0, 1.0))
    assert equal[0][0] == "only-in-bm25"

    knn_favored = reciprocal_rank_fusion([bm25, knn], k=60, weights=(1.0, 5.0))
    fused_ids = [chunk_id for chunk_id, _score in knn_favored]
    assert fused_ids.index("only-in-knn") < fused_ids.index("only-in-bm25")


_SOURCE = {
    "chunk_id": "precedent-000001#body-000",
    "document_id": "precedent-000001",
    "title": "판례 제목",
    "source_uri": "https://example.org/case",
    "official_number": "2020구합1",
    "locator": "이유 > 1",
    "text": "본문 예시 텍스트",
}


def test_source_to_retrieval_hit_carries_ids_rank_and_score() -> None:
    hit = source_to_retrieval_hit(_SOURCE, rank=3, score=0.5)

    assert hit == RetrievalHit(
        document_id="precedent-000001",
        chunk_id="precedent-000001#body-000",
        rank=3,
        score=0.5,
    )


def test_source_to_citation_carries_lineage_fields_and_uses_text_as_excerpt() -> None:
    citation = source_to_citation(_SOURCE)

    assert citation == Citation(
        document_id="precedent-000001",
        chunk_id="precedent-000001#body-000",
        title="판례 제목",
        source_uri="https://example.org/case",
        official_number="2020구합1",
        locator="이유 > 1",
        excerpt="본문 예시 텍스트",
    )


def test_source_to_citation_omits_absent_optional_fields() -> None:
    source = {
        "chunk_id": "law-000001#body-000",
        "document_id": "law-000001",
        "title": "약사법 제1조",
        "text": "제1조 본문",
    }

    citation = source_to_citation(source)

    assert citation.source_uri is None
    assert citation.official_number is None
    assert citation.locator is None


def test_source_to_citation_trims_text_longer_than_the_excerpt_limit() -> None:
    source = {**_SOURCE, "text": "가" * 2_100}

    citation = source_to_citation(source)

    assert len(citation.excerpt) == 2_000
    assert citation.excerpt.endswith("...")
