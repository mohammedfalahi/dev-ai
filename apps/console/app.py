import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from apps.investigator.engine import investigate_incident
from apps.voice.agent import VoiceAgentSession
from evals.run_eval_matrix import run_eval_matrix
from packages.policy.tier import ActionTier, classify_command

logger = logging.getLogger("console")

app = FastAPI(title="On-call Voice Console & Evaluation Hub")

STATIC_DIR = Path(__file__).resolve().parent / "static"
EVAL_REPORT_PATH = Path("eval-report.json")
BROKEN_SHOP_URL = "http://localhost:8081"

# Global state for the active agent session and drill
active_session: VoiceAgentSession | None = None
active_proposed_command: str | None = None
active_tier: ActionTier | None = None
active_workflow_id: str | None = None
active_fault: str | None = None
active_fault_status: str = "IDLE"  # "IDLE", "TRIGGERED", "RESOLVED"
fault_states: dict[str, str] = {}  # {fault_id: "IDLE" | "TRIGGERED" | "RESOLVED"}
dedupe_counter: dict[str, int] = {"alerts_received": 0, "incidents_created": 0}


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
    latency_ms: float
    approved: bool | None = None
    approval_message: str | None = None
    dispatch_event: dict[str, Any] | None = None


class DrillTriggerRequest(BaseModel):
    fault: str = "db-pool-exhaustion"


class DrillTriggerResponse(BaseModel):
    incident_id: str
    workflow_id: str
    status: str
    alert: dict[str, Any]
    ico: dict[str, Any]
    greeting: str


class DrillStatusResponse(BaseModel):
    workflow_id: str
    status: str
    call_status: str
    tier: str | None = None
    proposed_command: str | None = None
    is_confirmed: bool = False
    ico: dict[str, Any] | None = None
    dispatched_actions: list[dict[str, Any]] = []
    active_fault: str | None = None
    active_fault_status: str = "IDLE"
    fault_states: dict[str, str] = {}


class FaultResolveRequest(BaseModel):
    fault_id: str | None = None
    incident_id: str | None = None
    command: str | None = None
    status: str = "RESOLVED"


class FaultEscalateRequest(BaseModel):
    fault_id: str | None = None
    incident_id: str | None = None
    command: str | None = None
    status: str = "PROBLEM_ESCALATED_TO_HUMAN"


class FaultResetRequest(BaseModel):
    fault_id: str | None = None


@app.get("/triage", response_class=FileResponse)
async def get_triage_page() -> FileResponse:
    triage_file = STATIC_DIR / "triage.html"
    if not triage_file.exists():
        raise HTTPException(status_code=404, detail="Triage page not found")
    return FileResponse(triage_file)


@app.get("/api/faults/status")
async def get_faults_status() -> dict[str, Any]:
    return {
        "active_fault": active_fault,
        "active_fault_status": active_fault_status,
        "fault_states": fault_states,
        "is_confirmed": active_session.is_confirmed if active_session else False,
        "workflow_id": active_workflow_id,
        "incident_id": active_session.ico.incident_id if active_session else None,
    }


@app.post("/api/faults/resolve")
async def resolve_fault_endpoint(
    req: FaultResolveRequest | None = None,
) -> dict[str, Any]:
    global active_fault_status

    active_fault_status = "RESOLVED"
    target_fault = (
        (req.fault_id if req and req.fault_id else None)
        or active_fault
        or "db-pool-exhaustion"
    )
    fault_states[target_fault] = "RESOLVED"

    if active_session:
        active_session.is_confirmed = True

    return {
        "status": "RESOLVED",
        "fault_id": target_fault,
        "active_fault": active_fault,
        "active_fault_status": active_fault_status,
        "fault_states": fault_states,
    }


