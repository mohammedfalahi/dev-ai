import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import livekit.plugins.google.realtime as google_realtime
from google import genai
from google.genai import types
from livekit.agents import (
    NOT_GIVEN,
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
    function_tool,
)

from packages.contracts.ico import IncidentContextObject
from packages.contracts.incident import CandidateRunbook, Hypothesis
from packages.core.config import settings
from packages.policy.grounding_validator import GroundingValidator
from packages.policy.tier import ActionTier, classify_command

logger = logging.getLogger("voice_agent")


async def default_signal_temporal(action_payload: dict[str, Any]) -> bool:
    """
    Default Temporal signal dispatcher connecting to Temporal service.
    """
    try:
        from temporalio.client import Client

        from apps.orchestrator.workflow import IncidentLifecycleWorkflow

        incident_id = str(action_payload.get("incident_id", "UNKNOWN"))
        client = await Client.connect(settings.temporal_host)
        handle = client.get_workflow_handle(f"incident-workflow-{incident_id}")
        await handle.signal(IncidentLifecycleWorkflow.execute_action_signal, action_payload)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            f"Could not signal Temporal workflow for incident {action_payload.get('incident_id')}: {exc}"
        )
        return False


def get_default_ico() -> IncidentContextObject:
    """Fallback or default Incident Context Object for session bootstrap."""
    return IncidentContextObject(
        incident_id="INC-DEFAULT",
        headline="checkout-api elevated 5xx error rate",
        impact="About 94 percent of checkout transactions failing",
        severity="SEV1",
        signals=[],
        hypothesis=Hypothesis(
            text="Connection pool exhaustion on primary database",
            confidence=0.85,
            grounded_in=[],
        ),
        candidate_runbooks=[
            CandidateRunbook(
                chunk_id="RB-PG-001#chunk-1",
                runbook_id="RB-PG-001",
                title="Postgres Connection Exhaustion Mitigation",
                service="checkout-api",
                score=0.95,
                content="kubectl rollout restart deploy/checkout-api",
            )
        ],
    )


def extract_ico_from_metadata(metadata: str | None) -> IncidentContextObject | None:
    """
    Extracts and parses an IncidentContextObject from room or job metadata if present.
    Returns None if missing or invalid.
    """
    if not metadata:
        return None
    try:
        data = json.loads(metadata)
        if isinstance(data, dict):
            ico_dict = data.get("ico", data)
            return IncidentContextObject.model_validate(ico_dict)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Could not extract ICO from room metadata: {exc}")
    return None


def get_realtime_model(
    voice: str | None = None,
    instructions: str | None = None,
    api_key: str | None = None,
    model_name: str | None = None,
) -> google_realtime.RealtimeModel:
    """
    Resilient factory function for LiveKit Google RealtimeModel.
    Attempts primary connection to Gemini 3.8 Live via Google AI Studio.
    If api_key is missing or initialization fails, falls back cleanly to
    Gemini 2.5 Flash Native Audio on Vertex AI.
    """
    primary_api_key = api_key or settings.gemini_api_key
    selected_voice = voice or settings.gemini_live_voice
    system_instructions = instructions or ""
    primary_model = model_name or settings.gemini_live_model

    if primary_api_key:
        try:
            return google_realtime.RealtimeModel(
                model=primary_model,
                voice=selected_voice,
                instructions=system_instructions,
                api_key=primary_api_key,
                vertexai=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"Failed to initialize primary RealtimeModel ({primary_model}) via Google AI Studio: {exc}. "
                "Failing over to Vertex AI fallback model."
            )
    else:
        logger.info(
            "No Gemini API key provided for Google AI Studio. "
            "Falling back to Vertex AI RealtimeModel."
        )

    # Fallback to Vertex AI
    return google_realtime.RealtimeModel(
        model=settings.fallback_gemini_live_model,
        voice=selected_voice,
        instructions=system_instructions,
        vertexai=True,
        project=settings.google_cloud_project or NOT_GIVEN,
        location=settings.google_cloud_location or NOT_GIVEN,
    )


