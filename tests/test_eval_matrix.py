import json

from evals.benchmarks.run_retrieval_benchmark import BenchmarkScorecard
from evals.generation.run_generation_eval import GenerationBenchmarkScorecard
from evals.run_eval_matrix import EvaluationMatrixResult, evaluate_metric_gates


def _create_mock_scorecards(
    recall_1: float = 0.85,
    recall_3: float = 1.00,
    recall_5: float = 1.00,
    mrr: float = 0.90,
    refusal_prec: float = 1.00,
    hard_negs: int = 0,
    verbatim_match: float = 0.95,
    forbidden_rate: float = 0.00,
    refusal_gen_acc: float = 1.00,
    overall_gen_pass: float = 0.95,
) -> tuple[BenchmarkScorecard, GenerationBenchmarkScorecard]:
    retrieval_card = BenchmarkScorecard(
        total_cases=21,
        actionable_cases=19,
        refusal_cases=2,
        recall_at_1=recall_1,
        recall_at_3=recall_3,
        recall_at_5=recall_5,
        mrr=mrr,
        refusal_precision=refusal_prec,
        hard_negatives_at_rank_1=hard_negs,
    )
    generation_card = GenerationBenchmarkScorecard(
        total_cases=21,
        actionable_cases=19,
        refusal_cases=2,
        verbatim_grounding_match_rate=verbatim_match,
        forbidden_claim_violation_rate=forbidden_rate,
        refusal_generation_accuracy=refusal_gen_acc,
        overall_pass_rate=overall_gen_pass,
    )
    return retrieval_card, generation_card


def test_evaluate_metric_gates_all_pass():
    """Verify that healthy benchmark scorecards pass all quality gates across all 3 tiers."""
    ret_card, gen_card = _create_mock_scorecards()
    tier1, tier2, tier3, overall_passed = evaluate_metric_gates(ret_card, gen_card)

    assert overall_passed is True
    assert len(tier1) == 3
    assert len(tier2) == 3
    assert len(tier3) == 4

    for g in tier1 + tier2 + tier3:
        assert g.passed is True, f"Expected {g.name} to pass, but failed"


def test_evaluate_metric_gates_mrr_drop_fails():
    """Assert that an MRR regression (< 0.80) triggers gate failure."""
    ret_card, gen_card = _create_mock_scorecards(mrr=0.74)
    _, tier2, _, overall_passed = evaluate_metric_gates(ret_card, gen_card)

    assert overall_passed is False
    mrr_gate = next(g for g in tier2 if "MRR" in g.name)
    assert mrr_gate.passed is False
    assert mrr_gate.measured == 0.74


def test_evaluate_metric_gates_forbidden_claim_fails():
    """Assert that any forbidden claim violation (> 0%) triggers gate failure."""
    ret_card, gen_card = _create_mock_scorecards(forbidden_rate=0.048)
    _, _, tier3, overall_passed = evaluate_metric_gates(ret_card, gen_card)

    assert overall_passed is False
    forbidden_gate = next(g for g in tier3 if "Forbidden Claim" in g.name)
    assert forbidden_gate.passed is False


def test_evaluate_metric_gates_hard_negative_fails():
    """Assert that a hard negative appearing at Rank 1 triggers gate failure."""
    ret_card, gen_card = _create_mock_scorecards(hard_negs=1)
    _, tier2, _, overall_passed = evaluate_metric_gates(ret_card, gen_card)

    assert overall_passed is False
    hard_neg_gate = next(g for g in tier2 if "Hard Negatives" in g.name)
    assert hard_neg_gate.passed is False


def test_evaluate_metric_gates_refusal_accuracy_fails():
    """Assert that refusal generation inaccuracy (< 100%) triggers gate failure."""
    ret_card, gen_card = _create_mock_scorecards(refusal_gen_acc=0.50)
    _, _, tier3, overall_passed = evaluate_metric_gates(ret_card, gen_card)

    assert overall_passed is False
    refusal_gate = next(g for g in tier3 if "Refusal Generation" in g.name)
    assert refusal_gate.passed is False


def test_matrix_serialization_and_json_schema():
    """Verify that EvaluationMatrixResult serializes to a clean, well-formed JSON object."""
    ret_card, gen_card = _create_mock_scorecards()
    tier1, tier2, tier3, overall_passed = evaluate_metric_gates(ret_card, gen_card)

    result = EvaluationMatrixResult(
        runbooks_count=20,
        chunks_count=129,
        total_eval_cases=21,
        evaluated_cases=21,
        tier1_retrieval_gates=tier1,
        tier2_reranking_gates=tier2,
        tier3_generation_gates=tier3,
        overall_passed=overall_passed,
        retrieval_scorecard=ret_card,
        generation_scorecard=gen_card,
    )

    data = result.to_dict()
    assert data["system_overview"]["runbooks_count"] == 20
    assert data["system_overview"]["chunks_count"] == 129
    assert data["system_overview"]["total_eval_cases"] == 21
    assert data["overall_passed"] is True
    assert len(data["tier1_retrieval"]) == 3
    assert len(data["tier2_reranking"]) == 3
    assert len(data["tier3_generation"]) == 4

    # Ensure JSON serializable
    json_str = json.dumps(data)
    assert "tier1_retrieval" in json_str
    assert "overall_passed" in json_str
