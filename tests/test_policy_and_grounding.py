from packages.contracts.ico import IncidentContextObject
from packages.contracts.incident import CandidateRunbook, Hypothesis
from packages.policy.grounding_validator import GroundingValidator
from packages.policy.tier import ActionTier, classify_command


def test_command_tier_classification():
    """Test 1: Check deterministic classification of Tier 1 vs Tier 2."""
    assert classify_command("kubectl get pods") == ActionTier.TIER_1_READ_ONLY
    assert classify_command("SELECT * FROM pg_stat_activity") == ActionTier.TIER_1_READ_ONLY
    assert classify_command("kubectl rollout restart deploy/checkout-api") == ActionTier.TIER_2_MUTATING
    assert classify_command("rm -rf /var/lib/data") == ActionTier.TIER_2_MUTATING
    assert classify_command("DROP TABLE users") == ActionTier.TIER_2_MUTATING


def test_grounding_rejection():
    """Test 2: Ensure ungrounded/unsupported commands are rejected."""
    ico = IncidentContextObject(
        incident_id="INC-001",
        headline="Test incident",
        impact="None",
        severity="SEV3",
        signals=[],
        hypothesis=Hypothesis(text="Test hypothesis", confidence=0.9, grounded_in=[]),
        candidate_runbooks=[
            CandidateRunbook(
                chunk_id="RB-1#chunk-1",
                runbook_id="RB-1",
                title="Restart service",
                service="svc",
                score=0.9,
                content="kubectl rollout restart deploy/svc"
            )
        ]
    )
    
    candidate_command = "rm -rf /var/lib/data"
    is_valid, msg = GroundingValidator.validate_action(candidate_command, ico)
    
    assert not is_valid
    assert "UNSUPPORTED_COMMAND" in msg


def test_grounding_acceptance():
    """Test 3: Ensure grounded, verbatim commands are accepted."""
    ico = IncidentContextObject(
        incident_id="INC-001",
        headline="Test incident",
        impact="None",
        severity="SEV3",
        signals=[],
        hypothesis=Hypothesis(text="Test hypothesis", confidence=0.9, grounded_in=[]),
        candidate_runbooks=[
            CandidateRunbook(
                chunk_id="RB-1#chunk-1",
                runbook_id="RB-1",
                title="Restart service",
                service="svc",
                score=0.9,
                content="""
                To fix this, execute:
                kubectl rollout restart deploy/svc
                """
            )
        ]
    )
    
    # Exact matched Tier 2 command
    candidate_command = "kubectl rollout restart deploy/svc"
    is_valid, msg = GroundingValidator.validate_action(candidate_command, ico)
    
    assert is_valid
    assert "VALID" in msg
    assert "TIER_2_MUTATING" in msg
    
    # Exact matched Tier 1 command (not mutated keywords)
    read_only_command = "To fix this, execute:"
    is_valid, msg = GroundingValidator.validate_action(read_only_command, ico)
    assert is_valid
    assert "TIER_1_READ_ONLY" in msg


def test_voice_brief_safety():
    """Test 4: Validate spoken brief rejects dangerous formatting."""
    ico = IncidentContextObject(
        incident_id="INC-001",
        headline="Test", impact="Test", severity="SEV1",
        signals=[], hypothesis=Hypothesis(text="Test", confidence=1.0, grounded_in=[]),
        candidate_runbooks=[]
    )
    
    # Valid prose
    assert GroundingValidator.validate_voice_brief("We are tracking a database failure.", ico)
    
    # Invalid markdown code block
    assert not GroundingValidator.validate_voice_brief("Run `kubectl get pods`.", ico)
    
    # Invalid JSON
    assert not GroundingValidator.validate_voice_brief("Payload: {'error': 'timeout'}", ico)
