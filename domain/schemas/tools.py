"""Pydantic schemas for Phase 5: Tool Gateway, Scoped Memory, and Rollback Artifacts."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from domain.enums.agent_status import DataClassification
from domain.enums.governance import RiskLevel
from domain.enums.tools import MemoryScope, RollbackStatus, ToolExecutionStatus


class ToolDefinitionCreate(BaseModel):
    """Payload to register a tool in the catalog."""

    name: str = Field(..., min_length=2, max_length=64)
    description: str = Field(..., min_length=5)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    schema_definition: dict | None = None
    is_enabled: bool = True
    requires_approval: bool = False


class ToolDefinitionResponse(BaseModel):
    """Tool definition representation."""

    id: uuid.UUID
    name: str
    description: str
    risk_level: RiskLevel
    schema_definition: dict | None
    is_enabled: bool
    requires_approval: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ToolExecutionRequest(BaseModel):
    """Payload to request a sandboxed tool invocation."""

    tool_name: str
    agent_id: uuid.UUID
    task_id: uuid.UUID | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class ToolExecutionResponse(BaseModel):
    """Audited result of a tool invocation."""

    id: uuid.UUID
    tool_name: str
    agent_id: uuid.UUID
    task_id: uuid.UUID | None
    status: ToolExecutionStatus
    parameters: dict[str, Any] | None
    result: dict[str, Any] | None
    error_message: str | None
    execution_duration_ms: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentMemoryStore(BaseModel):
    """Payload to store or update scoped agent memory."""

    scope: MemoryScope
    scope_id: uuid.UUID | None = None
    key: str = Field(..., min_length=1, max_length=128)
    value: Any
    data_classification: DataClassification = DataClassification.INTERNAL


class AgentMemoryResponse(BaseModel):
    """Agent memory record representation."""

    id: uuid.UUID
    agent_id: uuid.UUID
    scope: MemoryScope
    scope_id: uuid.UUID | None
    key: str
    value: Any
    data_classification: DataClassification
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RollbackResponse(BaseModel):
    """Reversible change artifact representation."""

    id: uuid.UUID
    task_id: uuid.UUID
    agent_id: uuid.UUID
    tool_name: str
    target_resource: str
    status: RollbackStatus
    created_at: datetime
    reverted_at: datetime | None
    reverted_by: uuid.UUID | None

    model_config = {"from_attributes": True}
