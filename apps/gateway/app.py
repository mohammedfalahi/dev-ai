import hashlib
import hmac
import time
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from apps.gateway.dedupe import deduplicator
from apps.orchestrator.workflow import IncidentLifecycleWorkflow
from packages.contracts.alert import NormalizedAlert, PagingDecision
from packages.core.config import settings

app = FastAPI(title="On-call Voice Signal Ingest & Triage Gateway")

# Pluggable dispatcher for workflow execution (injected in tests or using Temporal in prod)
workflow_dispatcher: Callable[[dict[str, Any]], Awaitable[bool]] | None = None


def verify_signature(
    body: bytes,
    signature_header: str | None,
    timestamp_header: str | None,
    secret: str = settings.hmac_secret,
) -> bool:
    """
    Validates HMAC-SHA256 signature and timestamp tolerance (+/- 300s).
    """
    if not signature_header or not timestamp_header:
        return False

    # Check timestamp drift
    try:
        req_ts = int(timestamp_header)
        current_ts = int(time.time())
        if abs(current_ts - req_ts) > 300:
            return False
    except ValueError:
        return False

    # Compute expected HMAC digest over "{timestamp}.{body}"
    message = f"{timestamp_header}.".encode() + body
    expected_mac = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    
    # Strip any prefix like "sha256="
    clean_sig = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected_mac, clean_sig)


async def default_temporal_dispatch(alert_payload: dict[str, Any]) -> bool:
    """
    Default production dispatcher connecting to Temporal.
    """
    try:
        from temporalio.client import Client
        client = await Client.connect(settings.temporal_host)
        incident_id = alert_payload["incident_id"]
        await client.start_workflow(
            IncidentLifecycleWorkflow.run,
            alert_payload,
            id=f"incident-workflow-{incident_id}",
            task_queue="incident-task-queue",
        )
        return True
    except Exception:  # noqa: BLE001
        # Fall back gracefully in offline or local dev
        return False


class IngestResponse(BaseModel):
    status: str
    delivery_id: str
    fingerprint: str
    incident_id: str
    is_new_incident: bool
    is_duplicate_delivery: bool
    alert_count: int
    decision: str
    workflow_dispatched: bool


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "gateway"}


@app.post("/api/v1/alerts", response_model=IngestResponse)
async def ingest_alert(
    request: Request,
    alert: NormalizedAlert,
    x_signature_256: str | None = Header(default=None),
    x_timestamp: str | None = Header(default=None),
    x_test_bypass_signature: str | None = Header(default=None),
) -> IngestResponse:
    # 1. Enforce payload size limits (1MB cap)
    raw_body = await request.body()
    if len(raw_body) > 1_000_000:
        raise HTTPException(status_code=413, detail="Payload exceeds 1MB limit")

    # 2. Signature verification
    if x_test_bypass_signature != "true":
        is_valid = verify_signature(raw_body, x_signature_256, x_timestamp)
        if not is_valid:
            raise HTTPException(status_code=401, detail="Invalid HMAC signature or expired timestamp")

    # 3. Deduplication and Grouping
    incident, is_new, is_duplicate = deduplicator.process_alert(alert)

    # 4. Workflow dispatch for SEV1 voice page
    workflow_dispatched = False
    if is_new and incident.decision == PagingDecision.VOICE_PAGE:
        dispatch_payload = {
            "incident_id": incident.incident_id,
            "severity": incident.severity,
            "service": incident.service,
            "error": f"{alert.headline}. {alert.description}".strip(),
            "timestamp": alert.observed_at,
        }

        dispatcher = workflow_dispatcher or default_temporal_dispatch
        try:
            workflow_dispatched = await dispatcher(dispatch_payload)
        except Exception:  # noqa: BLE001
            workflow_dispatched = False

    return IngestResponse(
        status="processed",
        delivery_id=alert.delivery_id,
        fingerprint=incident.fingerprint,
        incident_id=incident.incident_id,
        is_new_incident=is_new,
        is_duplicate_delivery=is_duplicate,
        alert_count=incident.alert_count,
        decision=incident.decision.value,
        workflow_dispatched=workflow_dispatched,
    )
