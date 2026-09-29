from typing import Any

from temporalio import activity

from apps.investigator.engine import investigate_incident
from apps.voice.agent import VoiceAgentSession
from packages.contracts.ico import IncidentContextObject
from packages.contracts.telephony import DialRequest
from packages.core.config import settings
from packages.observability import scrub_sensitive_data, trace_span
from packages.policy.grounding_validator import GroundingValidator
from packages.providers.telephony import get_telephony_adapter


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
async def notify_oncall_activity(incident_id: str, ico_dict: dict[str, Any]) -> str:
    """
    Dispatches the alert, bootstraps the Voice Agent session with the precomputed ICO,
    and initiates the outbound call or sets up WebRTC session according to TelephonyMode.
    """
    with trace_span(
        name="activity:notify_oncall",
        as_type="tool",
        input={"incident_id": incident_id},
        metadata={"activity": "notify_oncall_activity"},
    ):
        ico = IncidentContextObject.model_validate(ico_dict)
        session = VoiceAgentSession(ico=ico)
        voice_brief = await session.get_initial_greeting()

        mode = settings.telephony_mode.replace("_", "-").lower()
        room_name = f"callops-{incident_id.lower()}"

        if mode in ("livekit-rtc", "browser"):
            status_msg = "SKIPPED_PSTN_RTC_READY"
            activity.logger.info(
                f"[notify_oncall_activity] Telephony mode '{settings.telephony_mode}' active. "
                f"PSTN dial bypassed; ready for LiveKit WebRTC connection. "
                f"Room: '{room_name}'. Connect via: https://agents-playground.livekit.io. "
                f"Brief: '{voice_brief}'"
            )
            return status_msg

        # Destination: use configured oncall_phone_number if set, else fallback simulation
        target_number = settings.oncall_phone_number or "+15555550100"
        adapter = get_telephony_adapter()
        request = DialRequest(
            incident_id=incident_id,
            destination=target_number,
            initial_brief=voice_brief,
        )
        call_id = await adapter.dial(request)
        activity.logger.info(
            f"Voice agent session bootstrapped for {incident_id}. "
            f"Brief: '{voice_brief}'. Call dispatched: call_id={call_id}"
        )
        return call_id


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
