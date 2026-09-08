"""Pydantic schemas for Phase 7: Controlled Evolution, Sandboxes, and Shadow Deployments."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.enums.evolution import EvolutionStatus, EvolutionType, SandboxVerdict


class EvolutionCandidateCreate(BaseModel):
    """Schema for proposing an evolution candidate."""

    title: str = Field(min_length=3, max_length=256)
    evolution_type: EvolutionType
    target_identifier: str = Field(min_length=1, max_length=128)
    proposed_change: dict[str, Any]


class EvolutionCandidateResponse(BaseModel):
    """Schema for returning evolution candidate details."""

    id: uuid.UUID
    title: str
    evolution_type: EvolutionType
    target_identifier: str
    proposed_change: dict[str, Any]
    status: EvolutionStatus
    proposer_agent_id: uuid.UUID
    benchmark_results: dict[str, Any] | None = None
    shadow_traffic_percentage: int
    created_at: datetime
    approved_by: uuid.UUID | None = None
    promoted_at: datetime | None = None
    reverted_at: datetime | None = None
    reversion_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)


class SandboxRunCreate(BaseModel):
    """Schema for creating a sandbox benchmarking run."""

    candidate_id: uuid.UUID
    test_suite_name: str = Field(min_length=1, max_length=128)
    baseline_score: float = Field(ge=0.0, le=100.0)
    candidate_score: float = Field(ge=0.0, le=100.0)
    metrics: dict[str, Any] | None = None
    verdict: SandboxVerdict


class SandboxRunResponse(BaseModel):
    """Schema for returning sandbox run details."""

    id: uuid.UUID
    candidate_id: uuid.UUID
    test_suite_name: str
    baseline_score: float
    candidate_score: float
    metrics: dict[str, Any] | None = None
    verdict: SandboxVerdict
    executed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ShadowDeployRequest(BaseModel):
    """Schema for configuring shadow traffic deployment."""

    percentage: int = Field(ge=1, le=100)


class PromotionRequest(BaseModel):
    """Schema for promoting an evolution candidate to production."""

    notes: str | None = Field(default=None, max_length=500)


class RollbackRequest(BaseModel):
    """Schema for rolling back a promoted or shadow-deployed candidate."""

    reason: str = Field(min_length=3, max_length=1000)
