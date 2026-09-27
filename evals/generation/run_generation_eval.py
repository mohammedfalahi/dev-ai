import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Ensure project root is in sys.path when executed directly
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.investigator.engine import investigate_incident
from evals.generation.eval_grounding import (
    GenerationCaseResult,
    validate_generation_case,
)
from evals.schemas import GoldenEvalCase
from packages.observability import flush_tracing, record_score, trace_span

DEFAULT_DATASET = Path("evals/datasets/golden_dataset.jsonl")


@dataclass
class GenerationBenchmarkScorecard:
    total_cases: int = 0
    actionable_cases: int = 0
    refusal_cases: int = 0
    verbatim_grounding_match_rate: float = 0.0
    forbidden_claim_violation_rate: float = 0.0
    refusal_generation_accuracy: float = 0.0
    overall_pass_rate: float = 0.0
    results: list[GenerationCaseResult] = field(default_factory=list)


async def evaluate_generation(
    dataset_path: str | Path = DEFAULT_DATASET,
    limit: int | None = None,
) -> GenerationBenchmarkScorecard:
    """
    Executes live generation evaluation by running investigate_incident across GoldenEvalCase fixtures.
    """
    path = Path(dataset_path)
    if not path.is_file():
        raise FileNotFoundError(f"Evaluation dataset not found at {path}")

    cases: list[GoldenEvalCase] = []
    for line in path.read_text(encoding="utf-8").strip().splitlines():
        stripped = line.strip()
        if stripped:
            cases.append(GoldenEvalCase.model_validate_json(stripped))

    if limit is not None and limit > 0:
        cases = cases[:limit]

    with trace_span(
        name="benchmark:generation_evaluation",
        as_type="evaluator",
        input={"total_cases": len(cases), "dataset_path": str(dataset_path)},
    ) as eval_span:
        scorecard = GenerationBenchmarkScorecard(total_cases=len(cases))

        actionable_grounded: list[bool] = []
        forbidden_violations: list[bool] = []
        refusal_successes: list[bool] = []
        overall_passes: list[bool] = []

        for case in cases:
            raw_alert = {
                "incident_id": f"INC-{case.case_id}",
                "severity": "SEV1",
                "service": case.service or "infrastructure",
                "error": case.incident_query,
                "timestamp": "2026-09-26T12:00:00Z",
            }

            try:
                ico = await investigate_incident(raw_alert)
                case_result = validate_generation_case(ico, case)
            except (ValueError, RuntimeError, TimeoutError, OSError) as exc:
                case_result = GenerationCaseResult(
                    case_id=case.case_id,
                    category=case.category,
                    command_grounded=False,
                    command_grounding_reason=f"ERROR: {exc}",
                    passed=False,
                    refusal_ok=False,
                    expected_action=case.expected_action_command,
                    emitted_action=None,
                )

            scorecard.results.append(case_result)
            overall_passes.append(case_result.passed)
            has_violations = len(case_result.forbidden_claims_violated) > 0
            forbidden_violations.append(has_violations)

            if case.should_refuse:
                scorecard.refusal_cases += 1
                refusal_successes.append(case_result.refusal_ok)
            else:
                scorecard.actionable_cases += 1
                actionable_grounded.append(case_result.command_grounded)

        if actionable_grounded:
            scorecard.verbatim_grounding_match_rate = sum(
                1.0 for g in actionable_grounded if g
            ) / len(actionable_grounded)

        if forbidden_violations:
            scorecard.forbidden_claim_violation_rate = sum(
                1.0 for v in forbidden_violations if v
            ) / len(forbidden_violations)

        if refusal_successes:
            scorecard.refusal_generation_accuracy = sum(
                1.0 for r in refusal_successes if r
            ) / len(refusal_successes)
        else:
            scorecard.refusal_generation_accuracy = 1.0

        if overall_passes:
            scorecard.overall_pass_rate = sum(
                1.0 for p in overall_passes if p
            ) / len(overall_passes)

        eval_span.update(
            output={
                "verbatim_grounding_match_rate": scorecard.verbatim_grounding_match_rate,
                "forbidden_claim_violation_rate": scorecard.forbidden_claim_violation_rate,
                "refusal_generation_accuracy": scorecard.refusal_generation_accuracy,
                "overall_pass_rate": scorecard.overall_pass_rate,
            }
        )
        record_score(
            name="generation_verbatim_grounding_match_rate",
            value=scorecard.verbatim_grounding_match_rate,
        )
        record_score(
            name="generation_forbidden_claim_violation_rate",
            value=scorecard.forbidden_claim_violation_rate,
        )
        record_score(
            name="generation_refusal_generation_accuracy",
            value=scorecard.refusal_generation_accuracy,
        )
        record_score(
            name="generation_overall_pass_rate",
            value=scorecard.overall_pass_rate,
        )

    return scorecard


