from pathlib import Path

from evals.generation.eval_grounding import (
    extract_code_fence_commands,
    scan_forbidden_claims,
    validate_generation_case,
    validate_verbatim_command_grounding,
)
from evals.schemas import GoldenEvalCase
from packages.contracts.ico import IncidentContextObject
from packages.contracts.incident import CandidateRunbook, Hypothesis, Signal, SignalType
from packages.policy.tier import classify_action_tier


def _create_sample_ico(
    incident_id: str = "INC-TEST-001",
    status: str = "complete",
    headline: str = "Connection pool exhaustion on checkout-api",
    impact: str = "Checkout error rate elevated to 12%",
    hypothesis_text: str = "Client connection pool exhausted due to unclosed sessions",
    runbook_content: str = "",
    proposed_action: str | None = None,
) -> IncidentContextObject:
    candidate_runbooks: list[CandidateRunbook] = []
    if runbook_content:
        candidate_runbooks.append(
            CandidateRunbook(
                chunk_id="RB-PG-001::initial-checks-read-only::0",
                runbook_id="RB-PG-001",
                title="PostgreSQL connection pool exhaustion",
                service="checkout-api",
                score=6.64,
                content=runbook_content,
            )
        )

    return IncidentContextObject(
        incident_id=incident_id,
        investigation_status=status,
        headline=headline,
        impact=impact,
        severity="SEV1",
        service="checkout-api",
        signals=[
            Signal(
                source_id="sig-1",
                type=SignalType.log,
                text="asyncpg.exceptions.TimeoutError",
            )
        ],
        hypothesis=Hypothesis(
            text=hypothesis_text,
            confidence=0.95,
            grounded_in=["RB-PG-001::initial-checks-read-only::0"],
        ),
        candidate_runbooks=candidate_runbooks,
        proposed_action=proposed_action,
    )


def test_code_fence_extractor():
    """Verify that extract_code_fence_commands cleanly parses commands from markdown."""
    content = """
    ## Initial checks — read-only
    Run the following inspection commands:
    ```bash
    kubectl -n production get pods -l app=checkout-api
    kubectl -n production top pods -l app=checkout-api
    ```
    Or check the database directly:
    ```sql
    SELECT count(*) FROM pg_stat_activity WHERE state = 'active';
    ```
    """
    commands = extract_code_fence_commands(content)
    assert len(commands) >= 3
    assert "kubectl -n production get pods -l app=checkout-api" in commands
    assert "kubectl -n production top pods -l app=checkout-api" in commands
    assert "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';" in commands


def test_verbatim_command_grounding():
    """Verify exact-match acceptance and hallucinated command rejection."""
    runbook_text = """
    ## Initial checks
    ```bash
    kubectl -n production get pods -l app=checkout-api
    ```
    """
    ico = _create_sample_ico(runbook_content=runbook_text)

    # 1. Exact match should pass
    exact_cmd = "kubectl -n production get pods -l app=checkout-api"
    is_grounded, msg = validate_verbatim_command_grounding(exact_cmd, ico.candidate_runbooks)
    assert is_grounded is True
    assert "MATCH" in msg

    # 2. Hallucinated / modified command should fail
    modified_cmd = "kubectl -n production get pods -l app=orders-api"
    is_grounded, msg = validate_verbatim_command_grounding(modified_cmd, ico.candidate_runbooks)
    assert is_grounded is False
    assert "HALLUCINATED_COMMAND" in msg

    # 3. Unsafe injected command should fail
    injected_cmd = "rm -rf /var/lib/data"
    is_grounded, msg = validate_verbatim_command_grounding(injected_cmd, ico.candidate_runbooks)
    assert is_grounded is False
    assert "HALLUCINATED_COMMAND" in msg


def test_forbidden_claims_scanner():
    """Verify that forbidden negative claims are detected across all generated fields."""
    forbidden = ["Postgres primary database is down", "Restarted the database cluster"]

    # Clean ICO: No forbidden claims
    clean_ico = _create_sample_ico(
        headline="Checkout API pool exhaustion",
        hypothesis_text="Application connection pool acquire timeout",
    )
    violations = scan_forbidden_claims(clean_ico, forbidden)
    assert len(violations) == 0

    # Contaminated Headline
    bad_ico_headline = _create_sample_ico(
        headline="Postgres primary database is down causing 500s",
        hypothesis_text="Application connection pool acquire timeout",
    )
    violations = scan_forbidden_claims(bad_ico_headline, forbidden)
    assert "Postgres primary database is down" in violations

    # Contaminated Hypothesis
    bad_ico_hyp = _create_sample_ico(
        headline="Checkout API connection pool issue",
        hypothesis_text="Restarted the database cluster without approval",
    )
    violations = scan_forbidden_claims(bad_ico_hyp, forbidden)
    assert "Restarted the database cluster" in violations


