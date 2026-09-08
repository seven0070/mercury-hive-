"""Typed schemas for AI Agent runtime decisions and resource tracking."""

import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentDecisionType(StrEnum):
    DELEGATE = "delegate"
    EXECUTE_TOOL = "execute_tool"
    COMPLETE_TASK = "complete"
    REQUEST_APPROVAL = "request_approval"
    REJECT_TASK = "reject"


class AgentDecision(BaseModel):
    """Strictly typed output schema for autonomous agent decisions."""

    model_config = ConfigDict(extra="forbid")

    decision: AgentDecisionType
    reason: str = Field(..., min_length=5, description="Justification for the decision")
    target_role: str | None = Field(default=None, description="Target role for delegation")
    target_agent_id: str | None = Field(
        default=None, description="Target agent UUID for delegation"
    )
    task_id: str | None = Field(default=None, description="Associated task ID")
    requested_tools: list[str] = Field(
        default_factory=list, description="Tools requested for execution"
    )
    tool_arguments: dict[str, Any] = Field(
        default_factory=dict, description="Arguments for the requested tool"
    )
    output_payload: dict[str, Any] = Field(
        default_factory=dict, description="Resulting work output artifacts"
    )
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Model self-assessed confidence score"
    )
    requires_approval: bool = Field(
        default=False, description="Whether human owner review is requested"
    )


@dataclass(frozen=True)
class UsageMetrics:
    """Cost and token accounting metrics per agent execution cycle."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    latency_ms: float = 0.0


@dataclass(frozen=True)
class AgentExecutionContext:
    """Execution context and hierarchy boundaries passed to an agent."""

    agent_id: uuid.UUID
    agent_role: str
    department_id: uuid.UUID | None
    task_id: uuid.UUID | None
    system_prompt_version: str = "1.0.0"
    context_data: dict[str, Any] | None = None
