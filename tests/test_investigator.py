import pytest

from apps.investigator.engine import investigate_incident


@pytest.mark.asyncio
async def test_postgres_pool_incident():
    """Test 1: Check if known failure maps back to grounded ICO with correct runbooks."""
    raw_alert = {
        "incident_id": "INC-TEST-001",
        "severity": "SEV1",
        "service": "checkout-api",
        "error": "asyncpg.exceptions.TimeoutError or pool acquire timeout",
        "timestamp": "2026-09-23T02:58:00Z",
    }

    # We use a query that maps solidly to RB-PG-001 as demonstrated in hybrid_search tests
    ico = await investigate_incident(raw_alert)

    assert ico.severity == "SEV1"

    runbook_ids = [rb.runbook_id for rb in ico.candidate_runbooks]
    assert "RB-PG-001" in runbook_ids, (
        "Expected RB-PG-001 to be retrieved and referenced"
    )
    assert 0.0 <= ico.hypothesis.confidence <= 1.0


@pytest.mark.asyncio
async def test_refusal_undocumented_failure():
    """Test 2: Unknown out-of-domain failure should return zero runbooks and refuse gracefully."""
    raw_alert = {
        "incident_id": "INC-TEST-002",
        "severity": "SEV1",
        "service": "unknown-service",
        "error": "Quantum entanglement cosmic ray failure",
    }
    ico = await investigate_incident(raw_alert)

    assert len(ico.candidate_runbooks) == 0, (
        "Expected empty runbooks due to refusal gate"
    )

    # Verify the LLM recognized it as undocumented
    hyp_lower = ico.hypothesis.text.lower()
    is_undocumented = (
        "undocumented" in hyp_lower
        or "unverified" in hyp_lower
        or "no runbook" in hyp_lower
        or "unknown" in hyp_lower
    )
    assert is_undocumented, (
        f"Hypothesis did not flag undocumented failure: {ico.hypothesis.text}"
    )


@pytest.mark.asyncio
async def test_voice_brief_readiness():
    """Test 3: Verify the output from the engine converts cleanly to TTS speech."""
    raw_alert = {
        "incident_id": "INC-TEST-003",
        "severity": "SEV2",
        "service": "checkout-api",
        "error": "asyncpg.exceptions.TimeoutError or pool acquire timeout",
    }
    ico = await investigate_incident(raw_alert)

    brief = ico.to_voice_brief()
    assert len(brief) < 600, "Brief should be concise (under 600 characters)"
    assert "`" not in brief, "Brief should not contain backticks"
    assert "We are tracking a SEV2 incident" in brief
