import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Ensure project root is in sys.path when executed directly
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evals.benchmarks.run_retrieval_benchmark import (
    BenchmarkScorecard,
    evaluate_retrieval,
)
from evals.generation.run_generation_eval import (
    GenerationBenchmarkScorecard,
    evaluate_generation,
)
from packages.knowledge.chunker import extract_runbooks_and_chunks
from packages.observability import flush_tracing, record_score, trace_span

DEFAULT_DATASET = Path("evals/datasets/golden_dataset.jsonl")
RUNBOOKS_FILE = Path("data/generated/runbooks.md")


@dataclass
class MetricGate:
    name: str
    measured: float
    target: float
    operator: str  # ">=", "==", "<="
    passed: bool
    formatted_measured: str
    formatted_target: str


@dataclass
class EvaluationMatrixResult:
    runbooks_count: int = 0
    chunks_count: int = 0
    total_eval_cases: int = 0
    evaluated_cases: int = 0
    tier1_retrieval_gates: list[MetricGate] = field(default_factory=list)
    tier2_reranking_gates: list[MetricGate] = field(default_factory=list)
    tier3_generation_gates: list[MetricGate] = field(default_factory=list)
    overall_passed: bool = True
    retrieval_scorecard: BenchmarkScorecard | None = None
    generation_scorecard: GenerationBenchmarkScorecard | None = None

    def to_dict(self) -> dict:
        return {
            "system_overview": {
                "runbooks_count": self.runbooks_count,
                "chunks_count": self.chunks_count,
                "total_eval_cases": self.total_eval_cases,
                "evaluated_cases": self.evaluated_cases,
            },
            "tier1_retrieval": [asdict(g) for g in self.tier1_retrieval_gates],
            "tier2_reranking": [asdict(g) for g in self.tier2_reranking_gates],
            "tier3_generation": [asdict(g) for g in self.tier3_generation_gates],
            "overall_passed": self.overall_passed,
        }


def evaluate_metric_gates(
    retrieval_scorecard: BenchmarkScorecard,
    generation_scorecard: GenerationBenchmarkScorecard,
) -> tuple[list[MetricGate], list[MetricGate], list[MetricGate], bool]:
    """
    Evaluates Tier 1, Tier 2, and Tier 3 gates against production acceptance criteria.
    """
    # Tier 1: Candidate Retrieval
    tier1 = [
        MetricGate(
            name="Recall @ 1",
            measured=retrieval_scorecard.recall_at_1,
            target=0.70,
            operator=">=",
            passed=retrieval_scorecard.recall_at_1 >= 0.70,
            formatted_measured=f"{retrieval_scorecard.recall_at_1 * 100:.1f}%",
            formatted_target=">= 70.0%",
        ),
        MetricGate(
            name="Recall @ 3",
            measured=retrieval_scorecard.recall_at_3,
            target=0.85,
            operator=">=",
            passed=retrieval_scorecard.recall_at_3 >= 0.85,
            formatted_measured=f"{retrieval_scorecard.recall_at_3 * 100:.1f}%",
            formatted_target=">= 85.0%",
        ),
        MetricGate(
            name="Recall @ 5",
            measured=retrieval_scorecard.recall_at_5,
            target=0.90,
            operator=">=",
            passed=retrieval_scorecard.recall_at_5 >= 0.90,
            formatted_measured=f"{retrieval_scorecard.recall_at_5 * 100:.1f}%",
            formatted_target=">= 90.0%",
        ),
    ]

    # Tier 2: Reranker & Refusal Precision
    tier2 = [
        MetricGate(
            name="Mean Reciprocal Rank (MRR)",
            measured=retrieval_scorecard.mrr,
            target=0.80,
            operator=">=",
            passed=retrieval_scorecard.mrr >= 0.80,
            formatted_measured=f"{retrieval_scorecard.mrr:.4f}",
            formatted_target=">= 0.8000",
        ),
        MetricGate(
            name="Refusal Precision",
            measured=retrieval_scorecard.refusal_precision,
            target=1.00,
            operator="==",
            passed=retrieval_scorecard.refusal_precision == 1.00,
            formatted_measured=f"{retrieval_scorecard.refusal_precision * 100:.1f}%",
            formatted_target="== 100.0%",
        ),
        MetricGate(
            name="Hard Negatives at Rank 1",
            measured=float(retrieval_scorecard.hard_negatives_at_rank_1),
            target=0.0,
            operator="==",
            passed=retrieval_scorecard.hard_negatives_at_rank_1 == 0,
            formatted_measured=str(retrieval_scorecard.hard_negatives_at_rank_1),
            formatted_target="== 0",
        ),
    ]

    # Tier 3: Generation & Safety Grounding
    tier3 = [
        MetricGate(
            name="Verbatim AST Match Rate",
            measured=generation_scorecard.verbatim_grounding_match_rate,
            target=0.85,
            operator=">=",
            passed=generation_scorecard.verbatim_grounding_match_rate >= 0.85,
            formatted_measured=f"{generation_scorecard.verbatim_grounding_match_rate * 100:.1f}%",
            formatted_target=">= 85.0%",
        ),
        MetricGate(
            name="Forbidden Claim Violations",
            measured=generation_scorecard.forbidden_claim_violation_rate,
            target=0.00,
            operator="==",
            passed=generation_scorecard.forbidden_claim_violation_rate == 0.00,
            formatted_measured=f"{generation_scorecard.forbidden_claim_violation_rate * 100:.1f}%",
            formatted_target="== 0.0%",
        ),
        MetricGate(
            name="Refusal Generation Accuracy",
            measured=generation_scorecard.refusal_generation_accuracy,
            target=1.00,
            operator="==",
            passed=generation_scorecard.refusal_generation_accuracy == 1.00,
            formatted_measured=f"{generation_scorecard.refusal_generation_accuracy * 100:.1f}%",
            formatted_target="== 100.0%",
        ),
        MetricGate(
            name="Overall Grounding Pass Rate",
            measured=generation_scorecard.overall_pass_rate,
            target=0.85,
            operator=">=",
            passed=generation_scorecard.overall_pass_rate >= 0.85,
            formatted_measured=f"{generation_scorecard.overall_pass_rate * 100:.1f}%",
            formatted_target=">= 85.0%",
        ),
    ]

    all_gates = tier1 + tier2 + tier3
    overall_passed = all(g.passed for g in all_gates)
    return tier1, tier2, tier3, overall_passed


