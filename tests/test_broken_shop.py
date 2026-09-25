from fastapi.testclient import TestClient

from labs.broken_shop.app import app

client = TestClient(app)

def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert "status" in resp.json()

def test_db_pool_exhaustion():
    resp = client.post("/faults/db-pool-exhaustion")
    assert resp.status_code == 200
    data = resp.json()
    assert data["incident_id"] == "INC-DB-001"
    assert data["service"] == "checkout-api"

def test_redis_oom():
    resp = client.post("/faults/redis-oom")
    assert resp.status_code == 200
    assert resp.json()["incident_id"] == "INC-REDIS-001"

def test_edge_502():
    resp = client.post("/faults/edge-502")
    assert resp.status_code == 200
    data = resp.json()
    assert data["incident_id"] == "INC-EDGE-001"
    assert "502" in data["error"]

def test_webhook_loop():
    resp = client.post("/faults/webhook-loop")
    assert resp.status_code == 200
    data = resp.json()
    assert data["incident_id"] == "INC-WEBHOOK-001"
    assert "webhook" in data["error"].lower()

def test_db_deadlock():
    resp = client.post("/faults/db-deadlock")
    assert resp.status_code == 200
    data = resp.json()
    assert data["incident_id"] == "INC-DB-002"
    assert "deadlock" in data["error"].lower()

def test_undocumented_anomaly():
    resp = client.post("/faults/undocumented-anomaly")
    assert resp.status_code == 200
    data = resp.json()
    assert data["incident_id"] == "INC-ANOMALY-001"
    assert "Quantum" in data["error"]

def test_reset():
    resp = client.post("/faults/reset")
    assert resp.status_code == 200
    assert resp.json()["status"] == "reset_successful"