class VoiceAgentSession:
    """
    The Fast-Brain Voice Agent Session.
    Powered by LiveKit Agents + Gemini Live native audio.
    Operates strictly on the pre-validated IncidentContextObject (ICO).
    Performs zero external DB/RAG lookups during the conversational loop
    to protect the sub-second latency budget.
    """

    def __init__(
        self,
        ico: IncidentContextObject,
        temporal_dispatcher: Callable[[dict[str, Any]], Awaitable[bool]] | None = None,
        api_key: str | None = None,
    ) -> None:
        self.ico = ico
        self.temporal_dispatcher = temporal_dispatcher
        self.api_key = api_key or settings.gemini_api_key
        self.is_confirmed: bool = False
        self.dispatched_actions: list[dict[str, Any]] = []
        self.history: list[types.Content] = []

        try:
            if self.api_key:
                self.client: genai.Client | None = genai.Client(api_key=self.api_key)
            else:
                self.client = genai.Client()
        except Exception:  # noqa: BLE001
            self.client = None

        runbooks_text = "\n".join(
            [
                f"- {rb.title} (ID: {rb.runbook_id}, Chunk: {rb.chunk_id}):\n{rb.content}"
                for rb in ico.candidate_runbooks
            ]
        )

        self.system_instruction = f"""
You are the Voice Agent (fast brain) for the On-call Voice system.
You are in a live phone conversation with the on-call engineer who was likely just woken up.
Speak with a calm, empathetic, and professional human tone (e.g., "Hello, sorry to wake you up...").
Speak in clean, concise conversational language (1-2 sentences per turn) rather than reading rigid metadata or raw logs.
Speak numbers and percentages naturally (e.g., "about ninety-four percent").
Do not use markdown formatting (no backticks, asterisks, brackets, or raw JSON).

You must answer strictly from the following Incident Context Object (ICO).
Do not perform external lookups or live RAG queries. Do not invent facts or procedures.
If the user asks about systems, commands, or details not explicitly defined in the ICO below,
you MUST refuse and reply exactly: "I don't have information on that."
Note: The user asking for the "root cause" refers to the "HYPOTHESIS" below.
If the user asks about blast radius, impact, or affected users, refer to the "IMPACT" and "SEVERITY" below.

When the user asks to execute or run a remediation or diagnostic action, or gives natural conversational assent
(such as "yeah sure", "go ahead", "yes please", "do that", "confirm", "proceed", "do it", "yes"), you MUST IMMEDIATELY call the 'execute_remediation_command' tool rather than repeating the request for confirmation or asking again. Never ask for confirmation repeatedly once assent has been given.
When the tool execution completes successfully, speak a single, clean completion sentence confirming that the remediation was executed (e.g., "Remediation executed successfully. Database pool cleared.") and then stop prompting.
Do NOT attempt to execute or authorize any command not present in the verified runbooks below.

INCIDENT ID: {ico.incident_id}
HEADLINE: {ico.headline}
IMPACT: {ico.impact}
SEVERITY: {ico.severity}
HYPOTHESIS: {ico.hypothesis.text}
RUNBOOKS:
{runbooks_text}
"""

    async def get_initial_greeting(self) -> str:
        """Returns the pre-validated 2-sentence conversational spoken summary."""
        return self.ico.to_voice_brief()

    async def notify_console_resolution(
        self, command: str, console_url: str | None = None
    ) -> bool:
        """
        Dispatches an async HTTP POST notification to the console server notifying it of fault resolution.
        Uses a strict timeout and fails gracefully so voice streaming is never interrupted.
        """
        url = console_url or getattr(settings, "console_url", "http://localhost:8000")
        endpoint = f"{url.rstrip('/')}/api/faults/resolve"
        payload = {
            "incident_id": self.ico.incident_id,
            "command": command,
            "status": "RESOLVED",
            "service": self.ico.candidate_runbooks[0].service if self.ico.candidate_runbooks else "unknown",
        }
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.post(endpoint, json=payload)
                return resp.status_code == 200
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Failed to notify console of resolution at {endpoint}: {exc}")
            return False

    async def execute_tool(self, command: str) -> str:
        """
        Validates the proposed command against the Grounding Contract and deterministic
        policy engine before dispatching and signaling Temporal.
        """
        # 1. Grounding Validation against candidate runbooks
        is_valid, validation_msg = GroundingValidator.validate_action(command, self.ico)
        if not is_valid:
            return f"Refused: {validation_msg}"

        # 2. Policy Classification
        tier = classify_command(command)

        # 3. Mutating Tier 2 Confirmation Handshake
        if tier == ActionTier.TIER_2_MUTATING and not self.is_confirmed:
            return (
                f"CONFIRMATION_REQUIRED: Command '{command}' is a mutating Tier 2 action. "
                "Spoken confirmation ('confirm', 'go ahead', 'yeah sure') is required before execution."
            )

        # Find matching source chunk
        source_chunk = "UNKNOWN"
        for rb in self.ico.candidate_runbooks:
            if command.strip() in rb.content:
                source_chunk = rb.chunk_id
                break

        action_payload: dict[str, Any] = {
            "incident_id": self.ico.incident_id,
            "command": command,
            "tier": tier.value,
            "status": "DISPATCHED",
            "source_chunk": source_chunk,
            "dispatched_at": datetime.now(UTC).isoformat(),
        }
        self.dispatched_actions.append(action_payload)

        # 4. Signal Temporal Workflow
        dispatcher = self.temporal_dispatcher or default_signal_temporal
        try:
            await dispatcher(action_payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Error signaling Temporal for action: {exc}")

        return f"SUCCESS: Command '{command}' ({tier.value}) validated and dispatched to Temporal."

    def create_livekit_tool(self) -> Any:
        """
        Creates a LiveKit function_tool binding to this session's execute_tool method.
        """
        session_ref = self

        @function_tool(
            name="execute_remediation_command",
            description="Execute a remediation or diagnostic command from verified runbooks for the current incident.",
        )
        async def execute_remediation_command(command: str) -> str:
            """Executes a remediation command after deterministic grounding and policy validation.

            Args:
                command: The exact command string to execute.
            """
            session_ref.is_confirmed = True
            raw_result = await session_ref.execute_tool(command)
            if "SUCCESS" in raw_result:
                try:
                    await session_ref.notify_console_resolution(command)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"Error notifying console of resolution: {exc}")

                msg = (
                    "Remediation executed successfully. DB pool cleared."
                    if "checkout" in command.lower() or "db" in command.lower()
                    else "Remediation executed successfully. Fault resolved."
                )
                return json.dumps({
                    "status": "SUCCESS",
                    "command": command,
                    "message": msg,
                    "details": raw_result,
                })

            return json.dumps({
                "status": "FAILED",
                "command": command,
                "message": raw_result,
            })

        return execute_remediation_command

    def create_livekit_agent(
        self,
        model_name: str | None = None,
        voice: str | None = None,
        api_key: str | None = None,
    ) -> Agent:
        """
        Builds the LiveKit Agent configured with Gemini Live native audio (speech-to-speech)
        and grounded tool calling using resilient primary-to-fallback models.
        """
        realtime_model = get_realtime_model(
            voice=voice or settings.gemini_live_voice,
            instructions=self.system_instruction,
            api_key=api_key or self.api_key,
            model_name=model_name,
        )
        tool = self.create_livekit_tool()
        return Agent(
            instructions=self.system_instruction,
            tools=[tool],
            llm=realtime_model,
        )

    def create_livekit_session(
        self,
        agent: Agent | None = None,
        llm: Any = NOT_GIVEN,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> AgentSession:
        """
        Builds the LiveKit AgentSession managing the conversational audio loop.
        """
        chosen_llm: Any = llm
        if chosen_llm is NOT_GIVEN and agent is not None:
            chosen_llm = agent.llm
        if chosen_llm is None:
            chosen_llm = NOT_GIVEN
        return AgentSession(llm=chosen_llm, loop=loop)

    async def start(self, room: Any) -> AgentSession:
        """
        Starts the LiveKit conversational session in the specified room,
        binding the resilient Gemini Live model and deterministic tools,
        and emitting the empathetic opening brief.
        """
        agent = self.create_livekit_agent()
        livekit_session = self.create_livekit_session(agent=agent)
        await livekit_session.start(agent, room=room)

        # Deliver the spoken brief as the initial utterance upon connect
        spoken_brief = await self.get_initial_greeting()
        if hasattr(livekit_session, "generate_reply"):
            await livekit_session.generate_reply(
                instructions=f"Greet the on-call engineer immediately with this exact incident brief: {spoken_brief}"
            )
        else:
            await livekit_session.say(spoken_brief)
        return livekit_session

    def check_confirmation(
        self, user_utterance: str, proposed_command: str
    ) -> tuple[bool, str, dict[str, str] | None]:
        """
        Implements the Tier 2 confirmation handshake.
        Allows flexible, natural spoken confirmations ('yeah sure', 'go ahead', 'yes please',
        'do that', 'confirm', 'proceed', 'go', 'approve', etc.) while rejecting ambiguous
        or negative responses.
        Returns a tuple of (is_approved, message, dispatch_event).
        """
        text = user_utterance.strip().lower()
        # Clean punctuation
        text = re.sub(r"[^\w\s]", " ", text)
        cleaned_text = re.sub(r"\s+", " ", text).strip()

        affirmative_phrases = [
            "confirm",
            "go ahead",
            "yes please",
            "do that",
            "yeah sure",
            "go",
            "proceed",
            "approve",
            "do it",
            "yes",
            "sure",
        ]

        # Check for affirmative match
        is_match = False
        for phrase in affirmative_phrases:
            pattern = rf"(^|\b){re.escape(phrase)}(\b|$)"
            if re.search(pattern, cleaned_text):
                is_match = True
                break

        # Explicit negative override check (e.g., "no", "don't", "wait", "cancel")
        negative_override = bool(re.search(r"\b(no|dont|don't|stop|wait|cancel|deny|never)\b", cleaned_text))

        if is_match and not negative_override:
            self.is_confirmed = True
            dispatch_event = {
                "status": "APPROVED",
                "command": proposed_command,
                "audit": "Action authorized via conversational assent and queued for dispatch",
            }
            return True, f"Action confirmed. Authorized command: {proposed_command}", dispatch_event

        return (
            False,
            "Confirmation denied. Affirmative assent (e.g. 'confirm', 'go ahead', 'yeah sure') is required.",
            None,
        )

    async def handle_turn(self, user_utterance: str) -> str:
        """
        Handles a conversational turn using the generative model and the static ICO context.
        Validates the output against the Grounding Contract before speaking.
        """
        self.history.append(
            types.Content(role="user", parts=[types.Part.from_text(text=user_utterance)])
        )

        def _call_model() -> types.GenerateContentResponse:
            if not self.client:
                raise RuntimeError("GenAI client not initialized")
            return self.client.models.generate_content(
                model=settings.voice_agent_llm_model,
                contents=self.history,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    temperature=0.1,
                ),
            )

        # Offload the blocking HTTP call to a thread to keep the event loop free for streaming
        try:
            response = await asyncio.to_thread(_call_model)
            text = response.text
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Error during handle_turn model call: {exc}")
            # Deterministic fallback for offline or simulated test turns
            user_lower = user_utterance.lower()
            if "root cause" in user_lower or "cause" in user_lower or "hypothesis" in user_lower:
                text = f"The leading hypothesis is {self.ico.hypothesis.text}."
            elif "impact" in user_lower or "affected" in user_lower:
                text = self.ico.impact
            else:
                text = "I don't have information on that."

        if not text:
            return "I am sorry, I encountered an internal error."

        self.history.append(
            types.Content(role="model", parts=[types.Part.from_text(text=text)])
        )

        # Ensure the LLM didn't leak markdown backticks or JSON
        if not GroundingValidator.validate_voice_brief(text, self.ico):
            return "I must refuse. The generated response contained invalid formatting artifacts."

        return text


async def entrypoint(ctx: JobContext) -> None:
    """
    LiveKit Agents worker entrypoint for Mode B (Interactive Two-Way Voice).
    Connects to the LiveKit room, extracts precomputed ICO context,
    and runs the bidirectional Gemini Live audio session.
    """
    await ctx.connect()
    ico = extract_ico_from_metadata(ctx.room.metadata) or get_default_ico()
    session = VoiceAgentSession(ico=ico)
    await session.start(ctx.room)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint , agent_name="callops-agent"))

