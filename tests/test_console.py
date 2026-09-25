from unittest.mock import AsyncMock, patch

# We will patch httpx.AsyncClient so it doesn't try to hit localhost:8081 over the network.
# But actually, httpx.AsyncClient supports ASGITransport to mock apps directly! Let's just use unittest.mock.
import pytest
from fastapi.testclient import TestClient

from apps.console.app import app
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


def test_trigger_fault_returns_ico_and_starts_session(
    mock_httpx_post, mock_investigate
):
    # Mock broken shop response
    from unittest.mock import MagicMock

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

    # Mock investigator response
    mock_ico = IncidentContextObject(
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
    mock_investigate.return_value = mock_ico

    # Call the endpoint
    response = client.post("/api/faults/db-pool-exhaustion")
    assert response.status_code == 200

    data = response.json()
    assert "alert" in data
    assert "ico" in data
    assert "greeting" in data
    assert "We are tracking a SEV1 incident" in data["greeting"]
    assert data["ico"]["incident_id"] == "INC-TEST-001"


def test_chat_without_session_fails():
    # Since active_session is global, we need to make sure it's reset
    client.post("/api/faults/reset")

    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 400
    assert "No active session" in response.json()["detail"]
