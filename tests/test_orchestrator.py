import asyncio

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from apps.orchestrator.workflow import IncidentLifecycleWorkflow

# We mock the actual activity implementations so they don't hit the DB or LLM during workflow tests.
# This validates the state machine purely.


@activity.defn(name="investigate_incident_activity")
async def mock_investigate_incident_activity(raw_alert: dict) -> dict:
    return {
        "incident_id": raw_alert.get("incident_id", "TEST"),
        "headline": "Test",
        "impact": "Test",
        "severity": "SEV1",
        "signals": [],
        "hypothesis": {"text": "Test", "confidence": 0.9, "grounded_in": []},
        "candidate_runbooks": [],
        "similar_past_incidents": [],
        "unknowns": [],
        "tool_errors": [],
        "schema_version": "1.0",
        "investigation_status": "complete",
    }


@activity.defn(name="validate_grounding_activity")
async def mock_validate_grounding_activity(ico_dict: dict) -> bool:
    return True


@activity.defn(name="notify_oncall_activity")
async def mock_notify_oncall_activity(incident_id: str, ico_dict: dict) -> None:
    pass


@activity.defn(name="dispatch_escalation_activity")
async def mock_dispatch_escalation_activity(
    incident_id: str, escalation_level: int, reason: str
) -> None:
    pass


@pytest.fixture
def activities():
    return [
        mock_investigate_incident_activity,
        mock_validate_grounding_activity,
        mock_notify_oncall_activity,
        mock_dispatch_escalation_activity,
    ]


@pytest.mark.asyncio
async def test_workflow_happy_path(activities):
    """Test 1: Happy path where triage completes and signal acknowledges incident before timeout."""
    async with await WorkflowEnvironment.start_time_skipping() as env, Worker(
        env.client,
        task_queue="test-task-queue",
        workflows=[IncidentLifecycleWorkflow],
        activities=activities,
    ):
        # Start workflow
        handle = await env.client.start_workflow(
            IncidentLifecycleWorkflow.run,
            {"incident_id": "INC-100"},
            id="incident-workflow-INC-100",
            task_queue="test-task-queue",
        )

        # Wait for workflow to reach AWAITING_ACK state
        # In time-skipping env, it runs as fast as possible until it hits a timer.
        for _ in range(10):
            status = await handle.query(IncidentLifecycleWorkflow.get_status)
            if status["status"] == "AWAITING_ACK":
                break
            await asyncio.sleep(0.1)

        assert status["status"] == "AWAITING_ACK"

        # Send signal
        await handle.signal(
            IncidentLifecycleWorkflow.acknowledge_incident, "eng-123"
        )

        # Workflow should complete
        result = await handle.result()

        assert result["result"] == "Acknowledged"

        # Check final status
        status = await handle.query(IncidentLifecycleWorkflow.get_status)
        assert status["status"] == "ACKNOWLEDGED"
        assert status["acknowledged_by"] == "eng-123"


@pytest.mark.asyncio
async def test_workflow_escalation_timeout(activities):
    """Test 2: Timeout path where missing acknowledgment triggers the escalation activity."""
    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="test-task-queue-timeout",
            workflows=[IncidentLifecycleWorkflow],
            activities=activities,
        ),
    ):
        handle = await env.client.start_workflow(
            IncidentLifecycleWorkflow.run,
            {"incident_id": "INC-200"},
            id="incident-workflow-INC-200",
            task_queue="test-task-queue-timeout",
        )

        # Do NOT send signal. Instead, advance time to force the timeout.
        # The time-skipping environment automatically advances time if we wait for the result.
        result = await handle.result()

        assert result["result"] == "Escalated"

        status = await handle.query(IncidentLifecycleWorkflow.get_status)
        assert status["status"] == "ESCALATED"
