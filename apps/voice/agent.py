import asyncio
import re

from google import genai
from google.genai import types

from packages.contracts.ico import IncidentContextObject
from packages.core.config import settings
from packages.policy.grounding_validator import GroundingValidator


class VoiceAgentSession:
    """
    The Fast Brain Voice Agent.
    Operates strictly on the pre-validated IncidentContextObject (ICO).
    Performs zero external DB/RAG lookups during the conversational loop 
    to protect the <800ms latency budget.
    """

    def __init__(self, ico: IncidentContextObject):
        self.ico = ico
        self.client = genai.Client()
        self.history: list[types.Content] = []

        runbooks_text = "\n".join(
            [f"- {rb.title} (ID: {rb.runbook_id}):\n{rb.content}" for rb in ico.candidate_runbooks]
        )

        self.system_instruction = f"""
        You are the Voice Agent (fast brain) for the On-call Voice system.
        You must speak strictly from the following Incident Context Object (ICO).
        Do not perform external lookups. Do not invent facts or procedures.
        Keep answers short (1-2 sentences).
        Do not use markdown formatting (no *, _, `, or ~). Speak numbers naturally.

        If the user asks about systems, commands, or details not explicitly defined 
        in the ICO below, you MUST refuse and reply exactly: "I don't have information on that."
        Note: The user asking for the "root cause" refers to the "HYPOTHESIS" below.
        If the user asks about blast radius, impact, or affected users, refer to the "IMPACT" and "SEVERITY" below.

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

    async def handle_turn(self, user_utterance: str) -> str:
        """
        Handles a conversational turn using the generative model and the static ICO context.
        Validates the output against the Grounding Contract before speaking.
        """
        self.history.append(
            types.Content(role="user", parts=[types.Part.from_text(text=user_utterance)])
        )

        def _call_model() -> types.GenerateContentResponse:
            return self.client.models.generate_content(
                model=settings.voice_agent_llm_model,
                contents=self.history,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    temperature=0.1,
                ),
            )

        # Offload the blocking HTTP call to a thread to keep the event loop free for streaming
        response = await asyncio.to_thread(_call_model)
        
        text = response.text
        if not text:
            return "I am sorry, I encountered an internal error."

        self.history.append(
            types.Content(role="model", parts=[types.Part.from_text(text=text)])
        )

        # Ensure the LLM didn't leak markdown backticks or JSON
        if not GroundingValidator.validate_voice_brief(text, self.ico):
            return "I must refuse. The generated response contained invalid formatting artifacts."

        return text

    def check_confirmation(self, user_utterance: str, proposed_command: str) -> tuple[bool, str, dict[str, str] | None]:
        """
        Implements the Tier 2 confirmation handshake.
        Requires the exact explicit keyword to authorize the action.
        Returns a tuple of (is_approved, message, dispatch_event).
        """
        text = user_utterance.strip().lower()
        # Remove punctuation to catch isolated keywords
        text = re.sub(r'[^\w\s]', '', text)
        
        # We accept 'confirm' (prompt requested) or 'go' (original architecture document)
        # Any casual assent like "yeah sure" or "do it" fails this strict check.
        if text == "confirm" or text == "go":
            dispatch_event = {
                "status": "APPROVED",
                "command": proposed_command,
                "audit": "Action logged and dispatched to Slack #incidents"
            }
            return True, f"Action confirmed. Dispatching command: {proposed_command}", dispatch_event
            
        return False, "Confirmation denied. Exact keyword 'confirm' is required.", None