@app.post("/api/faults/escalate")
async def escalate_fault_endpoint(
    req: FaultEscalateRequest | None = None,
) -> dict[str, Any]:
    global active_fault_status

    active_fault_status = "PROBLEM_ESCALATED_TO_HUMAN"
    target_fault = (
        (req.fault_id if req and req.fault_id else None)
        or active_fault
        or "db-pool-exhaustion"
    )
    fault_states[target_fault] = "PROBLEM_ESCALATED_TO_HUMAN"

    if active_session:
        active_session.is_confirmed = True
        active_session.status = "PROBLEM_ESCALATED_TO_HUMAN"

    return {
        "status": "PROBLEM_ESCALATED_TO_HUMAN",
        "fault_id": target_fault,
        "active_fault": active_fault,
        "active_fault_status": active_fault_status,
        "fault_states": fault_states,
    }


@app.post("/api/faults/reset")
async def reset_fault_endpoint(
    req: FaultResetRequest | None = None,
) -> dict[str, Any]:
    global active_session, active_proposed_command, active_tier, active_workflow_id, active_fault, active_fault_status

    target_fault = req.fault_id if (req and req.fault_id) else None

    # Reset broken-shop if reachable
    async with httpx.AsyncClient() as client:
        try:
            await client.post(f"{BROKEN_SHOP_URL}/faults/reset", timeout=2.0)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Reset request to broken-shop skipped: {exc}")

    if target_fault:
        fault_states[target_fault] = "IDLE"
        if target_fault == active_fault:
            active_session = None
            active_proposed_command = None
            active_tier = None
            active_workflow_id = None
            active_fault = None
            active_fault_status = "IDLE"
    else:
        # Global reset
        for k in list(fault_states.keys()):
            fault_states[k] = "IDLE"
        active_session = None
        active_proposed_command = None
        active_tier = None
        active_workflow_id = None
        active_fault = None
        active_fault_status = "IDLE"

    return {
        "status": "RESET",
        "fault_id": target_fault,
        "active_fault": active_fault,
        "active_fault_status": active_fault_status,
        "fault_states": fault_states,
    }


