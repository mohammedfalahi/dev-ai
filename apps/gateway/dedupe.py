import hashlib
import threading
from datetime import UTC, datetime
from uuid import uuid4

from packages.contracts.alert import IncidentRecord, NormalizedAlert, PagingDecision
from packages.core.config import settings


def compute_fingerprint(alert: NormalizedAlert, version: int = 1) -> str:
    """
    Computes a deterministic SHA-256 fingerprint from stable alert dimensions.
    Volatile fields like delivery IDs, timestamps, and transient messages are explicitly excluded.
    """
    sorted_dims = sorted(f"{k}={v}" for k, v in alert.dimensions.items())
    dims_str = ",".join(sorted_dims)
    raw_key = f"v{version}:{alert.source}:{alert.environment.lower()}:{alert.service.lower()}:{alert.alert_rule.lower()}:{dims_str}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def evaluate_severity_policy(alert: NormalizedAlert) -> tuple[PagingDecision, str]:
    """
    Deterministic severity decision engine adhering to ADR-006.
    Maps raw source severity and environment context into a structured paging decision.
    """
    sev_upper = alert.severity.upper()
    env_lower = alert.environment.lower()

    # SEV1 / Critical: Triggers voice call only for production systems
    if sev_upper in ["CRITICAL", "SEV1", "P1", "FATAL", "EMERGENCY"]:
        if env_lower in ["prod", "production"]:
            return PagingDecision.VOICE_PAGE, "SEV1"
        return PagingDecision.MESSAGE_ONLY, "SEV1"

    # SEV2 / Warning: Slack / message-only notification
    if sev_upper in ["WARNING", "WARN", "SEV2", "P2"]:
        return PagingDecision.MESSAGE_ONLY, "SEV2"

    # SEV3 / Info: Suppressed from immediate paging
    return PagingDecision.SUPPRESS, "SEV3"


class AlertDeduplicator:
    """
    Thread-safe alert deduplicator and grouping engine.
    Enforces exact delivery ID idempotency and groups related alerts by fingerprint
    within a sliding time window.
    """

    def __init__(self, window_seconds: int | None = None):
        self.window_seconds = window_seconds or settings.grouping_window_seconds
        self._lock = threading.Lock()
        # Delivery ID -> incident_id (for exact idempotency)
        self._processed_deliveries: dict[str, str] = {}
        # Fingerprint -> IncidentRecord
        self._active_incidents: dict[str, IncidentRecord] = {}

    def process_alert(
        self, alert: NormalizedAlert
    ) -> tuple[IncidentRecord, bool, bool]:
        """
        Processes an incoming normalized alert.
        Returns:
            (incident_record, is_new_incident, is_duplicate_delivery)
        """
        with self._lock:
            # 1. Exact delivery ID idempotency check
            if alert.delivery_id in self._processed_deliveries:
                existing_incident_id = self._processed_deliveries[alert.delivery_id]
                for incident in self._active_incidents.values():
                    if incident.incident_id == existing_incident_id:
                        return incident, False, True
                # If incident aged out, still recognize as duplicate delivery
                now_iso = datetime.now(UTC).isoformat()
                fp = compute_fingerprint(alert)
                decision, normalized_sev = evaluate_severity_policy(alert)
                dummy = IncidentRecord(
                    incident_id=existing_incident_id,
                    fingerprint=fp,
                    severity=normalized_sev,
                    decision=decision,
                    service=alert.service,
                    environment=alert.environment,
                    headline=alert.headline,
                    opened_at=now_iso,
                    last_seen_at=now_iso,
                    alert_count=1,
                    alerts=[alert],
                )
                return dummy, False, True

            # 2. Compute fingerprint
            fp = compute_fingerprint(alert)
            now = datetime.now(UTC)
            now_iso = now.isoformat()

            # 3. Sliding time-window grouping check
            existing = self._active_incidents.get(fp)
            if existing:
                try:
                    last_seen = datetime.fromisoformat(existing.last_seen_at)
                    diff = (now - last_seen).total_seconds()
                except (ValueError, TypeError):
                    diff = 0

                if diff <= self.window_seconds:
                    # Within grouping window -> attach to existing incident
                    existing.last_seen_at = now_iso
                    existing.alert_count += 1
                    existing.alerts.append(alert)
                    self._processed_deliveries[alert.delivery_id] = existing.incident_id
                    return existing, False, False

            # 4. Outside window or first time seen -> create new IncidentRecord
            decision, normalized_sev = evaluate_severity_policy(alert)
            incident_id = f"INC-{uuid4().hex[:8].upper()}"
            new_incident = IncidentRecord(
                incident_id=incident_id,
                fingerprint=fp,
                severity=normalized_sev,
                decision=decision,
                service=alert.service,
                environment=alert.environment,
                headline=alert.headline,
                opened_at=now_iso,
                last_seen_at=now_iso,
                alert_count=1,
                alerts=[alert],
            )
            self._active_incidents[fp] = new_incident
            self._processed_deliveries[alert.delivery_id] = incident_id
            return new_incident, True, False

    def reset(self) -> None:
        """Clears all in-memory deduplication state."""
        with self._lock:
            self._processed_deliveries.clear()
            self._active_incidents.clear()


# Global singleton instance for the application
deduplicator = AlertDeduplicator()
