"""Pydantic schemas for Phase 4: Tasks, Cross-Department Bridges, and Delegations."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from domain.enums.agent_status import DataClassification
from domain.enums.tasks import BridgeStatus, TaskPriority, TaskStatus


class TaskCreate(BaseModel):
    """Payload to create a new task or mission."""

    title: str = Field(..., min_length=3, max_length=256)
    description: str = Field(..., min_length=5)
    priority: TaskPriority = TaskPriority.MEDIUM
    origin_department_id: uuid.UUID
    assigned_department_id: uuid.UUID
    assigned_agent_id: uuid.UUID | None = None
    parent_task_id: uuid.UUID | None = None
    required_capabilities: list[str] = Field(default_factory=list)
    input_artifacts: dict | None = None
    budget_allocated: float = Field(default=0.0, ge=0.0)
    deadline: datetime | None = None


class TaskUpdate(BaseModel):
    """Payload to update an existing task."""

    title: str | None = None
    description: str | None = None
    priority: TaskPriority | None = None
    required_capabilities: list[str] | None = None
    input_artifacts: dict | None = None
    output_artifacts: dict | None = None
    budget_allocated: float | None = None
    budget_spent: float | None = None
    deadline: datetime | None = None


class TaskStatusTransition(BaseModel):
    """Payload to transition task status."""

    status: TaskStatus
    reason: str = Field(..., min_length=3, max_length=1000)
    output_artifacts: dict | None = None


class TaskResponse(BaseModel):
    """Task representation."""

    id: uuid.UUID
    title: str
    description: str
    priority: TaskPriority
    status: TaskStatus
    origin_department_id: uuid.UUID
    assigned_department_id: uuid.UUID
    assigned_agent_id: uuid.UUID | None
    created_by: uuid.UUID
    parent_task_id: uuid.UUID | None
    required_capabilities: list[str] | None
    input_artifacts: dict | None
    output_artifacts: dict | None
    budget_allocated: float
    budget_spent: float
    deadline: datetime | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class BridgeCreate(BaseModel):
    """Payload to propose a cross-department bridge."""

    source_department_id: uuid.UUID
    target_department_id: uuid.UUID
    purpose: str = Field(..., min_length=10, max_length=1000)
    allowed_data_classification: DataClassification = DataClassification.INTERNAL
    data_sharing_scopes: list[str] = Field(default_factory=list)
    expires_at: datetime


class BridgeDecisionRequest(BaseModel):
    """Decision payload for approving or rejecting a bridge."""

    reason: str = Field(..., min_length=3, max_length=1000)


class BridgeResponse(BaseModel):
    """Cross-department bridge representation."""

    id: uuid.UUID
    source_department_id: uuid.UUID
    target_department_id: uuid.UUID
    purpose: str
    status: BridgeStatus
    allowed_data_classification: DataClassification
    data_sharing_scopes: list[str] | None
    requested_by: uuid.UUID
    approved_by: uuid.UUID | None
    expires_at: datetime
    created_at: datetime
    revoked_at: datetime | None
    revocation_reason: str | None

    model_config = {"from_attributes": True}


class TaskDelegationCreate(BaseModel):
    """Payload to delegate a task across an active bridge."""

    task_id: uuid.UUID
    bridge_id: uuid.UUID
    delegated_to_agent_id: uuid.UUID
    notes: str | None = None


class TaskDelegationResponse(BaseModel):
    """Record of task delegation across departments."""

    id: uuid.UUID
    task_id: uuid.UUID
    bridge_id: uuid.UUID
    delegated_from_agent_id: uuid.UUID
    delegated_to_agent_id: uuid.UUID
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