@app.post("/api/faults/{fault_name}")
async def trigger_fault(fault_name: str) -> dict[str, Any]:
    global active_session, active_proposed_command, active_tier, active_workflow_id, active_fault, active_fault_status

    if fault_name == "reset":
        return await reset_fault_endpoint()

    dedupe_counter["alerts_received"] += 1

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(f"{BROKEN_SHOP_URL}/faults/{fault_name}", timeout=5.0)
            resp.raise_for_status()
            alert_data = resp.json()
        except Exception:  # noqa: BLE001
            # Synthesize alert if broken-shop is not running in background
            alert_data = {
                "incident_id": f"INC-LOCAL-{int(time.time())}",
                "severity": "SEV1",
                "service": "checkout-api" if "db" in fault_name else "redis-cache",
                "error": f"Simulated {fault_name}: connection acquire timeout",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

    dedupe_counter["incidents_created"] += 1

    # Investigate to build ICO
    ico = await investigate_incident(alert_data)

    # Initialize Voice Session
    active_session = VoiceAgentSession(ico)
    greeting = await active_session.get_initial_greeting()
    active_workflow_id = f"workflow-{ico.incident_id}"
    active_fault = fault_name
    active_fault_status = "TRIGGERED"
    fault_states[fault_name] = "TRIGGERED"

    # Extract proposed command and policy tier
    active_proposed_command = ico.proposed_action or (
        ico.candidate_runbooks[0].content if ico.candidate_runbooks else None
    )
    active_tier = classify_command(active_proposed_command) if active_proposed_command else None

    # Dispatch on-call notification / PSTN dial according to TELEPHONY_MODE
    call_dispatch_status: str | None = None
    try:
        from apps.orchestrator.activities import notify_oncall_activity

        call_dispatch_status = await notify_oncall_activity(ico.incident_id, ico.model_dump())
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Could not dispatch on-call notification for {ico.incident_id}: {exc}")

    return {
        "alert": alert_data,
        "ico": ico.model_dump(),
        "greeting": greeting,
        "workflow_id": active_workflow_id,
        "tier": active_tier.value if active_tier else None,
        "proposed_command": active_proposed_command,
        "dedupe": dedupe_counter,
        "active_fault": active_fault,
        "active_fault_status": active_fault_status,
        "fault_states": fault_states,
        "call_dispatch_status": call_dispatch_status,
    }


@app.post("/api/drill/trigger", response_model=DrillTriggerResponse)
async def drill_trigger(req: DrillTriggerRequest) -> DrillTriggerResponse:
    data = await trigger_fault(req.fault)
    return DrillTriggerResponse(
        incident_id=data["ico"]["incident_id"],
        workflow_id=data["workflow_id"],
        status="INVESTIGATED",
        alert=data["alert"],
        ico=data["ico"],
        greeting=data["greeting"],
    )


@app.get("/api/drill/status/{workflow_id}", response_model=DrillStatusResponse)
async def drill_status(workflow_id: str) -> DrillStatusResponse:
    if not active_session:
        raise HTTPException(status_code=404, detail="No active drill session found.")

    drill_status_str = "NOTIFYING"
    if active_fault_status == "RESOLVED":
        drill_status_str = "RESOLVED"
    elif (
        active_fault_status == "PROBLEM_ESCALATED_TO_HUMAN"
        or getattr(active_session, "status", "") == "PROBLEM_ESCALATED_TO_HUMAN"
    ):
        drill_status_str = "PROBLEM_ESCALATED_TO_HUMAN"
    elif active_session.is_confirmed:
        drill_status_str = "DISPATCHED"

    return DrillStatusResponse(
        workflow_id=workflow_id,
        status=drill_status_str,
        call_status="CONNECTED",
        tier=active_tier.value if active_tier else None,
        proposed_command=active_proposed_command,
        is_confirmed=active_session.is_confirmed,
        ico=active_session.ico.model_dump(),
        dispatched_actions=active_session.dispatched_actions,
        active_fault=active_fault,
        active_fault_status=active_fault_status,
        fault_states=fault_states,
    )


@app.get("/api/evals/latest")
async def get_latest_evals() -> dict[str, Any]:
    if EVAL_REPORT_PATH.exists():
        try:
            return json.loads(EVAL_REPORT_PATH.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Failed to read eval-report.json: {exc}")

    # Execute a lightweight slice run (limit=3) if no report is present
    result = await run_eval_matrix(limit=3)
    data = result.to_dict()
    EVAL_REPORT_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


@app.post("/api/evals/run")
async def run_evals() -> dict[str, Any]:
    result = await run_eval_matrix(limit=5)
    data = result.to_dict()
    EVAL_REPORT_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest) -> ChatResponse:
    global active_proposed_command, active_tier, active_fault_status

    if not active_session:
        raise HTTPException(
            status_code=400, detail="No active session. Trigger a fault first."
        )

    start_time = time.perf_counter()

    approved = None
    approval_msg = None
    dispatch_evt = None

    # Handle pending confirmation for mutating Tier 2 action
    if active_tier == ActionTier.TIER_2_MUTATING and active_proposed_command:
        is_app, msg, dispatch = active_session.check_confirmation(
            req.message, active_proposed_command
        )
        if is_app:
            approved = True
            approval_msg = msg
            dispatch_evt = dispatch
            active_proposed_command = None
            active_tier = None
            if dispatch_evt and dispatch_evt.get("status") == "PROBLEM_ESCALATED_TO_HUMAN":
                active_fault_status = "PROBLEM_ESCALATED_TO_HUMAN"
                if active_fault:
                    fault_states[active_fault] = "PROBLEM_ESCALATED_TO_HUMAN"
            else:
                active_fault_status = "RESOLVED"
                if active_fault:
                    fault_states[active_fault] = "RESOLVED"
            latency_ms = (time.perf_counter() - start_time) * 1000
            return ChatResponse(
                response=msg,
                latency_ms=latency_ms,
                approved=True,
                approval_message=msg,
                dispatch_event=dispatch_evt,
            )
        else:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return ChatResponse(
                response=msg,
                latency_ms=latency_ms,
                approved=False,
                approval_message=msg,
                dispatch_event=None,
            )

    # Regular conversational turn
    response_text = await active_session.handle_turn(req.message)

    # Parse response for candidate runbook commands
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
        dispatch_event=dispatch_evt,
    )


# Mount static directory for frontend assets
app.mount("/", StaticFiles(directory="apps/console/static", html=True), name="static")
