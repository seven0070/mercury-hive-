"""Unit tests for Phase 5: Tool Gateway, Scoped Memory, and Rollback Subsystem."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.enums.agent_status import AgentStatus, DataClassification
from domain.enums.roles import SystemRole
from domain.enums.tools import MemoryScope, RollbackStatus, ToolExecutionStatus
from domain.models.agents import Agent, PermissionGrant
from domain.models.tools import RollbackArtifact, ToolDefinition
from domain.schemas.tools import (
    AgentMemoryStore,
    ToolExecutionRequest,
)
from services.memory.service import MemoryError, store_memory
from services.rollback.service import RollbackError, execute_rollback
from services.tools.gateway import (
    ToolGatewayError,
    execute_tool,
)


@pytest.mark.asyncio
async def test_tool_execution_blocked_without_permission_grant():
    """Agents attempting to use tools without explicit permission grants must be blocked."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.execute.return_value = MagicMock()

    agent_id = uuid.uuid4()
    agent = Agent(
        id=agent_id,
        display_name="Restricted Bot",
        role=SystemRole.WORKER,
        status=AgentStatus.ACTIVE,
        system_prompt_version="1.0.0",
        created_at=datetime.now(UTC),
    )
    tool = ToolDefinition(
        id=uuid.uuid4(),
        name="shell_command",
        description="Shell execution",
        risk_level="HIGH",
        is_enabled=True,
        requires_approval=False,
        created_at=datetime.now(UTC),
    )

    r_agent = MagicMock()
    r_agent.scalar_one_or_none.return_value = agent

    r_tool = MagicMock()
    r_tool.scalar_one_or_none.return_value = tool

    r_grants = MagicMock()
    r_grants.scalars.return_value.all.return_value = []  # No grants!

    mock_session.execute.side_effect = [r_agent, r_tool, r_grants, MagicMock()]

    req = ToolExecutionRequest(
        tool_name="shell_command",
        agent_id=agent_id,
        parameters={"cmd": "ls"},
    )

    with pytest.raises(ToolGatewayError, match="lacking permission grant"):
        await execute_tool(
            session=mock_session,
            request=req,
            actor_id=agent_id,
            actor_role=SystemRole.WORKER,
        )


@pytest.mark.asyncio
async def test_tool_execution_sandbox_path_traversal():
    """Tools must reject path traversal attempts."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.execute.return_value = MagicMock()

    agent_id = uuid.uuid4()
    agent = Agent(
        id=agent_id,
        display_name="File Reader Bot",
        role=SystemRole.WORKER,
        status=AgentStatus.ACTIVE,
        system_prompt_version="1.0.0",
        created_at=datetime.now(UTC),
    )
    tool = ToolDefinition(
        id=uuid.uuid4(),
        name="file_reader",
        description="File reader",
        risk_level="LOW",
        is_enabled=True,
        requires_approval=False,
        created_at=datetime.now(UTC),
    )
    grant = PermissionGrant(
        id=uuid.uuid4(),
        agent_id=agent_id,
        allowed_tools=["file_reader"],
        allowed_actions=["READ"],
        created_at=datetime.now(UTC),
        issued_by=uuid.uuid4(),
    )

    r_agent = MagicMock()
    r_agent.scalar_one_or_none.return_value = agent
    r_tool = MagicMock()
    r_tool.scalar_one_or_none.return_value = tool
    r_grants = MagicMock()
    r_grants.scalars.return_value.all.return_value = [grant]

    mock_session.execute.side_effect = [r_agent, r_tool, r_grants, MagicMock()]

    req = ToolExecutionRequest(
        tool_name="file_reader",
        agent_id=agent_id,
        parameters={"path": "../../../etc/shadow"},
    )

    with pytest.raises(ToolGatewayError, match="Path traversal or empty path forbidden"):
        await execute_tool(
            session=mock_session,
            request=req,
            actor_id=agent_id,
            actor_role=SystemRole.WORKER,
        )


@pytest.mark.asyncio
async def test_valid_tool_execution_with_rollback():
    """Mutating tool execution records execution log and rollback artifact."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.execute.return_value = MagicMock()

    agent_id = uuid.uuid4()
    task_id = uuid.uuid4()

    agent = Agent(
        id=agent_id,
        display_name="Editor Bot",
        role=SystemRole.WORKER,
        status=AgentStatus.ACTIVE,
        system_prompt_version="1.0.0",
        created_at=datetime.now(UTC),
    )
    tool = ToolDefinition(
        id=uuid.uuid4(),
        name="file_writer",
        description="File writer",
        risk_level="MEDIUM",
        is_enabled=True,
        requires_approval=False,
        created_at=datetime.now(UTC),
    )
    grant = PermissionGrant(
        id=uuid.uuid4(),
        agent_id=agent_id,
        allowed_tools=["file_writer"],
        allowed_actions=["WRITE"],
        created_at=datetime.now(UTC),
        issued_by=uuid.uuid4(),
    )

    r_agent = MagicMock()
    r_agent.scalar_one_or_none.return_value = agent
    r_tool = MagicMock()
    r_tool.scalar_one_or_none.return_value = tool
    r_grants = MagicMock()
    r_grants.scalars.return_value.all.return_value = [grant]

    mock_session.execute.side_effect = [r_agent, r_tool, r_grants, MagicMock()]

    req = ToolExecutionRequest(
        tool_name="file_writer",
        agent_id=agent_id,
        task_id=task_id,
        parameters={"path": "sandbox/doc.txt", "content": "Updated content"},
    )

    execution = await execute_tool(
        session=mock_session,
        request=req,
        actor_id=agent_id,
        actor_role=SystemRole.WORKER,
    )

    assert execution.status == ToolExecutionStatus.SUCCESS
    assert execution.tool_name == "file_writer"
    assert execution.result["status"] == "written"
    # Verify add was called for both ToolExecution and RollbackArtifact
    assert mock_session.add.call_count >= 2


