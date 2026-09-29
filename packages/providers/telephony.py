import logging
import re
import urllib.parse
import uuid
from typing import Protocol
from xml.sax.saxutils import escape

import httpx

from packages.contracts.telephony import DialRequest
from packages.core.config import settings

logger = logging.getLogger(__name__)

E164_REGEX = re.compile(r"^\+[1-9]\d{1,14}$")


class TelephonySecurityError(Exception):
    """Raised when a telephony call violates safety invariants."""


def normalize_e164(phone_number: str) -> str:
    """
    Validates and normalizes a phone number to standard E.164 format.
    Raises TelephonySecurityError if invalid.
    """
    cleaned = re.sub(r"[\s\-\(\)]", "", phone_number)
    if not E164_REGEX.match(cleaned):
        raise TelephonySecurityError(
            f"Destination {phone_number!r} is not a valid E.164 phone number."
        )
    return cleaned


def assert_telephony_safety(destination: str) -> None:
    """
    Enforces the Telephony Kill Switch and the Destination Allowlist.
    Raises TelephonySecurityError if a violation is detected.
    """
    if settings.telephony_kill_switch:
        raise TelephonySecurityError("Telephony kill switch is ENGAGED. All outbound calls are blocked.")

    norm_dest = normalize_e164(destination)
    if norm_dest not in settings.telephony_allowlist:
        raise TelephonySecurityError(
            f"Destination {norm_dest} is not in the authorized telephony allowlist."
        )


class TelephonyAdapter(Protocol):
    """Protocol for outbound telephony providers."""

    async def dial(
        self,
        request: DialRequest | str | None = None,
        *,
        destination: str | None = None,
        to_phone_number: str | None = None,
        incident_id: str | None = None,
        initial_brief: str | None = None,
        caller_id: str | None = None,
    ) -> str:
        """Initiate an outbound dial. Returns a unique call_id."""
        ...


def _resolve_dial_request(
    request: DialRequest | str | None = None,
    destination: str | None = None,
    to_phone_number: str | None = None,
    incident_id: str | None = None,
    initial_brief: str | None = None,
    caller_id: str | None = None,
) -> DialRequest:
    """Resolves a DialRequest from an instance, a raw phone number string, or keyword arguments."""
    if isinstance(request, DialRequest):
        return request
    if isinstance(request, str):
        return DialRequest(
            destination=request,
            incident_id=incident_id or "INC-MANUAL",
            initial_brief=initial_brief,
            caller_id=caller_id,
        )
    dest = to_phone_number or destination
    if not dest:
        raise ValueError(
            "A destination phone number ('destination' or 'to_phone_number') must be provided to dial()."
        )
    return DialRequest(
        destination=dest,
        incident_id=incident_id or "INC-MANUAL",
        initial_brief=initial_brief,
        caller_id=caller_id,
    )


class FakeTelephonyAdapter:
    """
    Deterministic fake telephony sink for testing and CI.
    Enforces all safety policies before logging and returning a simulated call ID.
    """

    def __init__(self) -> None:
        self.dispatched_calls: list[DialRequest] = []

    async def dial(
        self,
        request: DialRequest | str | None = None,
        *,
        destination: str | None = None,
        to_phone_number: str | None = None,
        incident_id: str | None = None,
        initial_brief: str | None = None,
        caller_id: str | None = None,
    ) -> str:
        req = _resolve_dial_request(
            request,
            destination=destination,
            to_phone_number=to_phone_number,
            incident_id=incident_id,
            initial_brief=initial_brief,
            caller_id=caller_id,
        )
        assert_telephony_safety(req.destination)
        call_id = f"fake-call-{uuid.uuid4()}"
        self.dispatched_calls.append(req)
        logger.info(
            f"[FakeTelephonyAdapter] Dial dispatched: call_id={call_id}, "
            f"incident_id={req.incident_id}, destination={req.destination}"
        )
        return call_id


