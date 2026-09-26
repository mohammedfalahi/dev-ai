from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

EvalCategory = Literal[
    "exact_error",
    "semantic_symptom",
    "hard_negative",
    "unanswerable_refusal",
    "adversarial_injection",
    "read_only_diagnostic",
]


class GoldenEvalCase(BaseModel):
    """
    Evaluation contract for measuring retrieval precision, refusal boundaries,
    and generation grounding across the CallOps incident corpus.
    """

    case_id: str = Field(
        description="Unique deterministic case identifier (e.g. EVAL-PG-EXACT-001)"
    )
    category: EvalCategory = Field(description="Evaluation taxonomy category")
    service: str | None = Field(
        default=None, description="Target service identifier, if known"
    )
    incident_query: str = Field(
        description="Raw query, error message, or diagnostic question"
    )
    expected_runbook_id: str | None = Field(
        default=None,
        description="Expected parent runbook ID (e.g. RB-PG-001), or None if refusal expected",
    )
    expected_chunk_ids: list[str] = Field(
        default_factory=list,
        description="Rank-ordered or set of ground-truth chunk IDs expected in Top-K retrieval",
    )
    negative_chunk_ids: list[str] = Field(
        default_factory=list,
        description="Distractor/hard-negative chunk IDs that must NOT place at Rank 1",
    )
    should_refuse: bool = Field(
        default=False,
        description="Whether the retrieval/investigator engine must refuse to produce an actionable runbook",
    )
    expected_action_command: str | None = Field(
        default=None,
        description="Exact expected remediation or diagnostic command string",
    )
    expected_action_tier: int = Field(
        default=1,
        description="Policy tier classification: 1 for read-only inspection, 2 for mutating action",
    )
    expected_ground_truth_facts: list[str] = Field(
        default_factory=list,
        description="Factual assertions that must be present in the generated incident brief or answer",
    )
    forbidden_claims: list[str] = Field(
        default_factory=list,
        description="Claims that MUST NOT appear in generated output (e.g. hallucinated fixes or premature actions)",
    )

    @model_validator(mode="after")
    def validate_refusal_invariants(self) -> Self:
        """
        Enforce safety boundary: If should_refuse is True, the case cannot assert
        expected runbooks or chunk retrievals.
        """
        if self.should_refuse:
            if self.expected_chunk_ids:
                raise ValueError(
                    f"Refusal case {self.case_id} must have empty expected_chunk_ids, "
                    f"got {self.expected_chunk_ids}"
                )
            if self.expected_runbook_id is not None:
                raise ValueError(
                    f"Refusal case {self.case_id} must have expected_runbook_id=None, "
                    f"got {self.expected_runbook_id}"
                )
        return self
