import pytest

from evals.benchmarks.run_retrieval_benchmark import evaluate_retrieval


@pytest.fixture(scope="module")
def scorecard():
    """Execute the retrieval benchmark suite once across all benchmark assertions."""
    return evaluate_retrieval()


def test_retrieval_recall_gates(scorecard):
    """
    Assert that retrieval Recall gates meet required thresholds:
    - Recall@1 >= 0.70
    - Recall@3 >= 0.85
    - Recall@5 >= 0.90
    """
    assert scorecard.recall_at_1 >= 0.70, (
        f"Recall@1 failed: expected >= 0.70, got {scorecard.recall_at_1:.4f}"
    )
    assert scorecard.recall_at_3 >= 0.85, (
        f"Recall@3 failed: expected >= 0.85, got {scorecard.recall_at_3:.4f}"
    )
    assert scorecard.recall_at_5 >= 0.90, (
        f"Recall@5 failed: expected >= 0.90, got {scorecard.recall_at_5:.4f}"
    )


def test_retrieval_mrr_gate(scorecard):
    """
    Assert that Mean Reciprocal Rank (MRR) meets the target gate >= 0.80.
    In voice CallOps, a high MRR ensures top-ranked chunks dominate prompt context
    and avoid token budget waste or LLM attention dilution.
    """
    assert scorecard.mrr >= 0.80, (
        f"MRR failed: expected >= 0.80, got {scorecard.mrr:.4f}"
    )


def test_refusal_precision_gate(scorecard):
    """
    Assert that Refusal Precision is exactly 1.0 (100%).
    Out-of-domain or undocumented queries must trigger the refusal gate and return 0 chunks.
    """
    assert scorecard.refusal_precision == 1.0, (
        f"Refusal Precision failed: expected 1.0, got {scorecard.refusal_precision:.4f}"
    )


def test_zero_hard_negatives_at_rank_1(scorecard):
    """
    Assert that zero distractor / hard-negative chunks place at Rank 1.
    """
    assert scorecard.hard_negatives_at_rank_1 == 0, (
        f"Hard negatives appeared at Rank 1: count={scorecard.hard_negatives_at_rank_1}"
    )
    assert scorecard.hard_negative_pass_rate == 1.0


def test_individual_case_integrity(scorecard):
    """
    Verify each individual case in the scorecard satisfies its category requirements.
    """
    assert scorecard.total_cases >= 5
    assert scorecard.actionable_cases >= 4
    assert scorecard.refusal_cases >= 1

    for m in scorecard.case_metrics:
        if m.should_refuse:
            assert m.refusal_ok is True, f"Refusal failed for case {m.case_id}"
            assert m.hit_rank is None
        else:
            assert m.hit_rank is not None, f"Expected hit for case {m.case_id}"
            assert m.hit_rank <= 3, (
                f"Case {m.case_id} ranked too low: rank={m.hit_rank}"
            )
            assert m.hard_negative_ok is True, (
                f"Hard negative check failed for {m.case_id}"
            )
