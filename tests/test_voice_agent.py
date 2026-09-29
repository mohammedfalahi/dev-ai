import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from apps.voice.agent import (
    VoiceAgentSession,
    extract_ico_from_metadata,
    get_default_ico,
    get_realtime_model,
)
from packages.contracts.ico import IncidentContextObject
from packages.contracts.incident import CandidateRunbook, Hypothesis
from packages.core.config import settings
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
    """Test 1: Assert greeting starts with to_voice_brief(), is empathetic, and contains no backticks."""
    session = VoiceAgentSession(mock_ico)
    greeting = await session.get_initial_greeting()
    
    assert "`" not in greeting
    assert "Hello, sorry to wake you up" in greeting
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
    """Test 5: Assert conversational assent ('yeah sure', 'go ahead', 'yes please', 'confirm', 'GO') succeeds while negative or ambiguous phrases fail."""
    session = VoiceAgentSession(mock_ico)
    command = "kubectl rollout restart deploy/checkout-api"
    
    # Negative / ambiguous phrases fail
    for negative in ["no don't", "wait", "tell me more", "maybe later", "cancel"]:
        session.is_confirmed = False
        is_approved, msg, dispatch = session.check_confirmation(negative, command)
        assert not is_approved
        assert "denied" in msg.lower()
        assert dispatch is None
        assert not session.is_confirmed
    
    # Conversational assent phrases succeed
    for assent in ["yeah sure", "go ahead", "yes please", "do that", "confirm", "GO!", "proceed"]:
        session.is_confirmed = False
        is_approved, msg, dispatch = session.check_confirmation(assent, command)
        assert is_approved
        assert "confirmed" in msg.lower()
        assert dispatch is not None
        assert dispatch["status"] == "APPROVED"
        assert dispatch["command"] == command
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
    """Test 10: Verify default ICO structure and empathetic voice brief formatting."""
    default_ico = get_default_ico()
    assert default_ico.incident_id == "INC-DEFAULT"
    assert default_ico.severity == "SEV1"
    brief = default_ico.to_voice_brief()
    assert "`" not in brief
    assert "Hello, sorry to wake you up" in brief
    assert "We are tracking a SEV1 incident" in brief


def test_get_realtime_model_primary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 11: Verify get_realtime_model selects primary model when API key is present."""
    monkeypatch.setattr(settings, "gemini_api_key", "test-api-key-1234")
    model = get_realtime_model(voice="Puck")
    assert model.model == "gemini-3.8-live"
    assert model._opts.vertexai is False
    assert model._opts.api_key == "test-api-key-1234"


def test_get_realtime_model_fallback_on_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 12: Verify get_realtime_model falls back to Vertex AI when gemini_api_key is unset."""
    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr(settings, "google_cloud_project", "test-gcp-project")
    monkeypatch.setattr(settings, "google_cloud_location", "us-central1")
    model = get_realtime_model(voice="Puck", api_key=None)
    assert model.model == "gemini-live-2.5-flash-native-audio"
    assert model._opts.vertexai is True
    assert model._opts.project == "test-gcp-project"
    assert model._opts.location == "us-central1"