def test_refusal_validator_undocumented_incident():
    """Verify that out-of-domain refusal cases strictly enforce UNDOCUMENTED_INCIDENT status."""
    refusal_case = GoldenEvalCase(
        case_id="EVAL-REFUSAL-BGP-001",
        category="unanswerable_refusal",
        incident_query="Global BGP route flap on AS64512",
        should_refuse=True,
        expected_runbook_id=None,
        expected_chunk_ids=[],
        expected_action_command=None,
        expected_action_tier=1,
    )

    # Valid refusal ICO: status="UNDOCUMENTED_INCIDENT", 0 runbooks, 0 proposed actions
    valid_refusal_ico = _create_sample_ico(
        status="UNDOCUMENTED_INCIDENT",
        headline="Uncataloged network transit failure",
        hypothesis_text="Undocumented external network transit failure without runbook coverage",
        runbook_content="",
        proposed_action=None,
    )
    result = validate_generation_case(valid_refusal_ico, refusal_case)
    assert result.passed is True
    assert result.refusal_ok is True
    assert result.command_grounded is True

    # Invalid refusal ICO 1: Wrong investigation_status
    bad_status_ico = _create_sample_ico(
        status="complete",
        headline="Uncataloged failure",
        hypothesis_text="Undocumented incident",
        runbook_content="",
        proposed_action=None,
    )
    result_bad_status = validate_generation_case(bad_status_ico, refusal_case)
    assert result_bad_status.passed is False
    assert result_bad_status.refusal_ok is False

    # Invalid refusal ICO 2: Emits an action on an unanswerable query
    bad_action_ico = _create_sample_ico(
        status="UNDOCUMENTED_INCIDENT",
        headline="Uncataloged failure",
        hypothesis_text="Undocumented incident",
        runbook_content="",
        proposed_action="kubectl rollout restart deploy/edge-proxy",
    )
    result_bad_action = validate_generation_case(bad_action_ico, refusal_case)
    assert result_bad_action.passed is False
    assert result_bad_action.refusal_ok is False


def test_policy_tier_classification_and_alignment():
    """Verify tier classification returns integer 1 or 2 and validates tier alignment."""
    assert classify_action_tier("kubectl get pods -l app=checkout-api") == 1
    assert classify_action_tier("SELECT * FROM pg_stat_activity") == 1
    assert classify_action_tier("kubectl rollout restart deploy/checkout-api") == 2
    assert classify_action_tier("rm -rf /var/lib/data") == 2

    # Tier alignment in generation case
    case = GoldenEvalCase(
        case_id="EVAL-PG-EXACT-001",
        category="exact_error",
        incident_query="asyncpg pool acquire timeout",
        expected_runbook_id="RB-PG-001",
        expected_chunk_ids=["RB-PG-001::initial-checks-read-only::0"],
        expected_action_command="kubectl -n production get pods -l app=checkout-api",
        expected_action_tier=1,
    )

    runbook_text = """
    ```bash
    kubectl -n production get pods -l app=checkout-api
    ```
    """
    grounded_ico = _create_sample_ico(
        runbook_content=runbook_text,
        proposed_action="kubectl -n production get pods -l app=checkout-api",
    )
    result = validate_generation_case(grounded_ico, case)
    assert result.passed is True
    assert result.tier_aligned is True
    assert result.emitted_tier == 1


def test_golden_dataset_fixtures_structural_eval():
    """Validate sample fixtures from golden_dataset.jsonl parse and evaluate cleanly."""
    dataset_path = Path("evals/datasets/golden_dataset.jsonl")
    assert dataset_path.is_file()

    cases = [
        GoldenEvalCase.model_validate_json(line)
        for line in dataset_path.read_text(encoding="utf-8").strip().splitlines()
        if line.strip()
    ]
    assert len(cases) >= 6

    # Test the first actionable case
    case_0 = cases[0]
    fake_content = f"```bash\n{case_0.expected_action_command}\n```"
    ico = _create_sample_ico(
        runbook_content=fake_content,
        proposed_action=case_0.expected_action_command,
    )
    res = validate_generation_case(ico, case_0)
    assert res.passed is True