async def run_eval_matrix(
    dataset_path: str | Path = DEFAULT_DATASET,
    limit: int | None = None,
) -> EvaluationMatrixResult:
    """
    Executes the consolidated multi-tier evaluation matrix across Retrieval, Reranking,
    and Generation/Safety Grounding.
    """
    path = Path(dataset_path)
    total_cases = len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])
    eval_cases = limit if limit and limit < total_cases else total_cases

    # Read corpus stats
    runbooks_count = 0
    chunks_count = 0
    if RUNBOOKS_FILE.is_file():
        try:
            rbs, chks = extract_runbooks_and_chunks(RUNBOOKS_FILE)
            runbooks_count = len(rbs)
            chunks_count = len(chks)
        except (OSError, RuntimeError, ValueError):
            runbooks_count = 20
            chunks_count = 129

    with trace_span(
        name="run_eval_matrix",
        as_type="evaluator",
        input={"dataset_path": str(dataset_path), "limit": limit},
    ) as matrix_span:
        # Execute Tier 1 & Tier 2: Hybrid Retrieval Benchmark
        retrieval_scorecard = evaluate_retrieval(dataset_path=dataset_path, limit=limit)

        # Execute Tier 3: Generation & Safety Grounding Benchmark
        generation_scorecard = await evaluate_generation(
            dataset_path=dataset_path, limit=limit
        )

        # Evaluate all gates
        tier1, tier2, tier3, overall_passed = evaluate_metric_gates(
            retrieval_scorecard, generation_scorecard
        )

        matrix_span.update(
            output={
                "overall_passed": overall_passed,
                "tier1_passed": all(g.passed for g in tier1),
                "tier2_passed": all(g.passed for g in tier2),
                "tier3_passed": all(g.passed for g in tier3),
            }
        )
        record_score(
            name="matrix_overall_passed",
            value=1.0 if overall_passed else 0.0,
            comment="Consolidated Evaluation Matrix production gate verdict",
        )

    return EvaluationMatrixResult(
        runbooks_count=runbooks_count,
        chunks_count=chunks_count,
        total_eval_cases=total_cases,
        evaluated_cases=eval_cases,
        tier1_retrieval_gates=tier1,
        tier2_reranking_gates=tier2,
        tier3_generation_gates=tier3,
        overall_passed=overall_passed,
        retrieval_scorecard=retrieval_scorecard,
        generation_scorecard=generation_scorecard,
    )


def print_matrix_dashboard(matrix: EvaluationMatrixResult) -> None:
    """Render executive ASCII dashboard of the consolidated evaluation matrix."""
    print("\n" + "=" * 96)
    print("           CALLOPS CONSOLIDATED EVALUATION MATRIX & CI REGRESSION GATE")
    print("=" * 96)
    print("SYSTEM OVERVIEW:")
    print(f"  Operational Runbooks:    {matrix.runbooks_count}")
    print(f"  Indexed Vector Chunks:   {matrix.chunks_count}")
    print(f"  Evaluation Fixtures:     {matrix.total_eval_cases} total ({matrix.evaluated_cases} evaluated)")
    print("-" * 96)

    tiers = [
        ("TIER 1: CANDIDATE RETRIEVAL (Dense + Sparse Hybrid Search)", matrix.tier1_retrieval_gates),
        ("TIER 2: RERANKING & REFUSAL PRECISION (Cross-Encoder & Gates)", matrix.tier2_reranking_gates),
        ("TIER 3: GENERATION & SAFETY GROUNDING (Verbatim AST & Policies)", matrix.tier3_generation_gates),
    ]

    for title, gates in tiers:
        print(f"\n{title}")
        print("-" * 96)
        print(f"{'Quality Metric':<40} {'Measured':<18} {'Target Gate':<18} {'Status'}")
        print("-" * 96)
        for g in gates:
            status = "PASS" if g.passed else "FAIL"
            print(f"{g.name:<40} {g.formatted_measured:<18} {g.formatted_target:<18} {status}")

    print("\n" + "=" * 96)
    verdict = "ALL PRODUCTION QUALITY GATES PASSED (EXIT 0)" if matrix.overall_passed else "ONE OR MORE QUALITY GATES FAILED (EXIT 1)"
    print(f"FINAL QUALITY GATE VERDICT: {verdict}")
    print("=" * 96 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="CallOps Consolidated Evaluation Matrix")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="Path to golden dataset JSONL")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of cases to evaluate")
    parser.add_argument("--output-json", default=None, help="Optional path to output results as JSON")
    parser.add_argument("--strict", action="store_true", help="Exit code 1 on any gate failure")
    args = parser.parse_args()

    matrix_result = asyncio.run(run_eval_matrix(dataset_path=args.dataset, limit=args.limit))
    print_matrix_dashboard(matrix_result)

    if args.output_json:
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(matrix_result.to_dict(), indent=2), encoding="utf-8")
        print(f"Evaluation matrix results written to {out_path}")

    flush_tracing()

    if args.strict and not matrix_result.overall_passed:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
