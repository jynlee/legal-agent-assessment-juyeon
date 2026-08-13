from legal_agent_assessment.retrieval import build_bm25_query, build_knn_query


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
