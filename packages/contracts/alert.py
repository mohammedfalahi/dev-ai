from enum import Enum

from pydantic import BaseModel, Field


class PagingDecision(str, Enum):
    VOICE_PAGE = "voice_page"
    MESSAGE_ONLY = "message_only"
    SUPPRESS = "suppress"


class NormalizedAlert(BaseModel):
    """
    Standardized alert contract across all monitoring and error tracking providers.
    Enforces clean separation between provider-specific JSON and system core.
    """
    delivery_id: str = Field(description="Unique delivery ID from provider for exact idempotency")
    source: str = Field(description="Source provider, e.g. prometheus, sentry, broken-shop")
    service: str = Field(description="Affected microservice name")
    environment: str = Field(default="production", description="Runtime environment")
    alert_rule: str = Field(description="Name of the triggering alert rule")
    severity: str = Field(description="Alert severity, e.g. critical, warning, info, SEV1")
    headline: str = Field(description="Brief description of the alert")
    description: str = Field(default="", description="Full alert details or logs")
    dimensions: dict[str, str] = Field(default_factory=dict, description="Stable dimensions/labels")
    observed_at: str = Field(description="ISO timestamp when alert was observed at source")


class IncidentRecord(BaseModel):
    """
    An active grouped incident aggregating one or more related alerts.
    """
    incident_id: str
    fingerprint: str
    fingerprint_version: int = 1
    severity: str
    decision: PagingDecision
    service: str
    environment: str
    headline: str
    opened_at: str
    last_seen_at: str
    alert_count: int = 1
    alerts: list[NormalizedAlert] = Field(default_factory=list)
