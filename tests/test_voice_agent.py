import pytest

from apps.voice.agent import VoiceAgentSession
from packages.contracts.ico import IncidentContextObject
from packages.contracts.incident import CandidateRunbook, Hypothesis


@pytest.fixture
def mock_ico() -> IncidentContextObject:
    return IncidentContextObject(
        incident_id="INC-001",
        headline="checkout-api returning 500s",
        impact="About 94 percent of requests failing",
        severity="SEV1",
        signals=[],
        hypothesis=Hypothesis(
            text="Connection-pool exhaustion",
            confidence=0.9,
            grounded_in=[]
        ),
        candidate_runbooks=[
            CandidateRunbook(
                chunk_id="RB-1#chunk-1",
                runbook_id="RB-1",
                title="Postgres connection exhaustion",
                service="checkout-api",
                score=0.9,
                content="kubectl rollout restart deploy/checkout-api"
            )
        ]
    )


@pytest.mark.asyncio
async def test_initial_greeting(mock_ico):
    """Test 1: Assert greeting starts with to_voice_brief() and contains no backticks."""
    session = VoiceAgentSession(mock_ico)
    greeting = await session.get_initial_greeting()
    
    assert "`" not in greeting
    assert "We are tracking a SEV1 incident" in greeting
    assert "checkout-api returning 500s" in greeting
    assert "Connection-pool exhaustion" in greeting


@pytest.mark.asyncio
async def test_grounded_qa(mock_ico):
    """Test 2: Feed question 'What is the root cause?' -> Assert response mentions hypothesis."""
    session = VoiceAgentSession(mock_ico)
    response = await session.handle_turn("What is the root cause?")
    
    response_lower = response.lower()
    assert "connection-pool exhaustion" in response_lower or "connection pool" in response_lower


@pytest.mark.asyncio
async def test_refusal_on_ungrounded_question(mock_ico):
    """Test 3: Feed question about unrelated system -> Assert agent refuses to guess."""
    session = VoiceAgentSession(mock_ico)
    response = await session.handle_turn("How do I restart the Redis cache?")
    
    assert "I don't have information on that." in response


def test_approval_keyword_handshake(mock_ico):
    """Test 4: Assert 'yeah sure' fails confirmation, while 'confirm' succeeds."""
    session = VoiceAgentSession(mock_ico)
    command = "kubectl rollout restart deploy/checkout-api"
    
    is_approved, msg = session.check_confirmation("yeah sure", command)
    assert not is_approved
    assert "denied" in msg.lower()
    
    is_approved, msg = session.check_confirmation("confirm", command)
    assert is_approved
    assert "confirmed" in msg.lower()
    
    # Check alternate authorized word 'go'
    is_approved, msg = session.check_confirmation("GO!", command)
    assert is_approved
    assert "confirmed" in msg.lower()
