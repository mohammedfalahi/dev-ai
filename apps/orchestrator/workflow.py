import asyncio
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from apps.orchestrator.activities import (
        investigate_incident_activity,
        validate_grounding_activity,
        notify_oncall_activity,
        dispatch_escalation_activity,
    )


@workflow.defn
class IncidentLifecycleWorkflow:
    def __init__(self) -> None:
        self._status = "PENDING"
        self._acknowledged_by: str | None = None
        self._is_acknowledged = False

    @workflow.signal
    async def acknowledge_incident(self, engineer_id: str) -> None:
        """
        Signal received when an on-call engineer picks up the phone
        or hits an API button acknowledging the incident.
        """
        self._is_acknowledged = True
        self._acknowledged_by = engineer_id
        self._status = "ACKNOWLEDGED"

    @workflow.query
    def get_status(self) -> dict[str, Any]:
        """
        Exposes the current state of the workflow deterministically.
        """
        return {
            "status": self._status,
            "acknowledged_by": self._acknowledged_by,
        }

    @workflow.run
    async def run(self, raw_alert: dict[str, Any]) -> dict[str, Any]:
        incident_id = raw_alert.get("incident_id", "UNKNOWN")
        self._status = "INVESTIGATING"

        # Step 1: Investigate (Slow Brain)
        try:
            ico_dict = await workflow.execute_activity(
                investigate_incident_activity,
                raw_alert,
                start_to_close_timeout=timedelta(seconds=60),
            )
        except Exception as e:
            self._status = "FAILED_INVESTIGATION"
            raise ApplicationError(f"Investigation failed: {e}") from e

        # Step 2: Validate Grounding Policy
        self._status = "VALIDATING"
        is_valid = await workflow.execute_activity(
            validate_grounding_activity,
            ico_dict,
            start_to_close_timeout=timedelta(seconds=10),
        )

        if not is_valid:
            self._status = "FAILED_VALIDATION"
            return {"result": "Validation failed - grounding constraints violated"}

        # Step 3: Notify the On-call Engineer
        self._status = "NOTIFYING"
        await workflow.execute_activity(
            notify_oncall_activity,
            args=[incident_id, ico_dict],
            start_to_close_timeout=timedelta(seconds=10),
        )

        # Step 4: Wait for Acknowledgment with Timer
        self._status = "AWAITING_ACK"
        try:
            # We wait up to 90 seconds for the engineer to signal `acknowledge_incident`
            await workflow.wait_condition(
                lambda: self._is_acknowledged,
                timeout=timedelta(seconds=90),
            )
        except asyncio.TimeoutError:
            # Escalation Ladder
            self._status = "ESCALATING"
            await workflow.execute_activity(
                dispatch_escalation_activity,
                args=[incident_id, 2, "Timeout awaiting acknowledgment"],
                start_to_close_timeout=timedelta(seconds=10),
            )
            self._status = "ESCALATED"
            return {"result": "Escalated"}

        return {"result": "Acknowledged"}
