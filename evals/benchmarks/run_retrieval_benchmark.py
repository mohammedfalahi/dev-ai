import sys
from dataclasses import dataclass, field
from pathlib import Path

# Ensure project root is in sys.path when executed directly
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evals.schemas import GoldenEvalCase
from packages.knowledge.hybrid_search import search_runbooks

DEFAULT_DATASET = Path("evals/datasets/golden_dataset.jsonl")


@dataclass
class CaseMetric:
    case_id: str
    category: str
    query: str
    should_refuse: bool
    top_chunk: str | None = None
    top_rerank_score: float | None = None
    hit_rank: int | None = None
    reciprocal_rank: float = 0.0
    recall_at_1: float = 0.0
    recall_at_3: float = 0.0
    recall_at_5: float = 0.0
    refusal_ok: bool = True
    hard_negative_ok: bool = True


@dataclass
class BenchmarkScorecard:
    total_cases: int = 0
    actionable_cases: int = 0
    refusal_cases: int = 0
    recall_at_1: float = 0.0
    recall_at_3: float = 0.0
    recall_at_5: float = 0.0
    mrr: float = 0.0
    refusal_precision: float = 0.0
    hard_negative_pass_rate: float = 1.0
    hard_negatives_at_rank_1: int = 0
    case_metrics: list[CaseMetric] = field(default_factory=list)


def evaluate_retrieval(
    dataset_path: str | Path = DEFAULT_DATASET,
    top_k: int = 5,
) -> BenchmarkScorecard:
    """
    Execute 100% deterministic, pure-Python retrieval evaluation against a dataset.
    Does NOT call any LLM-as-a-judge; metrics are computed via set intersection and rank math.
    """
    path = Path(dataset_path)
    if not path.is_file():
        raise FileNotFoundError(f"Evaluation dataset not found at {path}")

    cases: list[GoldenEvalCase] = []
    for line in path.read_text(encoding="utf-8").strip().splitlines():
        stripped = line.strip()
        if stripped:
            cases.append(GoldenEvalCase.model_validate_json(stripped))

    scorecard = BenchmarkScorecard(total_cases=len(cases))

    actionable_recalls_1: list[float] = []
    actionable_recalls_3: list[float] = []
    actionable_recalls_5: list[float] = []
    actionable_rrs: list[float] = []
    actionable_hard_negs: list[bool] = []
    refusal_outcomes: list[bool] = []

    for case in cases:
        results = search_runbooks(case.incident_query, top_k=top_k)

        top_chunk = results[0].chunk_id if results else None
        top_score = results[0].rerank_score if results else None

        metric = CaseMetric(
            case_id=case.case_id,
            category=case.category,
            query=case.incident_query,
            should_refuse=case.should_refuse,
            top_chunk=top_chunk,
            top_rerank_score=top_score,
        )

        if case.should_refuse:
            scorecard.refusal_cases += 1
            # Expected empty results on out-of-domain or unanswerable queries
            refused = len(results) == 0
            metric.refusal_ok = refused
            refusal_outcomes.append(refused)
            # Refusal cases trivially pass hard-negative check if empty
            metric.hard_negative_ok = True
        else:
            scorecard.actionable_cases += 1

            # Check if any negative chunk appeared at Rank 1
            if top_chunk and top_chunk in case.negative_chunk_ids:
                metric.hard_negative_ok = False
                scorecard.hard_negatives_at_rank_1 += 1
            else:
                metric.hard_negative_ok = True
            actionable_hard_negs.append(metric.hard_negative_ok)

            # Determine rank of first matching expected chunk
            hit_rank = None
            for idx, res in enumerate(results, start=1):
                if res.chunk_id in case.expected_chunk_ids:
                    hit_rank = idx
                    break

            metric.hit_rank = hit_rank
            if hit_rank is not None:
                rr = 1.0 / hit_rank
                rec_1 = 1.0 if hit_rank <= 1 else 0.0
                rec_3 = 1.0 if hit_rank <= 3 else 0.0
                rec_5 = 1.0 if hit_rank <= 5 else 0.0
            else:
                rr = 0.0
                rec_1 = 0.0
                rec_3 = 0.0
                rec_5 = 0.0

            metric.reciprocal_rank = rr
            metric.recall_at_1 = rec_1
            metric.recall_at_3 = rec_3
            metric.recall_at_5 = rec_5

            actionable_rrs.append(rr)
            actionable_recalls_1.append(rec_1)
            actionable_recalls_3.append(rec_3)
            actionable_recalls_5.append(rec_5)

        scorecard.case_metrics.append(metric)

    if actionable_rrs:
        scorecard.mrr = sum(actionable_rrs) / len(actionable_rrs)
        scorecard.recall_at_1 = sum(actionable_recalls_1) / len(actionable_recalls_1)
        scorecard.recall_at_3 = sum(actionable_recalls_3) / len(actionable_recalls_3)
        scorecard.recall_at_5 = sum(actionable_recalls_5) / len(actionable_recalls_5)
        scorecard.hard_negative_pass_rate = sum(
            1.0 for ok in actionable_hard_negs if ok
        ) / len(actionable_hard_negs)

    if refusal_outcomes:
        scorecard.refusal_precision = sum(1.0 for ok in refusal_outcomes if ok) / len(
            refusal_outcomes
        )
    else:
        scorecard.refusal_precision = 1.0

    return scorecard


