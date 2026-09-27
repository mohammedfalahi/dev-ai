from typing import Any

import pytest

from apps.voice.agent import VoiceAgentSession, get_default_ico
from packages.contracts.ico import IncidentContextObject
from packages.contracts.incident import CandidateRunbook, Hypothesis
from packages.policy.tier import ActionTier


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
            ),
            CandidateRunbook(
                chunk_id="RB-1#chunk-2",
                runbook_id="RB-1",
                title="Inspect active pods",
                service="checkout-api",
                score=0.85,
                content="kubectl get pods -l app=checkout-api"
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
async def test_livekit_agent_and_session_initialization(mock_ico):
    """Test 2: Verify LiveKit Agent and AgentSession instantiate with Gemini Live model and tools."""
    session = VoiceAgentSession(mock_ico, api_key="fake-test-key")
    agent = session.create_livekit_agent(model_name="gemini-live-2.5-flash-native-audio", voice="Puck")
    
    assert agent is not None
    assert len(agent.tools) == 1
    assert agent.tools[0].info.name == "execute_remediation_command"
    assert "checkout-api returning 500s" in agent.instructions

    livekit_session = session.create_livekit_session(agent=agent)
    assert livekit_session is not None


@pytest.mark.asyncio
async def test_grounded_qa(mock_ico):
    """Test 3: Feed question 'What is the root cause?' -> Assert response mentions hypothesis."""
    session = VoiceAgentSession(mock_ico)
    response = await session.handle_turn("What is the root cause?")
    
    response_lower = response.lower()
    assert "connection-pool exhaustion" in response_lower or "connection pool" in response_lower


@pytest.mark.asyncio
async def test_refusal_on_ungrounded_question(mock_ico):
    """Test 4: Feed question about unrelated system -> Assert agent refuses to guess."""
    session = VoiceAgentSession(mock_ico)
    response = await session.handle_turn("How do I restart the Redis cache?")
    
    assert "I don't have information on that." in response


def test_approval_keyword_handshake(mock_ico):
    """Test 5: Assert 'yeah sure' fails confirmation, while 'confirm' and 'GO' succeed."""
    session = VoiceAgentSession(mock_ico)
    command = "kubectl rollout restart deploy/checkout-api"
    
    is_approved, msg, dispatch = session.check_confirmation("yeah sure", command)
    assert not is_approved
    assert "denied" in msg.lower()
    assert dispatch is None
    assert not session.is_confirmed
    
    is_approved, msg, dispatch = session.check_confirmation("confirm", command)
    assert is_approved
    assert "confirmed" in msg.lower()
    assert dispatch is not None
    assert dispatch["status"] == "APPROVED"
    assert dispatch["command"] == command
    assert session.is_confirmed
    
    # Check alternate authorized word 'go'
    session.is_confirmed = False
    is_approved, msg, dispatch = session.check_confirmation("GO!", command)
    assert is_approved
    assert "confirmed" in msg.lower()
    assert session.is_confirmed


@pytest.mark.asyncio
async def test_tool_refuses_ungrounded_command(mock_ico):
    """Test 6: Tool execution strictly refuses commands not in candidate runbooks."""
    dispatched: list[dict[str, Any]] = []

    async def mock_dispatcher(payload: dict[str, Any]) -> bool:
        dispatched.append(payload)
        return True

    session = VoiceAgentSession(mock_ico, temporal_dispatcher=mock_dispatcher)
    ungrounded_cmd = "rm -rf /var/lib/postgresql/data"

    result = await session.execute_tool(ungrounded_cmd)

    assert "Refused" in result
    assert "UNSUPPORTED_COMMAND" in result
    assert len(dispatched) == 0
    assert len(session.dispatched_actions) == 0


@pytest.mark.asyncio
async def test_tool_blocks_mutating_tier_2_without_confirmation(mock_ico):
    """Test 7: Mutating Tier 2 command is blocked before spoken confirmation."""
    dispatched: list[dict[str, Any]] = []

    async def mock_dispatcher(payload: dict[str, Any]) -> bool:
        dispatched.append(payload)
        return True

    session = VoiceAgentSession(mock_ico, temporal_dispatcher=mock_dispatcher)
    mutating_cmd = "kubectl rollout restart deploy/checkout-api"

    result = await session.execute_tool(mutating_cmd)

    assert "CONFIRMATION_REQUIRED" in result
    assert "mutating Tier 2" in result
    assert len(dispatched) == 0
    assert len(session.dispatched_actions) == 0


@pytest.mark.asyncio
async def test_tool_executes_mutating_tier_2_after_confirmation(mock_ico):
    """Test 8: Mutating Tier 2 command executes and signals Temporal after exact confirmation."""
    dispatched: list[dict[str, Any]] = []

    async def mock_dispatcher(payload: dict[str, Any]) -> bool:
        dispatched.append(payload)
        return True

    session = VoiceAgentSession(mock_ico, temporal_dispatcher=mock_dispatcher)
    mutating_cmd = "kubectl rollout restart deploy/checkout-api"

    # 1. Spoken confirmation handshake
    session.check_confirmation("GO", mutating_cmd)
    assert session.is_confirmed

    # 2. Execute tool
    result = await session.execute_tool(mutating_cmd)

    assert "SUCCESS" in result
    assert "TIER_2_MUTATING" in result
    assert "dispatched to Temporal" in result
    assert len(dispatched) == 1
    assert dispatched[0]["command"] == mutating_cmd
    assert dispatched[0]["tier"] == ActionTier.TIER_2_MUTATING.value
    assert dispatched[0]["incident_id"] == "INC-001"
    assert dispatched[0]["source_chunk"] == "RB-1#chunk-1"


@pytest.mark.asyncio
async def test_tool_executes_read_only_tier_1_without_confirmation(mock_ico):
    """Test 9: Read-only Tier 1 command auto-runs without confirmation handshake."""
    dispatched: list[dict[str, Any]] = []

    async def mock_dispatcher(payload: dict[str, Any]) -> bool:
        dispatched.append(payload)
        return True

    session = VoiceAgentSession(mock_ico, temporal_dispatcher=mock_dispatcher)
    readonly_cmd = "kubectl get pods -l app=checkout-api"

    assert not session.is_confirmed

    result = await session.execute_tool(readonly_cmd)

    assert "SUCCESS" in result
    assert "TIER_1_READ_ONLY" in result
    assert len(dispatched) == 1
    assert dispatched[0]["command"] == readonly_cmd
    assert dispatched[0]["tier"] == ActionTier.TIER_1_READ_ONLY.value
    assert dispatched[0]["source_chunk"] == "RB-1#chunk-2"


def test_get_default_ico():
    """Test 10: Verify default ICO structure and voice brief formatting."""
    default_ico = get_default_ico()
    assert default_ico.incident_id == "INC-DEFAULT"
    assert default_ico.severity == "SEV1"
    brief = default_ico.to_voice_brief()
    assert "`" not in brief
    assert "We are tracking a SEV1 incident" in brief
