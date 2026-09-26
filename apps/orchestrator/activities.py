from typing import Any
from temporalio import activity

from apps.investigator.engine import investigate_incident
from packages.contracts.ico import IncidentContextObject
from packages.policy.grounding_validator import GroundingValidator


@activity.defn
async def investigate_incident_activity(raw_alert: dict[str, Any]) -> dict[str, Any]:
    """
    Executes the slow-brain investigation to generate an ICO.
    """
    ico = await investigate_incident(raw_alert)
    # Return as a serialized dict so Temporal can transparently encode it
    return ico.model_dump(mode="json")


@activity.defn
async def validate_grounding_activity(ico_dict: dict[str, Any]) -> bool:
    """
    Validates that the ICO passes safety formatting boundaries.
    """
    ico = IncidentContextObject.model_validate(ico_dict)
    brief = ico.to_voice_brief()

    # We mainly want to ensure the generated voice brief doesn't contain markdown or json
    if not GroundingValidator.validate_voice_brief(brief, ico):
        return False

    return True


@activity.defn
async def notify_oncall_activity(incident_id: str, ico_dict: dict[str, Any]) -> None:
    """
    Simulates dispatching the alert and initiating the Voice Agent call.
    """
    # In a real setup, this would trigger Twilio/LiveKit SIP bridging.
    activity.logger.info(f"Notification dispatched for incident: {incident_id}")


@activity.defn
async def dispatch_escalation_activity(
    incident_id: str, escalation_level: int, reason: str
) -> None:
    """
    Dispatches an escalation step (e.g. paging the secondary on-call).
    """
    activity.logger.info(f"ESCALATION [{escalation_level}] for {incident_id}: {reason}")
