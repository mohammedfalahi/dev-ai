from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.console.app import app
from evals.run_eval_matrix import EvaluationMatrixResult, MetricGate
from packages.contracts.ico import IncidentContextObject

client = TestClient(app)


@pytest.fixture
def mock_httpx_post():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        yield mock_post


@pytest.fixture
def mock_investigate():
    with patch(
        "apps.console.app.investigate_incident", new_callable=AsyncMock
    ) as mock_inv:
        yield mock_inv


@pytest.fixture
def sample_ico():
    return IncidentContextObject(
        incident_id="INC-TEST-001",
        headline="checkout-api returning 500s",
        impact="About 94 percent of requests failing",
        severity="SEV1",
        signals=[],
        hypothesis={
            "text": "Connection-pool exhaustion",
            "confidence": 0.9,
            "grounded_in": [],
        },
        candidate_runbooks=[],
    )


@pytest.fixture
def sample_matrix_result():
    return EvaluationMatrixResult(
        runbooks_count=20,
        chunks_count=129,
        total_eval_cases=21,
        evaluated_cases=3,
        tier1_retrieval_gates=[
            MetricGate("Recall @ 1", 1.0, 0.7, ">=", True, "100.0%", ">= 70.0%"),
            MetricGate("Recall @ 3", 1.0, 0.85, ">=", True, "100.0%", ">= 85.0%"),
            MetricGate("Recall @ 5", 1.0, 0.90, ">=", True, "100.0%", ">= 90.0%"),
        ],
        tier2_reranking_gates=[
            MetricGate("Mean Reciprocal Rank (MRR)", 1.0, 0.80, ">=", True, "1.0000", ">= 0.8000"),
            MetricGate("Refusal Precision", 1.0, 1.0, "==", True, "100.0%", "== 100.0%"),
            MetricGate("Hard Negatives at Rank 1", 0.0, 0.0, "==", True, "0", "== 0"),
        ],
        tier3_generation_gates=[
            MetricGate("Verbatim AST Match Rate", 1.0, 0.85, ">=", True, "100.0%", ">= 85.0%"),
            MetricGate("Forbidden Claim Violations", 0.0, 0.0, "==", True, "0.0%", "== 0.0%"),
            MetricGate("Refusal Accuracy", 1.0, 1.0, "==", True, "100.0%", "== 100.0%"),
            MetricGate("Overall Grounding Pass Rate", 1.0, 0.85, ">=", True, "100.0%", ">= 85.0%"),
        ],
        overall_passed=True,
    )


def test_get_operations_console_html():
    """Verify Dashboard 1 (Operations Console) serves static index.html."""
    response = client.get("/")
    assert response.status_code == 200
    assert "On-call Voice" in response.text
    assert "Operations & Chaos Console" in response.text
    assert "Chaos Injection" in response.text


def test_get_triage_forensics_html():
    """Verify Dashboard 2 (Triage & Evaluation Hub) serves static triage.html."""
    response = client.get("/triage")
    assert response.status_code == 200
    assert "On-call Voice" in response.text
    assert "Triage Forensics & Evaluation Hub" in response.text
    assert "3-Tier Production Evaluation Matrix" in response.text


def test_trigger_fault_returns_ico_and_starts_session(
    mock_httpx_post, mock_investigate, sample_ico
):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "incident_id": "INC-TEST-001",
        "severity": "SEV1",
        "service": "checkout-api",
        "error": "asyncpg.exceptions.TimeoutError or pool acquire timeout",
        "timestamp": "2026-09-24T12:00:00Z",
    }
    mock_resp.raise_for_status.return_value = None
    mock_httpx_post.return_value = mock_resp
    mock_investigate.return_value = sample_ico

    response = client.post("/api/faults/db-pool-exhaustion")
    assert response.status_code == 200

    data = response.json()
    assert "alert" in data
    assert "ico" in data
    assert "greeting" in data
    assert "We are tracking a SEV1 incident" in data["greeting"]
    assert data["ico"]["incident_id"] == "INC-TEST-001"
    assert "workflow_id" in data
    assert "dedupe" in data


