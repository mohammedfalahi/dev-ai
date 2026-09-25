import pytest
from pydantic import ValidationError

from packages.contracts.incident import Signal, Hypothesis, CandidateRunbook, SignalType
from packages.contracts.ico import IncidentContextObject


def test_ico_instantiation_and_serialization():
    """Test 1: Valid ICO instantiates and serializes cleanly to JSON."""
    signal = Signal(
        source_id="metric:error-rate:8820",
        type=SignalType.metric,
        text="Error rate increased from 0.2% to 94%",
        timestamp="2026-09-23T02:58:00Z",
    )

    hypothesis = Hypothesis(
        text="Connection-pool exhaustion introduced by v2.14.1",
        confidence=0.72,
        grounded_in=["log:8821", "deploy:v2.14.1"],
    )

    runbook = CandidateRunbook(
        chunk_id="DB-07#step-3",
        runbook_id="RB-PG-001",
        title="Postgres connection exhaustion",
        service="checkout-api",
        owner="database-platform",
        last_verified="2026-03-14",
        score=0.91,
    )

    ico = IncidentContextObject(
        incident_id="INC-000204",
        generated_at="2026-09-23T09:28:00Z",
        headline="Checkout API returning 500s since 02:58 UTC",
        impact="About 94% of checkout requests are failing",
        severity="SEV1",
        service="checkout-api",
        signals=[signal],
        hypothesis=hypothesis,
        candidate_runbooks=[runbook],
    )

    json_data = ico.model_dump_json()
    assert "INC-000204" in json_data
    assert "metric:error-rate:8820" in json_data

    # Check that defaults and aliases worked correctly
    data = ico.model_dump(by_alias=True)
    assert data["schema_version"] == "1.0"
    assert data["investigation_status"] == "complete"
    assert data["signals"][0]["observed_at"] == "2026-09-23T02:58:00Z"


def test_hypothesis_confidence_validation():
    """Test 2: Validation error is raised when confidence is out of bounds."""
    with pytest.raises(ValidationError) as exc_info:
        Hypothesis(
            text="Impossible hypothesis",
            confidence=1.5,  # Out of bounds (> 1.0)
            grounded_in=[],
        )
    assert "confidence" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        Hypothesis(
            text="Impossible hypothesis",
            confidence=-0.1,  # Out of bounds (< 0.0)
            grounded_in=[],
        )
    assert "confidence" in str(exc_info.value)


def test_ico_to_voice_brief():
    """Test 3: to_voice_brief() outputs plain spoken prose without backticks."""
    ico = IncidentContextObject(
        incident_id="INC-TEST",
        headline="`checkout-api` returning 500s",
        impact="~94% of requests failing",
        severity="SEV1",
        signals=[],
        hypothesis=Hypothesis(
            text="`redis` cache memory is exhausted.", confidence=0.8, grounded_in=[]
        ),
        candidate_runbooks=[],
    )

    brief = ico.to_voice_brief()

    # Should not contain any backticks
    assert "`" not in brief

    # Tildes should be expanded for speech
    assert "~" not in brief
    assert "About 94% of requests failing" in brief

    # Should end cleanly and read like prose
    expected = (
        "We are tracking a SEV1 incident: checkout-api returning 500s. "
        "About 94% of requests failing. "
        "The leading hypothesis is redis cache memory is exhausted."
    )
    assert brief == expected
