"""Pydantic schemas for Phase 6: Judging Council, Rubrics, and Evaluations."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from domain.enums.judging import CouncilStatus, EvaluationVerdict


class RubricCreate(BaseModel):
    """Payload to create a grading rubric."""

    name: str = Field(..., min_length=2, max_length=100)
    version: str = Field(default="1.0.0", max_length=32)
    description: str = Field(..., min_length=5)
    criteria: dict[str, Any] | list[Any]
    minimum_passing_score: float = Field(default=80.0, ge=0.0, le=100.0)
    is_active: bool = True


class RubricResponse(BaseModel):
    """Rubric representation."""

    id: uuid.UUID
    name: str
    version: str
    description: str
    criteria: dict[str, Any] | list[Any]
    minimum_passing_score: float
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class SubmissionCreate(BaseModel):
    """Payload to submit task deliverables to the judging council."""

    task_id: uuid.UUID
    title: str = Field(..., min_length=3, max_length=256)
    deliverable_payload: dict[str, Any]


class SubmissionResponse(BaseModel):
    """Deliverable submission representation."""

    id: uuid.UUID
    task_id: uuid.UUID
    author_agent_id: uuid.UUID
    title: str
    deliverable_payload: dict[str, Any]
    submitted_at: datetime

    model_config = {"from_attributes": True}


class JudgingSessionCreate(BaseModel):
    """Payload to initiate a council evaluation session."""

    submission_id: uuid.UUID
    rubric_id: uuid.UUID
    required_judges: int = Field(default=3, ge=1, le=9)


class JudgingSessionResponse(BaseModel):
    """Judging session representation."""

    id: uuid.UUID
    submission_id: uuid.UUID
    rubric_id: uuid.UUID
    status: CouncilStatus
    required_judges: int
    final_verdict: EvaluationVerdict | None
    aggregate_score: float | None
    consensus_notes: str | None
    created_at: datetime
    closed_at: datetime | None

    model_config = {"from_attributes": True}


class ScorecardSubmit(BaseModel):
    """Judge grading submission payload."""

    scores: dict[str, float]
    total_score: float = Field(..., ge=0.0, le=100.0)
    verdict: EvaluationVerdict
    feedback: str = Field(..., min_length=5)
    conflict_declared: bool = False
    conflict_reason: str | None = None


class ScorecardResponse(BaseModel):
    """Judge scorecard representation."""

    id: uuid.UUID
    session_id: uuid.UUID
    judge_agent_id: uuid.UUID
    scores: dict[str, float]
    total_score: float
    verdict: EvaluationVerdict
    feedback: str
    conflict_declared: bool
    conflict_reason: str | None
    submitted_at: datetime

    model_config = {"from_attributes": True}
