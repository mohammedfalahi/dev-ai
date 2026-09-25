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
        timestamp="2026-09-24T12:05:00Z",
    )


@app.post("/faults/reset")
def reset_fault():
    state.current_fault = None
    state.db_connections = 10
    state.health_status = "healthy"
    return {"status": "reset_successful"}
