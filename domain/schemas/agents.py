"""Pydantic schemas for Phase 3: Departments, Agents, and Permission Grants."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from domain.enums.agent_status import AgentStatus, DataClassification, DepartmentStatus
from domain.enums.roles import SystemRole


class DepartmentCreate(BaseModel):
    """Payload to create or propose a new department."""

    name: str = Field(..., min_length=2, max_length=100)
    purpose: str = Field(..., min_length=5, max_length=1000)
    data_classification: DataClassification = DataClassification.INTERNAL
    budget: float = Field(default=0.0, ge=0.0)
    workspace_metadata: dict | None = None


class DepartmentResponse(BaseModel):
    """Department representation."""

    id: uuid.UUID
    name: str
    purpose: str
    status: DepartmentStatus
    manager_id: uuid.UUID | None
    hr_owner_id: uuid.UUID | None
    data_classification: DataClassification
    budget: float
    workspace_metadata: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentCreate(BaseModel):
    """Payload to provision a new agent."""

    display_name: str = Field(..., min_length=2, max_length=100)
    role: SystemRole
    department_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None
    persona_source: str | None = None
    persona_disclosure: str | None = None
    system_prompt_version: str = "1.0.0"
    avatar_profile_id: uuid.UUID | None = None
    parent_agent_id: uuid.UUID | None = None


class AgentUpdate(BaseModel):
    """Payload to update an agent."""

    display_name: str | None = None
    system_prompt_version: str | None = None
    persona_disclosure: str | None = None


class AgentStatusChange(BaseModel):
    """Payload to alter an agent status (suspend, terminate, restore)."""

    reason: str = Field(..., min_length=3, max_length=1000)


class AgentResponse(BaseModel):
    """Agent representation."""

    id: uuid.UUID
    display_name: str
    role: SystemRole
    department_id: uuid.UUID | None
    manager_id: uuid.UUID | None
    status: AgentStatus
    persona_source: str | None
    persona_disclosure: str | None
    system_prompt_version: str
    avatar_profile_id: uuid.UUID | None
    parent_agent_id: uuid.UUID | None
    created_at: datetime
    suspended_at: datetime | None
    terminated_at: datetime | None
    termination_reason: str | None

    model_config = {"from_attributes": True}


class PermissionGrantCreate(BaseModel):
    """Payload to issue a scoped permission grant."""

    agent_id: uuid.UUID
    task_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    allowed_actions: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    memory_scopes: list[str] = Field(default_factory=list)
    budget_limit: float | None = None
    expires_at: datetime | None = None
    approval_requirements: dict | None = None


class PermissionGrantResponse(BaseModel):
    """Permission grant representation."""

    id: uuid.UUID
    agent_id: uuid.UUID
    task_id: uuid.UUID | None
    department_id: uuid.UUID | None
    allowed_actions: list[str]
    allowed_tools: list[str]
    memory_scopes: list[str]
    budget_limit: float | None
    expires_at: datetime | None
    approval_requirements: dict | None
    issued_by: uuid.UUID
    created_at: datetime
    revoked_at: datetime | None
    revocation_reason: str | None

    model_config = {"from_attributes": True}

