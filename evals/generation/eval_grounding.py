import re
from dataclasses import dataclass, field

from evals.schemas import GoldenEvalCase
from packages.contracts.ico import IncidentContextObject
from packages.contracts.incident import CandidateRunbook
from packages.policy.tier import ActionTier, classify_action_tier, classify_command


def extract_code_fence_commands(content: str) -> list[str]:
    """
    Deterministically extract commands inside markdown code fences (```bash ... ```, ```sql ... ```, etc.).
    Preserves exact commands while also parsing line-by-line executable statements.
    """
    commands: list[str] = []
    # Match fenced code blocks
    fence_pattern = re.compile(r"```(?:[a-zA-Z0-9_-]+)?\s*\n([\s\S]*?)\n?```", re.MULTILINE)
    for match in fence_pattern.finditer(content):
        block = match.group(1).strip()
        if block:
            commands.append(block)
            # Also extract individual lines within block (excluding comments/blank lines)
            for line in block.splitlines():
                line_str = line.strip()
                if line_str and not line_str.startswith("#") and not line_str.startswith("--"):
                    commands.append(line_str)

    return commands


def validate_verbatim_command_grounding(
    proposed_command: str | None,
    candidate_runbooks: list[CandidateRunbook],
) -> tuple[bool, str]:
    """
    Validates that a proposed CLI/SQL command exists verbatim within the AST code fences
    or chunk content of the retrieved candidate runbooks.
    """
    if not proposed_command or not proposed_command.strip():
        return True, "No action command proposed"

    cleaned_cmd = proposed_command.strip()

    for rb in candidate_runbooks:
        # Check 1: Direct substring presence in chunk content
        if cleaned_cmd in rb.content:
            return True, f"VERBATIM_MATCH in chunk {rb.chunk_id}"

        # Check 2: Match against extracted code fence blocks or command lines
        code_commands = extract_code_fence_commands(rb.content)
        for code_cmd in code_commands:
            if cleaned_cmd == code_cmd or cleaned_cmd in code_cmd:
                return True, f"CODE_FENCE_MATCH in chunk {rb.chunk_id}"

    return False, f"HALLUCINATED_COMMAND: '{cleaned_cmd}' not found in retrieved runbook code fences"


def scan_forbidden_claims(
    ico: IncidentContextObject,
    forbidden_claims: list[str],
) -> list[str]:
    """
    Scans the ICO headline, impact, hypothesis text, and spoken voice brief
    against forbidden claim strings. Returns any violating substrings.
    """
    violations: list[str] = []
    if not forbidden_claims:
        return violations

    voice_brief = ico.to_voice_brief()
    text_corpus = f"{ico.headline} \n {ico.impact} \n {ico.hypothesis.text} \n {voice_brief}".lower()

    for claim in forbidden_claims:
        claim_cleaned = claim.strip().lower()
        if claim_cleaned and claim_cleaned in text_corpus:
            violations.append(claim)

    return violations


@dataclass
class GenerationCaseResult:
    case_id: str
    category: str
    command_grounded: bool
    command_grounding_reason: str
    forbidden_claims_violated: list[str] = field(default_factory=list)
    tier_aligned: bool = True
    refusal_ok: bool = True
    passed: bool = True
    emitted_action: str | None = None
    expected_action: str | None = None
    expected_tier: int = 1
    emitted_tier: int = 1


def validate_generation_case(
    ico: IncidentContextObject,
    case: GoldenEvalCase,
) -> GenerationCaseResult:
    """
    Validates an emitted IncidentContextObject against a GoldenEvalCase contract:
    - Verbatim action command grounding in runbook AST fences.
    - Negative claim scanner (forbidden_claims).
    - Policy action tier alignment.
    - Refusal gate verification (UNDOCUMENTED_INCIDENT status, 0 runbooks, 0 mutating commands).
    """
    emitted_action = ico.proposed_action
    expected_action = case.expected_action_command
    violations = scan_forbidden_claims(ico, case.forbidden_claims)

    emitted_tier = classify_action_tier(emitted_action) if emitted_action else 1

    if case.should_refuse:
        # Refusal expectations:
        # 1. investigation_status must be "UNDOCUMENTED_INCIDENT"
        # 2. candidate_runbooks must be empty
        # 3. no mutating action proposed
        is_undocumented_status = (ico.investigation_status == "UNDOCUMENTED_INCIDENT")
        no_runbooks = (len(ico.candidate_runbooks) == 0)
        no_mutating = (
            emitted_action is None or classify_command(emitted_action) != ActionTier.TIER_2_MUTATING
        )

        refusal_ok = is_undocumented_status and no_runbooks and no_mutating
        command_grounded = (emitted_action is None)
        grounding_reason = "REFUSAL: No command emitted as required" if command_grounded else "REFUSAL_VIOLATION: Command emitted on unanswerable query"
        tier_aligned = True
    else:
        # Non-refusal expectations:
        refusal_ok = (ico.investigation_status != "UNDOCUMENTED_INCIDENT")
        command_grounded, grounding_reason = validate_verbatim_command_grounding(
            emitted_action, ico.candidate_runbooks
        )
        tier_aligned = (emitted_tier == case.expected_action_tier) if emitted_action else True

    passed = (
        command_grounded
        and len(violations) == 0
        and tier_aligned
        and refusal_ok
    )

    return GenerationCaseResult(
        case_id=case.case_id,
        category=case.category,
        command_grounded=command_grounded,
        command_grounding_reason=grounding_reason,
        forbidden_claims_violated=violations,
        tier_aligned=tier_aligned,
        refusal_ok=refusal_ok,
        passed=passed,
        emitted_action=emitted_action,
        expected_action=expected_action,
        expected_tier=case.expected_action_tier,
        emitted_tier=emitted_tier,
    )
