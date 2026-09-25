from packages.knowledge.hybrid_search import search_runbooks


def test_exact_error_lexical_hit():
    """Test 1: Query with a precise error string."""
    query = "asyncpg.exceptions.TimeoutError or pool acquire timeout"
    results = search_runbooks(query, top_k=3)
    assert len(results) > 0, "Expected non-empty result list"
    assert results[0].runbook_id == "RB-PG-001", (
        f"Expected top hit to be RB-PG-001, got {results[0].runbook_id}"
    )
    # This query should be extremely well-grounded, scoring significantly above the refusal threshold.
    assert results[0].rerank_score >= -11.5


def test_semantic_symptom_hit():
    """Test 2: Query describing a symptom conceptually without exact code names."""
    query = "Shoppers getting logged out because session cache memory is exhausted"
    results = search_runbooks(query, top_k=3)
    assert len(results) > 0, "Expected non-empty result list"
    assert results[0].runbook_id == "RB-REDIS-001", (
        f"Expected top hit to be RB-REDIS-001, got {results[0].runbook_id}"
    )
    assert results[0].rerank_score >= -11.5


def test_refusal_gate():
    """Test 3: Querying an out-of-domain concept should trigger the refusal gate."""
    query = "Quantum entanglement packet loss on Mars edge router"
    results = search_runbooks(query, top_k=3)
    assert len(results) == 0, (
        f"Expected refusal gate to trigger and return empty list, but got {len(results)} results."
    )
