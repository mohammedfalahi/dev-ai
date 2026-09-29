import pytest

from apps.orchestrator.activities import notify_oncall_activity
from packages.contracts.telephony import DialRequest
from packages.core.config import settings
from packages.providers.telephony import (
    FakeTelephonyAdapter,
    LiveKitSipAdapter,
    TelephonySecurityError,
    TwilioVoiceAdapter,
    assert_telephony_safety,
    get_telephony_adapter,
    normalize_e164,
)


def test_e164_normalization() -> None:
    # Valid E.164 formats
    assert normalize_e164("+15555550100") == "+15555550100"
    assert normalize_e164("+1 (555) 555-0100") == "+15555550100"
    assert normalize_e164("+44 20 7946 0991") == "+442079460991"

    # Invalid formats
    with pytest.raises(TelephonySecurityError, match="not a valid E.164"):
        normalize_e164("555-0100")

    with pytest.raises(TelephonySecurityError, match="not a valid E.164"):
        normalize_e164("15555550100")

    with pytest.raises(TelephonySecurityError, match="not a valid E.164"):
        normalize_e164("+0123456789")


def test_allowlist_enforcement(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telephony_allowlist", ["+15555550100"])
    monkeypatch.setattr(settings, "telephony_kill_switch", False)

    # Allowlisted number passes
    assert_telephony_safety("+15555550100")

    # Non-allowlisted number fails
    with pytest.raises(TelephonySecurityError, match="not in the authorized telephony allowlist"):
        assert_telephony_safety("+15555550199")


def test_kill_switch_enforcement(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telephony_allowlist", ["+15555550100"])
    monkeypatch.setattr(settings, "telephony_kill_switch", True)

    with pytest.raises(TelephonySecurityError, match="kill switch is ENGAGED"):
        assert_telephony_safety("+15555550100")


@pytest.mark.asyncio
async def test_fake_telephony_adapter_dial(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telephony_allowlist", ["+15555550100"])
    monkeypatch.setattr(settings, "telephony_kill_switch", False)

    adapter = FakeTelephonyAdapter()
    req = DialRequest(incident_id="INC-123", destination="+15555550100")
    call_id = await adapter.dial(req)

    assert call_id.startswith("fake-call-")
    assert len(adapter.dispatched_calls) == 1
    assert adapter.dispatched_calls[0].incident_id == "INC-123"


@pytest.mark.asyncio
async def test_livekit_sip_adapter_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telephony_allowlist", ["+15555550100"])
    monkeypatch.setattr(settings, "telephony_kill_switch", False)

    adapter = LiveKitSipAdapter()
    req = DialRequest(incident_id="INC-123", destination="+15555550100")

    with pytest.raises(NotImplementedError, match="LiveKit SIP dialing is not yet implemented"):
        await adapter.dial(req)


def test_telephony_adapter_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify factory returns appropriate adapter for each mode."""
    # fake mode
    monkeypatch.setattr(settings, "telephony_mode", "fake")
    assert isinstance(get_telephony_adapter(), FakeTelephonyAdapter)

    # livekit-rtc and browser modes return FakeTelephonyAdapter
    monkeypatch.setattr(settings, "telephony_mode", "livekit-rtc")
    assert isinstance(get_telephony_adapter(), FakeTelephonyAdapter)

    monkeypatch.setattr(settings, "telephony_mode", "browser")
    assert isinstance(get_telephony_adapter(), FakeTelephonyAdapter)

    # livekit-sip modes
    monkeypatch.setattr(settings, "telephony_mode", "livekit-sip")
    assert isinstance(get_telephony_adapter(), LiveKitSipAdapter)

    monkeypatch.setattr(settings, "telephony_mode", "livekit_sip")
    assert isinstance(get_telephony_adapter(), LiveKitSipAdapter)

    # twilio mode
    monkeypatch.setattr(settings, "telephony_mode", "twilio")
    assert isinstance(get_telephony_adapter(), TwilioVoiceAdapter)

    # unknown mode raises ValueError
    monkeypatch.setattr(settings, "telephony_mode", "unsupported-mode")
    with pytest.raises(ValueError, match="Unknown telephony mode"):
        get_telephony_adapter()


@pytest.mark.asyncio
async def test_twilio_voice_adapter_safety_and_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify TwilioVoiceAdapter enforces allowlist and credential checks."""
    monkeypatch.setattr(settings, "telephony_allowlist", ["+15555550100"])
    monkeypatch.setattr(settings, "telephony_kill_switch", False)
    adapter = TwilioVoiceAdapter()

    # Fails if destination not allowlisted
    with pytest.raises(TelephonySecurityError, match="not in the authorized telephony allowlist"):
        await adapter.dial(DialRequest(incident_id="INC-1", destination="+15555550199"))

    # Fails if credentials missing
    monkeypatch.setattr(settings, "twilio_account_sid", None)
    monkeypatch.setattr(settings, "twilio_auth_token", None)
    with pytest.raises(TelephonySecurityError, match="requires TWILIO_ACCOUNT_SID"):
        await adapter.dial(DialRequest(incident_id="INC-1", destination="+15555550100"))

    # Succeeds when allowlisted and credentials set
    monkeypatch.setattr(settings, "twilio_account_sid", "ACtest123")
    monkeypatch.setattr(settings, "twilio_auth_token", "secret123")
    call_id = await adapter.dial(DialRequest(incident_id="INC-1", destination="+15555550100"))
    assert call_id.startswith("twilio-call-")
    assert len(adapter.dispatched_calls) == 1


@pytest.mark.asyncio
async def test_notify_oncall_activity_livekit_rtc(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify notify_oncall_activity skips PSTN dialing and returns SKIPPED_PSTN_RTC_READY in livekit-rtc mode."""
    monkeypatch.setattr(settings, "telephony_mode", "livekit-rtc")
    sample_ico_dict = {
        "incident_id": "INC-RTC-001",
        "headline": "checkout-api 500s",
        "impact": "checkout degraded",
        "severity": "SEV1",
        "signals": [],
        "hypothesis": {"text": "pool exhaustion", "confidence": 0.9, "grounded_in": []},
        "candidate_runbooks": [],
    }

    result = await notify_oncall_activity("INC-RTC-001", sample_ico_dict)
    assert result == "SKIPPED_PSTN_RTC_READY"


@pytest.mark.asyncio
async def test_notify_oncall_activity_fake_dial(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify notify_oncall_activity dispatches dial in fake mode."""
    monkeypatch.setattr(settings, "telephony_mode", "fake")
    monkeypatch.setattr(settings, "oncall_phone_number", "+15555550100")
    monkeypatch.setattr(settings, "telephony_allowlist", ["+15555550100"])
    monkeypatch.setattr(settings, "telephony_kill_switch", False)

    sample_ico_dict = {
        "incident_id": "INC-FAKE-001",
        "headline": "checkout-api 500s",
        "impact": "checkout degraded",
        "severity": "SEV1",
        "signals": [],
        "hypothesis": {"text": "pool exhaustion", "confidence": 0.9, "grounded_in": []},
        "candidate_runbooks": [],
    }

    result = await notify_oncall_activity("INC-FAKE-001", sample_ico_dict)
    assert result.startswith("fake-call-")

