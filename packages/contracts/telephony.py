from enum import StrEnum

from pydantic import BaseModel, Field


class TelephonyMode(StrEnum):
    FAKE = "fake"
    LIVEKIT_RTC = "livekit-rtc"
    BROWSER = "browser"
    TWILIO = "twilio"
    LIVEKIT_SIP = "livekit-sip"


class CallOutcomeType(StrEnum):
    HUMAN_ANSWERED = "human_answered"
    VOICEMAIL = "voicemail"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    ERROR = "error"


class DialRequest(BaseModel):
    model_config = {"populate_by_name": True}

    incident_id: str = Field(default="INC-MANUAL", description="ID of the incident triggering the call")
    destination: str = Field(..., alias="to_phone_number", description="Target phone number in E.164 format")
    caller_id: str | None = Field(default=None, description="Outbound CLI/caller ID number")
    initial_brief: str | None = Field(default=None, description="Initial spoken brief or message")


class CallOutcomeEvent(BaseModel):
    call_id: str = Field(..., description="Unique provider ID for the call")
    incident_id: str = Field(..., description="ID of the related incident")
    outcome: CallOutcomeType = Field(..., description="Detected call completion or pickup outcome")
    duration_seconds: float = Field(default=0.0, description="Duration of the call in seconds")
    error_message: str | None = Field(default=None, description="Error reason if call failed")