def test_drill_trigger_and_status_endpoints(
    mock_httpx_post, mock_investigate, sample_ico
):
    """Verify POST /api/drill/trigger and GET /api/drill/status/{workflow_id}."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "incident_id": "INC-TEST-001",
        "severity": "SEV1",
        "service": "checkout-api",
        "error": "asyncpg.exceptions.TimeoutError",
        "timestamp": "2026-09-24T12:00:00Z",
    }
    mock_resp.raise_for_status.return_value = None
    mock_httpx_post.return_value = mock_resp
    mock_investigate.return_value = sample_ico

    trigger_resp = client.post("/api/drill/trigger", json={"fault": "db-pool-exhaustion"})
    assert trigger_resp.status_code == 200
    trigger_data = trigger_resp.json()

    assert trigger_data["status"] == "INVESTIGATED"
    assert "workflow-INC-TEST-001" in trigger_data["workflow_id"]
    assert trigger_data["incident_id"] == "INC-TEST-001"

    status_resp = client.get(f"/api/drill/status/{trigger_data['workflow_id']}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()

    assert status_data["call_status"] == "CONNECTED"
    assert status_data["status"] == "NOTIFYING"
    assert status_data["ico"]["incident_id"] == "INC-TEST-001"


def test_evals_latest_and_run_endpoints(sample_matrix_result):
    """Verify GET /api/evals/latest and POST /api/evals/run with mocked matrix runner."""
    with patch(
        "apps.console.app.run_eval_matrix", new_callable=AsyncMock
    ) as mock_eval_matrix:
        mock_eval_matrix.return_value = sample_matrix_result

        # Test latest evals
        latest_resp = client.get("/api/evals/latest")
        assert latest_resp.status_code == 200
        latest_data = latest_resp.json()
        assert latest_data["overall_passed"] is True
        assert len(latest_data["tier1_retrieval"]) == 3
        assert len(latest_data["tier2_reranking"]) == 3
        assert len(latest_data["tier3_generation"]) == 4

        # Test run evals
        run_resp = client.post("/api/evals/run")
        assert run_resp.status_code == 200
        run_data = run_resp.json()
        assert run_data["overall_passed"] is True
        assert run_data["system_overview"]["runbooks_count"] == 20


def test_chat_without_session_fails():
    # Since active_session is global, reset first
    client.post("/api/faults/reset")

    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 400
    assert "No active session" in response.json()["detail"]


def test_fault_resolve_and_status_endpoints():
    """Verify POST /api/faults/resolve transitions fault state to RESOLVED and GET /api/faults/status reflects it."""
    # Reset first
    client.post("/api/faults/reset")

    # Resolve active fault
    resp = client.post("/api/faults/resolve", json={"fault_id": "db-pool-exhaustion"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "RESOLVED"
    assert data["fault_id"] == "db-pool-exhaustion"
    assert data["fault_states"]["db-pool-exhaustion"] == "RESOLVED"

    # Status check
    status_resp = client.get("/api/faults/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["active_fault_status"] == "RESOLVED"
    assert status_data["fault_states"]["db-pool-exhaustion"] == "RESOLVED"


def test_fault_reset_with_fault_id():
    """Verify POST /api/faults/reset with fault_id payload resets target fault state to IDLE."""
    # Mark resolved first
    client.post("/api/faults/resolve", json={"fault_id": "db-pool-exhaustion"})

    # Reset with fault_id
    reset_resp = client.post("/api/faults/reset", json={"fault_id": "db-pool-exhaustion"})
    assert reset_resp.status_code == 200
    reset_data = reset_resp.json()
    assert reset_data["status"] == "RESET"
    assert reset_data["fault_states"]["db-pool-exhaustion"] == "IDLE"