def test_get_realtime_model_fallback_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 13: Verify get_realtime_model falls back to Vertex AI when primary model throws."""
    import livekit.plugins.google.realtime as google_realtime

    monkeypatch.setattr(settings, "gemini_api_key", "test-failing-key")
    monkeypatch.setattr(settings, "google_cloud_project", "fallback-gcp-project")

    orig_init = google_realtime.RealtimeModel.__init__

    def mock_init(self: Any, *args: Any, **kwargs: Any) -> None:
        if kwargs.get("vertexai") is False:
            raise ValueError("Simulated Google AI Studio quota / auth failure (HTTP 429)")
        orig_init(self, *args, **kwargs)

    with patch.object(google_realtime.RealtimeModel, "__init__", side_effect=mock_init, autospec=True):
        model = get_realtime_model(voice="Puck")
        assert model.model == "gemini-live-2.5-flash-native-audio"
        assert model._opts.vertexai is True
        assert model._opts.project == "fallback-gcp-project"


@pytest.mark.asyncio
async def test_conversational_assent_authorizes_mutating_action(mock_ico):
    """Test 14: Conversational assent ('yeah sure, go ahead') authorizes mutating Tier 2 tool execution."""
    dispatched: list[dict[str, Any]] = []

    async def mock_dispatcher(payload: dict[str, Any]) -> bool:
        dispatched.append(payload)
        return True

    session = VoiceAgentSession(mock_ico, temporal_dispatcher=mock_dispatcher)
    mutating_cmd = "kubectl rollout restart deploy/checkout-api"

    # User responds with natural conversational assent
    is_approved, msg, dispatch_event = session.check_confirmation("yeah sure, go ahead", mutating_cmd)
    assert is_approved
    assert "confirmed" in msg.lower()
    assert dispatch_event is not None
    assert session.is_confirmed

    # Now tool execution proceeds and dispatches to Temporal
    result = await session.execute_tool(mutating_cmd)
    assert "SUCCESS" in result
    assert "TIER_2_MUTATING" in result
    assert "dispatched to Temporal" in result
    assert len(dispatched) == 1
    assert dispatched[0]["command"] == mutating_cmd
    assert dispatched[0]["tier"] == ActionTier.TIER_2_MUTATING.value


def test_extract_ico_from_metadata(mock_ico):
    """Test 15: Verify extract_ico_from_metadata parses valid JSON and handles empty/corrupt metadata."""
    import json

    # None or empty metadata returns None
    assert extract_ico_from_metadata(None) is None
    assert extract_ico_from_metadata("") is None
    assert extract_ico_from_metadata("invalid-json") is None

    # Valid direct ICO JSON
    raw_json = mock_ico.model_dump_json()
    extracted = extract_ico_from_metadata(raw_json)
    assert extracted is not None
    assert extracted.incident_id == mock_ico.incident_id

    # Valid wrapped ICO JSON
    wrapped_json = json.dumps({"ico": mock_ico.model_dump()})
    extracted_wrapped = extract_ico_from_metadata(wrapped_json)
    assert extracted_wrapped is not None
    assert extracted_wrapped.incident_id == mock_ico.incident_id


@pytest.mark.asyncio
async def test_voice_agent_session_start(mock_ico):
    """Test 16: Verify session.start binds the agent, starts the session, and triggers generate_reply with opening greeting."""
    from unittest.mock import AsyncMock, MagicMock

    session = VoiceAgentSession(mock_ico, api_key="test-key")
    mock_room = MagicMock()

    mock_livekit_session = MagicMock()
    mock_livekit_session.start = AsyncMock()
    mock_livekit_session.generate_reply = AsyncMock()

    with patch.object(session, "create_livekit_session", return_value=mock_livekit_session):
        started_session = await session.start(mock_room)
        assert started_session is mock_livekit_session
        assert mock_livekit_session.start.await_count == 1
        assert mock_livekit_session.generate_reply.await_count == 1
        instructions = mock_livekit_session.generate_reply.call_args[1]["instructions"]
        assert "Greet the on-call engineer immediately" in instructions
        assert "Hello, sorry to wake you up" in instructions


@pytest.mark.asyncio
async def test_livekit_tool_execution_sets_confirmed_and_returns_json(mock_ico):
    """Test 17: Verify execute_remediation_command sets is_confirmed, notifies console, and returns JSON."""
    session = VoiceAgentSession(mock_ico)
    assert not session.is_confirmed

    tool = session.create_livekit_tool()
    with patch.object(session, "notify_console_resolution", new_callable=AsyncMock) as mock_notify:
        mock_notify.return_value = True
        result = await tool("kubectl rollout restart deploy/checkout-api")

        assert session.is_confirmed is True
        mock_notify.assert_awaited_once_with("kubectl rollout restart deploy/checkout-api")
        data = json.loads(result)
        assert data["status"] == "SUCCESS"
        assert "Remediation executed successfully" in data["message"]


def test_system_instruction_verbal_assent_directives(mock_ico):
    """Test 18: Verify system instructions direct immediate tool execution on verbal assent."""
    session = VoiceAgentSession(mock_ico)
    instructions = session.system_instruction
    assert "execute_remediation_command" in instructions
    assert "conversational assent" in instructions
    assert "stop prompting" in instructions

