from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from packages.core.config import settings
from packages.core.telegram import (
    dispatch_telegram_escalation,
    extract_manual_steps_from_runbook,
    format_telegram_escalation_message,
)


def test_telegram_config_properties():
    """Verify telegram_bot_token and uppercase properties in Settings."""
    assert hasattr(settings, "telegram_bot_token")
    assert hasattr(settings, "telegram_chat_id")
    assert hasattr(settings, "TELEGRAM_BOT_TOKEN")
    assert hasattr(settings, "TELEGRAM_CHAT_ID")
    assert settings.TELEGRAM_BOT_TOKEN == settings.telegram_bot_token
    assert settings.TELEGRAM_CHAT_ID == settings.telegram_chat_id


def test_format_telegram_escalation_message():
    """Verify Markdown escalation template meets strict spec."""
    msg = format_telegram_escalation_message(
        incident_id="INC-999",
        problem_summary="Postgres pool exhausted on checkout-api",
        impact="94% 500 error rate (Severity: SEV1)",
        exact_command="kubectl rollout restart deployment/checkout-api",
        manual_steps=[
            "Check pod logs: kubectl logs -l app=checkout-api",
            "Execute rollout restart command",
            "Monitor latency return to p95 < 200ms",
        ],
    )

    assert "🚨 **INCIDENT ESCALATED: INC-999**" in msg
    assert "**Status:** `PROBLEM_ESCALATED_TO_HUMAN`" in msg
    assert "**Problem Summary:** Postgres pool exhausted on checkout-api" in msg
    assert "**Impact & Severity:** 94% 500 error rate (Severity: SEV1)" in msg
    assert "🛠️ **Exact Remediation Command:**" in msg
    assert "```bash\nkubectl rollout restart deployment/checkout-api\n```" in msg
    assert "📋 **Step-by-Step Manual Instructions:**" in msg
    assert "1. Check pod logs: kubectl logs -l app=checkout-api" in msg
    assert "2. Execute rollout restart command" in msg
    assert "3. Monitor latency return to p95 < 200ms" in msg


def test_extract_manual_steps_from_runbook():
    """Verify step extraction from markdown numbered and bullet lists."""
    sample_content = """
    # Runbook: DB Connection Pool Exhaustion

    ## Mitigation Steps
    1. Check active database connections in RDS.
    2. Restart deployment using:
    ```bash
    kubectl rollout restart deployment/checkout-api
    ```
    3. Verify connection pool releases.
    - Check Grafana pool metrics
    - Confirm 500 errors drop to 0
    """

    steps = extract_manual_steps_from_runbook(sample_content)
    assert len(steps) >= 3
    assert "Check active database connections in RDS." in steps[0]
    assert "Restart deployment using:" in steps[1]
    assert "Verify connection pool releases." in steps[2]


@pytest.mark.asyncio
async def test_dispatch_telegram_mock_when_credentials_missing():
    """Verify graceful mock dispatch when bot token or chat ID is empty."""
    res = await dispatch_telegram_escalation(
        incident_id="INC-888",
        problem_summary="Connection pool saturated",
        impact="Service degraded",
        exact_command="kubectl rollout restart deploy/checkout-api",
        bot_token="",
        chat_id="",
    )

    assert res["status"] == "DISPATCHED_MOCK"
    assert res["incident_id"] == "INC-888"
    assert "PROBLEM_ESCALATED_TO_HUMAN" in res["message"]


@pytest.mark.asyncio
async def test_dispatch_telegram_delivers_via_httpx():
    """Verify HTTP POST to Telegram Bot API when credentials are provided."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 12345}}
        mock_post.return_value = mock_resp

        res = await dispatch_telegram_escalation(
            incident_id="INC-777",
            problem_summary="Connection pool saturated",
            impact="Service degraded",
            exact_command="kubectl rollout restart deploy/checkout-api",
            bot_token="test-bot-token",
            chat_id="12345678",
        )

        assert res["status"] == "DELIVERED"
        assert res["incident_id"] == "INC-777"
        assert res["chat_id"] == "12345678"
        mock_post.assert_awaited_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://api.telegram.org/bottest-bot-token/sendMessage"
        assert kwargs["json"]["chat_id"] == "12345678"
        assert kwargs["json"]["parse_mode"] == "Markdown"
        assert "PROBLEM_ESCALATED_TO_HUMAN" in kwargs["json"]["text"]
