from pathlib import Path

import pytest
from pydantic import ValidationError

from evals.schemas import GoldenEvalCase

DATASET_PATH = Path("evals/datasets/golden_dataset.jsonl")


def test_golden_dataset_file_exists():
    """Verify that the golden dataset file exists on disk."""
    assert DATASET_PATH.is_file(), f"Dataset file not found at {DATASET_PATH}"


def test_golden_dataset_parses_cleanly():
    """Verify that each line in golden_dataset.jsonl cleanly validates into GoldenEvalCase."""
    lines = DATASET_PATH.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 5, f"Expected at least 5 test cases, found {len(lines)}"

    cases: list[GoldenEvalCase] = []
    case_ids: set[str] = set()

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            case = GoldenEvalCase.model_validate_json(stripped)
            cases.append(case)
        except ValidationError as exc:
            pytest.fail(f"Line {idx} failed GoldenEvalCase validation: {exc}")

        assert case.case_id not in case_ids, f"Duplicate case_id found: {case.case_id}"
        case_ids.add(case.case_id)

    # Invariant: All cases with should_refuse=True must have empty expected_chunk_ids and expected_runbook_id=None
    refusal_cases = [c for c in cases if c.should_refuse]
    assert len(refusal_cases) > 0, "Expected at least one refusal evaluation case"
    for r_case in refusal_cases:
        assert r_case.expected_chunk_ids == [], (
            f"Refusal case {r_case.case_id} must have empty expected_chunk_ids"
        )
        assert r_case.expected_runbook_id is None, (
            f"Refusal case {r_case.case_id} must have expected_runbook_id=None"
        )

    # Invariant: Non-refusal cases should provide expected_runbook_id and expected_chunk_ids
    actionable_cases = [c for c in cases if not c.should_refuse]
    assert len(actionable_cases) >= 4, "Expected at least 4 actionable evaluation cases"
    for a_case in actionable_cases:
        assert a_case.expected_runbook_id is not None, (
            f"Actionable case {a_case.case_id} must provide expected_runbook_id"
        )
        assert len(a_case.expected_chunk_ids) > 0, (
            f"Actionable case {a_case.case_id} must provide expected_chunk_ids"
        )


def test_refusal_validator_enforces_safety_invariants():
    """Ensure GoldenEvalCase model validator rejects invalid refusal configurations."""
    # Invalid: should_refuse=True with expected_chunk_ids populated
    with pytest.raises(ValidationError, match="must have empty expected_chunk_ids"):
        GoldenEvalCase(
            case_id="EVAL-INVALID-001",
            category="unanswerable_refusal",
            incident_query="Out of domain",
            should_refuse=True,
            expected_chunk_ids=["RB-PG-001::purpose::0"],
        )

    # Invalid: should_refuse=True with expected_runbook_id populated
    with pytest.raises(ValidationError, match="must have expected_runbook_id=None"):
        GoldenEvalCase(
            case_id="EVAL-INVALID-002",
            category="unanswerable_refusal",
            incident_query="Out of domain",
            should_refuse=True,
            expected_runbook_id="RB-PG-001",
        )