@pytest.mark.asyncio
async def test_scoped_memory_storage_and_versioning():
    """Agent memory storage enforces granted scope and increments version."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.execute.return_value = MagicMock()

    agent_id = uuid.uuid4()
    agent = Agent(
        id=agent_id,
        display_name="Memory Bot",
        role=SystemRole.WORKER,
        status=AgentStatus.ACTIVE,
        system_prompt_version="1.0.0",
        created_at=datetime.now(UTC),
    )
    grant = PermissionGrant(
        id=uuid.uuid4(),
        agent_id=agent_id,
        memory_scopes=[MemoryScope.TASK, MemoryScope.DEPARTMENT],
        created_at=datetime.now(UTC),
        issued_by=uuid.uuid4(),
    )

    r_agent = MagicMock()
    r_agent.scalar_one_or_none.return_value = agent
    r_grants = MagicMock()
    r_grants.scalars.return_value.all.return_value = [grant]
    r_existing = MagicMock()
    r_existing.scalar_one_or_none.return_value = None  # New item

    mock_session.execute.side_effect = [r_agent, r_grants, r_existing, MagicMock()]

    mem_data = AgentMemoryStore(
        scope=MemoryScope.TASK,
        key="last_checkpoint",
        value={"step": 42},
        data_classification=DataClassification.INTERNAL,
    )

    stored = await store_memory(
        session=mock_session,
        agent_id=agent_id,
        data=mem_data,
        actor_id=agent_id,
        actor_role=SystemRole.WORKER,
    )

    assert stored.key == "last_checkpoint"
    assert stored.version == 1
    assert stored.scope == MemoryScope.TASK

    # Test scope restriction: COMPANY_SHARED not in grants -> must fail
    mock_session.execute.side_effect = [r_agent, r_grants]
    forbidden_data = AgentMemoryStore(
        scope=MemoryScope.COMPANY_SHARED,
        key="company_secret",
        value="leak",
    )
    with pytest.raises(MemoryError, match="lacks permission grant for memory scope"):
        await store_memory(
            session=mock_session,
            agent_id=agent_id,
            data=forbidden_data,
            actor_id=agent_id,
            actor_role=SystemRole.WORKER,
        )


@pytest.mark.asyncio
async def test_rollback_execution():
    """State rollback reverts changes and sets status to EXECUTED."""
    mock_session = AsyncMock()
    mock_session.execute.return_value = MagicMock()

    artifact_id = uuid.uuid4()
    owner_id = uuid.uuid4()

    artifact = RollbackArtifact(
        id=artifact_id,
        task_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        tool_name="file_writer",
        target_resource="sandbox/config.yaml",
        previous_state={"config": "original"},
        new_state={"config": "corrupted"},
        status=RollbackStatus.AVAILABLE,
        created_at=datetime.now(UTC),
    )

    r_artifact = MagicMock()
    r_artifact.scalar_one_or_none.return_value = artifact
    mock_session.execute.return_value = r_artifact

    # Worker cannot trigger rollback
    with pytest.raises(RollbackError, match="Only Owner, CEO, or Managers can trigger rollbacks"):
        await execute_rollback(
            session=mock_session,
            rollback_id=artifact_id,
            actor_id=uuid.uuid4(),
            actor_role=SystemRole.WORKER,
            reason="Illegal rollback attempt",
        )

    # Owner can trigger rollback
    reverted = await execute_rollback(
        session=mock_session,
        rollback_id=artifact_id,
        actor_id=owner_id,
        actor_role="OWNER",
        reason="Reverting corrupted config file",
    )

    assert reverted.status == RollbackStatus.EXECUTED
    assert reverted.reverted_at is not None
    assert reverted.reverted_by == owner_id