class LiveKitSipAdapter:
    """
    Outbound SIP Trunking adapter using LiveKit Cloud SIP.
    Enforces safety policies before raising NotImplementedError for live execution.
    """

    async def dial(
        self,
        request: DialRequest | str | None = None,
        *,
        destination: str | None = None,
        to_phone_number: str | None = None,
        incident_id: str | None = None,
        initial_brief: str | None = None,
        caller_id: str | None = None,
    ) -> str:
        req = _resolve_dial_request(
            request,
            destination=destination,
            to_phone_number=to_phone_number,
            incident_id=incident_id,
            initial_brief=initial_brief,
            caller_id=caller_id,
        )
        assert_telephony_safety(req.destination)
        raise NotImplementedError("LiveKit SIP dialing is not yet implemented. Use FakeTelephonyAdapter.")


class TwilioVoiceAdapter:
    """
    Outbound Twilio Programmable Voice adapter.
    Enforces safety policies before dispatching calls.
    Supports real Twilio API dispatch when live credentials are set,
    or simulated call IDs when test credentials (e.g. ACtest...) are used.
    """

    def __init__(self) -> None:
        self.dispatched_calls: list[DialRequest] = []

    async def dial(
        self,
        request: DialRequest | str | None = None,
        *,
        destination: str | None = None,
        to_phone_number: str | None = None,
        incident_id: str | None = None,
        initial_brief: str | None = None,
        caller_id: str | None = None,
    ) -> str:
        req = _resolve_dial_request(
            request,
            destination=destination,
            to_phone_number=to_phone_number,
            incident_id=incident_id,
            initial_brief=initial_brief,
            caller_id=caller_id,
        )
        assert_telephony_safety(req.destination)
        if not settings.twilio_account_sid or not settings.twilio_auth_token:
            raise TelephonySecurityError(
                "Twilio Voice dialing requires TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN."
            )

        # In testing/simulated environments with ACtest credentials or no from_number
        if settings.twilio_account_sid.startswith("ACtest") or not settings.twilio_from_number:
            call_id = f"twilio-call-{uuid.uuid4()}"
            self.dispatched_calls.append(req)
            logger.info(
                f"[TwilioVoiceAdapter] Simulated test dial: call_id={call_id}, "
                f"incident_id={req.incident_id}, destination={req.destination}"
            )
            return call_id

        # Live Twilio REST API outbound dial via httpx
        brief = (
            req.initial_brief
            or f"This is an automated on-call emergency notification for incident {req.incident_id}."
        )
        escaped_brief = escape(brief)
        twiml = f"<Response><Say voice='alice'>{escaped_brief}</Say><Pause length='1'/></Response>"

        if settings.twilio_twiml_url:
            call_url = settings.twilio_twiml_url
        else:
            call_url = f"https://twimlets.com/echo?Twiml={urllib.parse.quote_plus(twiml)}"

        from_num = req.caller_id or settings.twilio_from_number
        url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Calls.json"
        data = {
            "To": req.destination,
            "From": from_num,
            "Url": call_url,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url,
                    data=data,
                    auth=(settings.twilio_account_sid, settings.twilio_auth_token),
                )
                if resp.status_code >= 400:
                    logger.error(
                        f"[TwilioVoiceAdapter] Twilio API call failed ({resp.status_code}): {resp.text}"
                    )
                    raise RuntimeError(f"Twilio API Error ({resp.status_code}): {resp.text}")

                resp_data = resp.json()
                call_id = resp_data.get("sid", f"twilio-call-{uuid.uuid4()}")
                self.dispatched_calls.append(req)
                logger.info(
                    f"[TwilioVoiceAdapter] Live call dispatched: call_id={call_id}, "
                    f"incident_id={req.incident_id}, destination={req.destination}"
                )
                return str(call_id)
        except Exception as exc:
            if isinstance(exc, (TelephonySecurityError, RuntimeError)):
                raise
            logger.error(f"[TwilioVoiceAdapter] Unexpected error placing Twilio call: {exc}")
            raise RuntimeError(f"Twilio call dispatch failed: {exc}") from exc


def get_telephony_adapter() -> TelephonyAdapter:
    """Factory to retrieve the configured telephony adapter."""
    mode = settings.telephony_mode.replace("_", "-").lower()
    if mode in ("fake", "livekit-rtc", "browser"):
        return FakeTelephonyAdapter()
    elif mode in ("livekit-sip",):
        return LiveKitSipAdapter()
    elif mode in ("twilio",):
        return TwilioVoiceAdapter()
    raise ValueError(f"Unknown telephony mode: {settings.telephony_mode}")

