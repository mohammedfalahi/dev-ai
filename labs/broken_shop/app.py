from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Broken Shop Simulator")


class FaultState:
    current_fault: str | None = None
    db_connections: int = 10
    health_status: str = "healthy"


state = FaultState()


class AlertResponse(BaseModel):
    incident_id: str
    severity: str
    service: str
    error: str
    timestamp: str


@app.get("/health")
def health():
    return {
        "status": state.health_status,
        "db_connections": state.db_connections,
        "active_fault": state.current_fault,
    }


@app.post("/faults/db-pool-exhaustion", response_model=AlertResponse)
def trigger_db_pool():
    state.current_fault = "db-pool-exhaustion"
    state.db_connections = 100
    state.health_status = "degraded"
    return AlertResponse(
        incident_id="INC-DB-001",
        severity="SEV1",
        service="checkout-api",
        error="asyncpg.exceptions.TimeoutError or pool acquire timeout",
        timestamp="2026-09-24T12:00:00Z",
    )


@app.post("/faults/redis-oom", response_model=AlertResponse)
def trigger_redis_oom():
    state.current_fault = "redis-oom"
    state.db_connections = 10
    state.health_status = "degraded"
    return AlertResponse(
        incident_id="INC-REDIS-001",
        severity="SEV2",
        service="redis-cache",
        error="Shoppers getting logged out because session cache memory is exhausted",
        timestamp="2026-09-24T12:05:00Z"
    )

@app.post("/faults/edge-502", response_model=AlertResponse)
def trigger_edge_502():
    state.current_fault = "edge-502"
    state.health_status = "degraded"
    return AlertResponse(
        incident_id="INC-EDGE-001",
        severity="SEV2",
        service="edge-proxy",
        error="502 Bad Gateway upstream timeout",
        timestamp="2026-09-24T12:10:00Z"
    )

@app.post("/faults/webhook-loop", response_model=AlertResponse)
def trigger_webhook_loop():
    state.current_fault = "webhook-loop"
    state.health_status = "degraded"
    return AlertResponse(
        incident_id="INC-WEBHOOK-001",
        severity="SEV2",
        service="payment-gateway",
        error="500 error loop in webhook receiver",
        timestamp="2026-09-24T12:15:00Z"
    )

@app.post("/faults/db-deadlock", response_model=AlertResponse)
def trigger_db_deadlock():
    state.current_fault = "db-deadlock"
    state.health_status = "degraded"
    return AlertResponse(
        incident_id="INC-DB-002",
        severity="SEV2",
        service="checkout-api",
        error="deadlock detected DETAIL: Process 1234 waits for ShareLock",
        timestamp="2026-09-24T12:20:00Z"
    )

@app.post("/faults/undocumented-anomaly", response_model=AlertResponse)
def trigger_undocumented_anomaly():
    state.current_fault = "undocumented-anomaly"
    state.health_status = "degraded"
    return AlertResponse(
        incident_id="INC-ANOMALY-001",
        severity="SEV3",
        service="unknown-service",
        error="Quantum entanglement cosmic ray failure",
        timestamp="2026-09-24T12:25:00Z"
    )


@app.post("/faults/reset")
def reset_fault():
    state.current_fault = None
    state.db_connections = 10
    state.health_status = "healthy"
    return {"status": "reset_successful"}
