from typing import Any

from temporalio import activity

from apps.investigator.engine import investigate_incident
from packages.contracts.ico import IncidentContextObject
from packages.observability import scrub_sensitive_data, trace_span
from packages.policy.grounding_validator import GroundingValidator


@activity.defn
async def investigate_incident_activity(raw_alert: dict[str, Any]) -> dict[str, Any]:
    """
    Executes the slow-brain investigation to generate an ICO.
    """
    with trace_span(
        name="activity:investigate_incident",
        as_type="tool",
        input=scrub_sensitive_data(raw_alert),
        metadata={"activity": "investigate_incident_activity"},
    ) as span:
        ico = await investigate_incident(raw_alert)
        dump = ico.model_dump(mode="json")
        span.update(
            output={"incident_id": ico.incident_id, "status": ico.investigation_status}
        )
        return dump


@activity.defn
async def validate_grounding_activity(ico_dict: dict[str, Any]) -> bool:
    """
    Validates that the ICO passes safety formatting boundaries.
    """
    with trace_span(
        name="activity:validate_grounding",
        as_type="guardrail",
        input={"incident_id": ico_dict.get("incident_id")},
        metadata={"activity": "validate_grounding_activity"},
    ) as span:
        ico = IncidentContextObject.model_validate(ico_dict)
        brief = ico.to_voice_brief()

        # We mainly want to ensure the generated voice brief doesn't contain markdown or json
        is_valid = GroundingValidator.validate_voice_brief(brief, ico)
        span.update(output={"is_valid": is_valid, "brief_length": len(brief) if is_valid else 0})
        return is_valid


@activity.defn
async def notify_oncall_activity(incident_id: str, ico_dict: dict[str, Any]) -> None:
    """
    Simulates dispatching the alert and initiating the Voice Agent call.
    """
    with trace_span(
        name="activity:notify_oncall",
        as_type="tool",
        input={"incident_id": incident_id},
        metadata={"activity": "notify_oncall_activity"},
    ):
        # In a real setup, this would trigger Twilio/LiveKit SIP bridging.
        activity.logger.info(f"Notification dispatched for incident: {incident_id}")


@activity.defn
async def dispatch_escalation_activity(
    incident_id: str, escalation_level: int, reason: str
) -> None:
    """
    Dispatches an escalation step (e.g. paging the secondary on-call).
    """
    with trace_span(
        name="activity:dispatch_escalation",
        as_type="tool",
        input={
            "incident_id": incident_id,
            "escalation_level": escalation_level,
            "reason": reason,
        },
        metadata={"activity": "dispatch_escalation_activity"},
    ):
        activity.logger.info(
            f"ESCALATION [{escalation_level}] for {incident_id}: {reason}"
        )
