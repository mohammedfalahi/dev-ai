import time
import httpx
from typing import Any
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from apps.investigator.engine import investigate_incident
from apps.voice.agent import VoiceAgentSession
from packages.policy.grounding_validator import GroundingValidator
from packages.policy.tier import classify_command, ActionTier

app = FastAPI(title="On-call Voice Console")

# Global state for the active agent session
active_session: VoiceAgentSession | None = None
active_proposed_command: str | None = None
active_tier: ActionTier | None = None


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
    latency_ms: float
    approved: bool | None = None
    approval_message: str | None = None


BROKEN_SHOP_URL = "http://localhost:8081"


@app.post("/api/faults/{fault_name}")
async def trigger_fault(fault_name: str):
    global active_session, active_proposed_command, active_tier

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(f"{BROKEN_SHOP_URL}/faults/{fault_name}")
            resp.raise_for_status()
            alert_data = resp.json()
        except Exception as e:
            if fault_name == "reset":
                active_session = None
                active_proposed_command = None
                active_tier = None
                return {"status": "reset locally, broken-shop not running"}
            raise HTTPException(
                status_code=502, detail=f"Failed to contact broken-shop: {e}"
            )

    if fault_name == "reset":
        active_session = None
        active_proposed_command = None
        active_tier = None
        return alert_data

    # Investigate
    ico = await investigate_incident(alert_data)

    # Initialize Voice Session
    active_session = VoiceAgentSession(ico)
    greeting = await active_session.get_initial_greeting()

    return {"alert": alert_data, "ico": ico.model_dump(), "greeting": greeting}


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    global active_session, active_proposed_command, active_tier

    if not active_session:
        raise HTTPException(
            status_code=400, detail="No active session. Trigger a fault first."
        )

    start_time = time.perf_counter()

    approved = None
    approval_msg = None

    # Handle pending confirmation
    if active_tier == ActionTier.TIER_2_MUTATING and active_proposed_command:
        is_app, msg = active_session.check_confirmation(
            req.message, active_proposed_command
        )
        if is_app:
            approved = True
            approval_msg = msg
            active_proposed_command = None
            active_tier = None
            latency_ms = (time.perf_counter() - start_time) * 1000
            return ChatResponse(
                response=msg, latency_ms=latency_ms, approved=True, approval_message=msg
            )
        else:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return ChatResponse(
                response=msg,
                latency_ms=latency_ms,
                approved=False,
                approval_message=msg,
            )

    # Regular turn
    response_text = await active_session.handle_turn(req.message)

    # Parse LLM response text for potential mutating commands from runbooks
    for rb in active_session.ico.candidate_runbooks:
        lines = rb.content.split("\n")
        for line in lines:
            line = line.strip()
            if line and line in response_text:
                tier = classify_command(line)
                if tier == ActionTier.TIER_2_MUTATING:
                    active_proposed_command = line
                    active_tier = tier
                    break

    latency_ms = (time.perf_counter() - start_time) * 1000

    return ChatResponse(
        response=response_text,
        latency_ms=latency_ms,
        approved=approved,
        approval_message=approval_msg,
    )


app.mount("/", StaticFiles(directory="apps/console/static", html=True), name="static")
