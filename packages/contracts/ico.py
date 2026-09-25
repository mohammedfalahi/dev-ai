from typing import Any
from pydantic import BaseModel, Field

from packages.contracts.incident import Signal, Hypothesis, CandidateRunbook


class IncidentContextObject(BaseModel):
    """
    The compact validated brief passed from Investigator to Voice Agent.
    Strictly follows .context/architecture.md guidelines.
    """

    schema_version: str = "1.0"
    incident_id: str
    generated_at: str | None = None
    investigation_status: str = "complete"

    headline: str = Field(max_length=120)
    impact: str
    severity: str
    service: str = ""

    signals: list[Signal]
    hypothesis: Hypothesis
    candidate_runbooks: list[CandidateRunbook]

    similar_past_incidents: list[dict[str, Any]] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    tool_errors: list[str] = Field(default_factory=list)
    expires_at: str | None = None

    def to_voice_brief(self) -> str:
        """
        Returns a concise, 2-sentence conversational spoken summary formatted
        for streaming TTS. Avoids raw markdown, backticks, or JSON.
        """
        # Remove any Markdown or technical formatting that TTS might stumble on.
        clean_headline = self.headline.replace("`", "").strip()
        clean_impact = self.impact.replace("`", "").replace("~", "About ").strip()
        clean_hypothesis = self.hypothesis.text.replace("`", "").strip()

        # Ensure punctuation for sentence boundaries.
        if not clean_headline.endswith("."):
            clean_headline += "."
        if not clean_impact.endswith("."):
            clean_impact += "."
        if not clean_hypothesis.endswith("."):
            clean_hypothesis += "."

        return (
            f"We are tracking a {self.severity} incident: {clean_headline} "
            f"{clean_impact} The leading hypothesis is {clean_hypothesis}"
        )
