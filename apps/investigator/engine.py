import asyncio
import os
from typing import Any

from google import genai
from google.genai import types

from packages.contracts.ico import IncidentContextObject
from packages.core.config import settings
from packages.knowledge.hybrid_search import search_runbooks


async def investigate_incident(
    raw_alert: dict[str, Any], db_conn_str: str | None = None
) -> IncidentContextObject:
    """
    Investigates a raw alert by querying the hybrid knowledge vault and reasoning over
    the evidence using the configured LLM to output a validated IncidentContextObject.
    """
    if db_conn_str:
        os.environ["DATABASE_URL"] = db_conn_str

    service = raw_alert.get("service", "unknown-service")
    primary_error = raw_alert.get("error", "Unknown error")
    incident_id = raw_alert.get("incident_id", "INC-UNKNOWN")
    severity = raw_alert.get("severity", "SEV1")

    # 1. Retrieval
    try:
        # Run synchronous db/model search in a thread pool to avoid blocking the event loop
        retrieved_chunks = await asyncio.to_thread(search_runbooks, primary_error, 3)
    except Exception:
        retrieved_chunks = []

    # Format retrieval context for the LLM
    runbook_context = ""
    if retrieved_chunks:
        for i, chunk in enumerate(retrieved_chunks, 1):
            runbook_context += f"--- RUNBOOK CHUNK {i} ---\n"
            runbook_context += f"Runbook ID: {chunk.runbook_id}\n"
            runbook_context += f"Chunk ID: {chunk.chunk_id}\n"
            runbook_context += f"Service: {chunk.service}\n"
            runbook_context += f"Content:\n{chunk.content}\n\n"
    else:
        runbook_context = (
            "No verified runbooks found. (Refusal gate triggered or search empty)."
        )

    # 2. Reasoning via Gemini structured outputs
    prompt = f"""
    You are the Investigator (slow brain) for the On-call Voice system.
    Analyze the following raw alert and retrieved runbook chunks to generate an IncidentContextObject.

    GROUNDING CONTRACT:
    - Classify telemetry as 'observed'.
    - Reference retrieved chunks as 'retrieved' (cite chunk_id and runbook_id).
    - Formulate a root-cause 'hypothesis' with calibrated confidence (0.0 to 1.0) grounded in evidence.
    - If no runbooks match or hybrid search returns empty, flag candidate_runbooks as empty and record the incident as unverified/undocumented in the hypothesis.
    - Do not invent runbooks or commands.

    RAW ALERT:
    {raw_alert}
    
    RETRIEVED RUNBOOKS:
    {runbook_context}
    
    Please populate the IncidentContextObject. 
    - Set incident_id to "{incident_id}".
    - Set severity to "{severity}".
    - Similar past incidents and unknowns can be empty if no evidence exists.
    """

    client = genai.Client()
    response = client.models.generate_content(
        model=settings.investigator_llm_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=IncidentContextObject,
            temperature=0.1,
        ),
    )

    # 3. Validation
    if not response.text:
        raise ValueError("Model returned empty response text")
    ico = IncidentContextObject.model_validate_json(response.text)
    return ico
