import hashlib
import hmac
import time
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from apps.gateway import app as gateway_module
from apps.gateway.app import app, verify_signature
from apps.gateway.dedupe import (
    compute_fingerprint,
    deduplicator,
    evaluate_severity_policy,
)
from packages.contracts.alert import NormalizedAlert, PagingDecision
from packages.core.config import settings

client = TestClient(app)


def make_hmac_headers(body_bytes: bytes, secret: str = settings.hmac_secret, timestamp: int | None = None) -> dict[str, str]:
    ts = str(timestamp or int(time.time()))
    msg = f"{ts}.".encode() + body_bytes
    sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return {
        "X-Signature-256": sig,
        "X-Timestamp": ts,
    }


@pytest.fixture(autouse=True)
def reset_dedup():
    deduplicator.reset()
    gateway_module.workflow_dispatcher = None
    yield
    deduplicator.reset()
    gateway_module.workflow_dispatcher = None


def test_signature_verification():
    """Test 1: Verify valid HMAC succeeds, tampered body and stale timestamps fail."""
    body = b'{"hello": "world"}'
    
    # Valid signature
    headers = make_hmac_headers(body)
    assert verify_signature(body, headers["X-Signature-256"], headers["X-Timestamp"]) is True

    # Tampered body
    tampered_body = b'{"hello": "attacker"}'
    assert verify_signature(tampered_body, headers["X-Signature-256"], headers["X-Timestamp"]) is False

    # Stale timestamp (> 300 seconds ago)
    stale_ts = int(time.time()) - 350
    stale_headers = make_hmac_headers(body, timestamp=stale_ts)
    assert verify_signature(body, stale_headers["X-Signature-256"], stale_headers["X-Timestamp"]) is False


def test_fingerprint_stability():
    """Test 2: Volatile fields (delivery_id, observed_at, description) do not change fingerprint."""
    alert1 = NormalizedAlert(
        delivery_id="del-001",
        source="prometheus",
        service="checkout-api",
        environment="production",
        alert_rule="PostgresConnectionPoolExhausted",
        severity="critical",
        headline="Pool capacity exceeded",
        description="Error at 12:00:01 with request-id req-abc-123",
        dimensions={"cluster": "us-east-1", "pool": "primary"},
        observed_at="2026-09-24T12:00:01Z",
    )

    alert2 = NormalizedAlert(
        delivery_id="del-002",
        source="prometheus",
        service="checkout-api",
        environment="production",
        alert_rule="PostgresConnectionPoolExhausted",
        severity="critical",
        headline="Pool capacity exceeded",
        description="Error at 12:00:45 with request-id req-xyz-999 (completely different log)",
        dimensions={"pool": "primary", "cluster": "us-east-1"},  # reordered dict keys
        observed_at="2026-09-24T12:00:45Z",
    )

    fp1 = compute_fingerprint(alert1)
    fp2 = compute_fingerprint(alert2)

    assert fp1 == fp2, "Fingerprint must be stable across volatile fields and dimension orderings"

    # Distinct service must produce distinct fingerprint
    alert_different = alert1.model_copy(update={"service": "payment-api"})
    assert compute_fingerprint(alert_different) != fp1


def test_severity_policy():
    """Test 3: Severity decision matrix maps correctly to voice_page, message_only, and suppress."""
    # Critical in production -> VOICE_PAGE
    prod_critical = NormalizedAlert(
        delivery_id="1", source="prom", service="checkout", environment="production",
        alert_rule="R", severity="critical", headline="H", observed_at="2026-09-24T12:00:00Z"
    )
    decision, sev = evaluate_severity_policy(prod_critical)
    assert decision == PagingDecision.VOICE_PAGE
    assert sev == "SEV1"

    # Critical in staging -> Downgraded to MESSAGE_ONLY
    staging_critical = prod_critical.model_copy(update={"environment": "staging"})
    decision, sev = evaluate_severity_policy(staging_critical)
    assert decision == PagingDecision.MESSAGE_ONLY

    # Warning -> MESSAGE_ONLY
    warning_alert = prod_critical.model_copy(update={"severity": "warning"})
    decision, sev = evaluate_severity_policy(warning_alert)
    assert decision == PagingDecision.MESSAGE_ONLY
    assert sev == "SEV2"

    # Info -> SUPPRESS
    info_alert = prod_critical.model_copy(update={"severity": "info"})
    decision, sev = evaluate_severity_policy(info_alert)
    assert decision == PagingDecision.SUPPRESS
    assert sev == "SEV3"


def test_alert_storm_collapses_50_alerts_to_one_incident():
    """Test 4: Canonical Alert Storm Gate — 50 duplicate alerts collapse into exactly 1 incident."""
    mock_dispatcher = AsyncMock(return_value=True)
    gateway_module.workflow_dispatcher = mock_dispatcher

    incident_ids = set()
    alert_counts = []
    dispatched_flags = []

    # Simulate 50 incoming alerts from Prometheus over 30 seconds
    for i in range(50):
        alert_data = {
            "delivery_id": f"prom-alert-{i:03d}",
            "source": "prometheus",
            "service": "checkout-api",
            "environment": "production",
            "alert_rule": "PostgresPoolExhausted",
            "severity": "critical",
            "headline": "PostgreSQL connection pool exhausted",
            "description": f"Worker pod worker-{i%5} failed to acquire connection in 5000ms",
            "dimensions": {"database": "checkout_db", "datacenter": "us-east-1"},
            "observed_at": f"2026-09-24T12:00:{i:02d}Z",
        }

        # Send via API using test signature bypass header for speed
        resp = client.post(
            "/api/v1/alerts",
            json=alert_data,
            headers={"X-Test-Bypass-Signature": "true"},
        )
        assert resp.status_code == 200, f"Alert {i} failed: {resp.text}"
        data = resp.json()

        incident_ids.add(data["incident_id"])
        alert_counts.append(data["alert_count"])
        dispatched_flags.append(data["workflow_dispatched"])

    # 1. Exactly one incident created across all 50 alerts
    assert len(incident_ids) == 1, f"Expected 1 grouped incident, got {len(incident_ids)}"

    # 2. Alert counter steadily grew to 50
    assert alert_counts[0] == 1
    assert alert_counts[-1] == 50

    # 3. Only the first alert triggered a workflow start intent
    assert dispatched_flags[0] is True
    assert all(flag is False for flag in dispatched_flags[1:])

    # 4. Mock dispatcher was invoked exactly once with the unified incident
    assert mock_dispatcher.call_count == 1
    dispatched_payload = mock_dispatcher.call_args[0][0]
    assert dispatched_payload["incident_id"] == next(iter(incident_ids))
    assert dispatched_payload["severity"] == "SEV1"
    assert dispatched_payload["service"] == "checkout-api"


def test_exact_delivery_id_idempotency():
    """Test 5: Replayed delivery ID is recognized and does not increment alert count."""
    alert = NormalizedAlert(
        delivery_id="dup-delivery-001",
        source="prometheus",
        service="checkout-api",
        environment="production",
        alert_rule="HighLatency",
        severity="warning",
        headline="P99 latency > 2s",
        observed_at="2026-09-24T12:00:00Z",
    )

    # First delivery
    inc1, is_new1, is_dup1 = deduplicator.process_alert(alert)
    assert is_new1 is True
    assert is_dup1 is False
    assert inc1.alert_count == 1

    # Immediate redelivery with identical delivery_id
    inc2, is_new2, is_dup2 = deduplicator.process_alert(alert)
    assert is_new2 is False
    assert is_dup2 is True
    assert inc2.alert_count == 1  # Not incremented on duplicate delivery
