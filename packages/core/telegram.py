import logging
import re
from typing import Any

import httpx

from packages.core.config import settings

logger = logging.getLogger(__name__)


def format_telegram_escalation_message(
    incident_id: str,
    problem_summary: str,
    impact: str,
    exact_command: str,
    manual_steps: list[str] | None = None,
) -> str:
    """
    Formats the standard Markdown message for Telegram incident escalation.
    """
    steps = manual_steps or []
    if steps:
        formatted_steps_lines: list[str] = []
        for idx, step in enumerate(steps, start=1):
            cleaned = step.strip()
            # If the step already starts with a number like "1.", leave it as is
            if re.match(r"^\d+\.\s+", cleaned):
                formatted_steps_lines.append(cleaned)
            else:
                formatted_steps_lines.append(f"{idx}. {cleaned}")
        steps_text = "\n".join(formatted_steps_lines)
    else:
        steps_text = (
            "1. Review candidate runbook instructions.\n"
            "2. Execute the verified remediation command manually in the production cluster.\n"
            "3. Verify error rate and latency normalization in telemetry dashboards."
        )

    return (
        f"🚨 **INCIDENT ESCALATED: {incident_id}**\n"
        f"**Status:** `PROBLEM_ESCALATED_TO_HUMAN`\n"
        f"**Problem Summary:** {problem_summary}\n"
        f"**Impact & Severity:** {impact}\n\n"
        f"🛠️ **Exact Remediation Command:**\n"
        f"```bash\n"
        f"{exact_command.strip()}\n"
        f"```\n\n"
        f"📋 **Step-by-Step Manual Instructions:**\n"
        f"{steps_text}"
    )


def extract_manual_steps_from_runbook(content: str) -> list[str]:
    """
    Extracts ordered steps or bullet points from a markdown runbook chunk.
    """
    steps: list[str] = []
    lines = content.splitlines()
    for line in lines:
        stripped = line.strip()
        # Numbered list item
        match_num = re.match(r"^\d+\.\s+(.+)$", stripped)
        if match_num:
            steps.append(match_num.group(1).strip())
            continue
        # Bullet list item under Steps or Mitigation
        if stripped.startswith(("- ", "* ")):
            candidate = stripped[2:].strip()
            # Avoid picking up markdown headings or code fences as steps
            if not candidate.startswith("```") and not candidate.startswith("#"):
                steps.append(candidate)

    return steps


async def dispatch_telegram_escalation(
    incident_id: str,
    problem_summary: str,
    impact: str,
    exact_command: str,
    manual_steps: list[str] | None = None,
    bot_token: str | None = None,
    chat_id: str | None = None,
) -> dict[str, Any]:
    """
    Dispatches incident escalation details, verified command, and manual steps to Telegram.
    Fails safely in offline/test environments if bot token or chat ID is missing.
    """
    token = bot_token if bot_token is not None else settings.telegram_bot_token
    target_chat = chat_id if chat_id is not None else settings.telegram_chat_id

    formatted_message = format_telegram_escalation_message(
        incident_id=incident_id,
        problem_summary=problem_summary,
        impact=impact,
        exact_command=exact_command,
        manual_steps=manual_steps,
    )

    if not token or not target_chat:
        logger.warning(
            "Telegram bot token or chat ID is not configured. Emitting simulated mock dispatch for incident %s.",
            incident_id,
        )
        return {
            "status": "DISPATCHED_MOCK",
            "incident_id": incident_id,
            "chat_id": target_chat or "MOCK_CHAT",
            "message": formatted_message,
            "note": "Telegram bot token or chat ID missing. Mock dispatch recorded.",
        }

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": formatted_message,
        "parse_mode": "Markdown",
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            logger.info("Successfully dispatched Telegram escalation for incident %s", incident_id)
            return {
                "status": "DELIVERED",
                "incident_id": incident_id,
                "chat_id": target_chat,
                "message": formatted_message,
                "telegram_response": data,
            }
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to post message to Telegram API: %s", exc)
        return {
            "status": "FAILED_DELIVERY",
            "incident_id": incident_id,
            "chat_id": target_chat,
            "message": formatted_message,
            "error": str(exc),
        }