def print_executive_report(scorecard: GenerationBenchmarkScorecard) -> None:
    """Print an executive ASCII terminal report of the generation grounding benchmark."""
    print("\n" + "=" * 110)
    print("           CALLOPS GENERATION, SAFETY GROUNDING & ACTION VERIFICATION SCORECARD")
    print("=" * 110)
    print(
        f"{'Case ID':<26} {'Category':<22} {'Expected Action':<25} {'Emitted Action':<25} {'Grounding':<10} {'Verdict'}"
    )
    print("-" * 110)

    for r in scorecard.results:
        exp_act = (r.expected_action[:22] + "...") if r.expected_action and len(r.expected_action) > 25 else (r.expected_action or "None (Refusal)")
        emit_act = (r.emitted_action[:22] + "...") if r.emitted_action and len(r.emitted_action) > 25 else (r.emitted_action or "None")
        ground_status = "GROUNDED" if r.command_grounded else "UNGROUNDED"
        verdict = "PASS" if r.passed else "FAIL"

        print(
            f"{r.case_id:<26} {r.category:<22} {exp_act:<25} {emit_act:<25} {ground_status:<10} {verdict}"
        )

    print("=" * 110)
    print("                                   AGGREGATE SUMMARY")
    print("=" * 110)
    print(f"Total Cases: {scorecard.total_cases} | Actionable: {scorecard.actionable_cases} | Refusal: {scorecard.refusal_cases}")
    print("-" * 110)

    gates = [
        (
            "Verbatim Action Grounding Match Rate",
            scorecard.verbatim_grounding_match_rate * 100,
            85.0,
            scorecard.verbatim_grounding_match_rate >= 0.85,
        ),
        (
            "Forbidden Claim Violation Rate",
            scorecard.forbidden_claim_violation_rate * 100,
            0.0,
            scorecard.forbidden_claim_violation_rate == 0.0,
        ),
        (
            "Refusal Generation Accuracy",
            scorecard.refusal_generation_accuracy * 100,
            100.0,
            scorecard.refusal_generation_accuracy == 1.0,
        ),
        (
            "Overall Grounding Pass Rate",
            scorecard.overall_pass_rate * 100,
            85.0,
            scorecard.overall_pass_rate >= 0.85,
        ),
    ]

    print(f"{'Metric':<42} {'Measured':<15} {'Target Gate':<15} {'Result'}")
    print("-" * 110)
    all_pass = True
    for label, val, target, passed in gates:
        val_str = f"{val:.1f}%"
        target_str = f">= {target:.1f}%" if target > 0 else "== 0.0%"
        res_str = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"{label:<42} {val_str:<15} {target_str:<15} {res_str}")

    print("=" * 110)
    overall_verdict = "GENERATION SUITE PASSED ALL GATES" if all_pass else "GENERATION SUITE FAILED ONE OR MORE GATES"
    print(f"OVERALL VERDICT: {overall_verdict}")
    print("=" * 110 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="CallOps Generation & Grounding Evaluation Benchmark")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="Path to golden dataset JSONL file")
    parser.add_argument("--limit", type=int, default=None, help="Optional limit on number of cases to evaluate")
    args = parser.parse_args()

    scorecard = asyncio.run(evaluate_generation(dataset_path=args.dataset, limit=args.limit))
    print_executive_report(scorecard)
    flush_tracing()

    if (
        scorecard.verbatim_grounding_match_rate < 0.85
        or scorecard.forbidden_claim_violation_rate > 0.0
        or scorecard.refusal_generation_accuracy < 1.0
        or scorecard.overall_pass_rate < 0.85
    ):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