def print_executive_report(scorecard: BenchmarkScorecard) -> None:
    """Print an executive ASCII terminal report of the retrieval benchmark."""
    print("\n" + "=" * 90)
    print("           CALLOPS HYBRID RETRIEVAL BENCHMARK SCORECARD")
    print("=" * 90)
    print(
        f"{'Case ID':<26} {'Category':<22} {'Rank':<6} {'Score':<8} {'RR':<6} {'Rec@3':<6} {'HardNeg':<8} {'Status'}"
    )
    print("-" * 90)

    for m in scorecard.case_metrics:
        rank_str = (
            str(m.hit_rank)
            if m.hit_rank is not None
            else ("REFUSED" if m.should_refuse else "MISS")
        )
        score_str = (
            f"{m.top_rerank_score:.2f}" if m.top_rerank_score is not None else "N/A"
        )
        rr_str = f"{m.reciprocal_rank:.2f}" if not m.should_refuse else "—"
        rec3_str = (
            "1.0" if m.recall_at_3 == 1.0 else ("0.0" if not m.should_refuse else "—")
        )
        hard_str = "PASS" if m.hard_negative_ok else "FAIL"

        if m.should_refuse:
            status = "PASS" if m.refusal_ok else "FAIL"
        else:
            status = "PASS" if (m.recall_at_3 == 1.0 and m.hard_negative_ok) else "FAIL"

        print(
            f"{m.case_id:<26} {m.category:<22} {rank_str:<6} {score_str:<8} {rr_str:<6} {rec3_str:<6} {hard_str:<8} {status}"
        )

    print("=" * 90)
    print("                           AGGREGATE SUMMARY")
    print("=" * 90)
    print(
        f"Total Cases: {scorecard.total_cases} | Actionable: {scorecard.actionable_cases} | Refusals: {scorecard.refusal_cases}"
    )
    print("-" * 90)

    gates = [
        ("Recall @ 1", scorecard.recall_at_1, 0.70, scorecard.recall_at_1 >= 0.70),
        ("Recall @ 3", scorecard.recall_at_3, 0.85, scorecard.recall_at_3 >= 0.85),
        ("Recall @ 5", scorecard.recall_at_5, 0.90, scorecard.recall_at_5 >= 0.90),
        ("Mean Reciprocal Rank (MRR)", scorecard.mrr, 0.80, scorecard.mrr >= 0.80),
        (
            "Refusal Precision",
            scorecard.refusal_precision,
            1.00,
            scorecard.refusal_precision == 1.00,
        ),
        (
            "Hard Negatives at Rank 1",
            float(scorecard.hard_negatives_at_rank_1),
            0.0,
            scorecard.hard_negatives_at_rank_1 == 0,
        ),
    ]

    print(f"{'Metric':<35} {'Measured':<12} {'Target Gate':<15} {'Result'}")
    print("-" * 90)
    all_pass = True
    for label, val, target, passed in gates:
        val_str = f"{val:.4f}" if "Negatives" not in label else f"{int(val)}"
        target_str = (
            f">= {target:.2f}"
            if "Negatives" not in label and target > 0
            else (f"== {target:.2f}" if target == 1.0 else "== 0")
        )
        res_str = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"{label:<35} {val_str:<12} {target_str:<15} {res_str}")

    print("=" * 90)
    overall_verdict = (
        "BENCHMARK SUITE PASSED ALL GATES"
        if all_pass
        else "BENCHMARK SUITE FAILED ONE OR MORE GATES"
    )
    print(f"OVERALL VERDICT: {overall_verdict}")
    print("=" * 90 + "\n")


def main() -> None:
    scorecard = evaluate_retrieval()
    print_executive_report(scorecard)

    # Check exit condition against quality gates
    if (
        scorecard.recall_at_3 < 0.85
        or scorecard.mrr < 0.80
        or scorecard.refusal_precision < 1.00
        or scorecard.hard_negatives_at_rank_1 > 0
    ):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
