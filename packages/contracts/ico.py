from typing import Any

from pydantic import BaseModel, Field

from packages.contracts.incident import CandidateRunbook, Hypothesis, Signal


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
    proposed_action: str | None = Field(
        default=None,
        description="The primary remediation or diagnostic CLI/SQL command grounded in retrieved candidate runbooks",
    )

    similar_past_incidents: list[dict[str, Any]] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    tool_errors: list[str] = Field(default_factory=list)
    expires_at: str | None = None

    def to_voice_brief(self) -> str:
        """
        Returns a natural, empathetic, and concise conversational spoken summary
        formatted for speech synthesis and audio delivery. Avoids raw markdown,
        backticks, or JSON formatting.
        """
        # Remove any Markdown or technical formatting that TTS might stumble on.
        clean_headline = self.headline.replace("`", "").strip().rstrip(".")
        clean_impact = self.impact.replace("`", "").replace("~", "About ").strip().rstrip(".")
        clean_hypothesis = self.hypothesis.text.replace("`", "").strip().rstrip(".")
        service_target = f" on {self.service}" if self.service else ""

        return (
            f"Hello, sorry to wake you up. We are tracking a {self.severity} incident"
            f"{service_target}: {clean_headline}. Specifically, {clean_impact}. "
            f"The leading hypothesis is {clean_hypothesis}. Would you like me to run the recommended remediation?"
        )
