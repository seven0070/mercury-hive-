"""Pydantic schemas for Phase 8: Tribe Adapter and Team/Skill/Task Synchronization."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.enums.tribe import SkillProficiency, SyncDirection, SyncStatus


class TribeMappingCreate(BaseModel):
    """Schema for creating a department-to-tribe mapping."""

    department_id: uuid.UUID
    tribe_name: str = Field(min_length=2, max_length=100)
    squad_name: str = Field(min_length=2, max_length=100)
    external_team_id: str = Field(min_length=1, max_length=128)


class TribeMappingResponse(BaseModel):
    """Schema for returning tribe mapping details."""

    id: uuid.UUID
    department_id: uuid.UUID
    tribe_name: str
    squad_name: str
    external_team_id: str
    sync_status: SyncStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentSkillCreate(BaseModel):
    """Schema for registering a skill for an agent."""

    skill_name: str = Field(min_length=2, max_length=100)
    proficiency_level: SkillProficiency = SkillProficiency.COMPETENT


class AgentSkillVerify(BaseModel):
    """Schema for verifying or rejecting an agent skill."""

    is_verified: bool


class AgentSkillResponse(BaseModel):
    """Schema for returning agent skill details."""

    id: uuid.UUID
    agent_id: uuid.UUID
    skill_name: str
    proficiency_level: SkillProficiency
    is_verified: bool
    verified_by: uuid.UUID | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskSyncCreate(BaseModel):
    """Schema for creating an external task synchronization mapping."""

    task_id: uuid.UUID
    external_system: str = Field(min_length=2, max_length=64)
    external_task_id: str = Field(min_length=1, max_length=128)
    sync_direction: SyncDirection = SyncDirection.BIDIRECTIONAL


class TaskSyncResponse(BaseModel):
    """Schema for returning task synchronization details."""

    id: uuid.UUID
    task_id: uuid.UUID
    external_system: str
    external_task_id: str
    sync_direction: SyncDirection
    sync_status: SyncStatus
    last_synced_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExternalTaskIngestRequest(BaseModel):
    """Schema for ingesting an external issue/task into Mercury Hive."""

    external_system: str = Field(min_length=2, max_length=64)
    external_task_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=5)
    department_id: uuid.UUID
    priority: str = Field(default="MEDIUM")


class WebhookResponse(BaseModel):
    """Schema for external integration webhook response."""

    status: str = "processed"
    message: str = "Webhook processed successfully"
    idempotency_key: str | None = None
    event: str | None = None
    task_id: uuid.UUID | None = None
    cached: bool = False
    data: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)

