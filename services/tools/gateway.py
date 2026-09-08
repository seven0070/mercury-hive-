"""Governed Tool Gateway: policy verification, scoped execution, and execution logging."""

import time
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums.agent_status import AgentStatus
from domain.enums.tools import RollbackStatus, ToolExecutionStatus
from domain.models.agents import Agent, PermissionGrant
from domain.models.tools import RollbackArtifact, ToolDefinition, ToolExecution
from domain.schemas.audit import AuditEventCreate
from domain.schemas.tools import ToolDefinitionCreate, ToolExecutionRequest
from services.audit.service import log_audit_event

logger = structlog.get_logger()


class ToolGatewayError(Exception):
    """Business logic or security violations in the tool gateway."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# Built-in mock sandbox handlers
async def _execute_builtin_tool(
    name: str,
    params: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    """Execute a sandboxed built-in tool.

    Returns:
        (result_dict, previous_state, new_state)
    """
    if name == "file_reader":
        path = params.get("path", "")
        if not path or ".." in path:
            raise ToolGatewayError("Path traversal or empty path forbidden")
        return (
            {"content": f"Mock sandboxed content of {path}", "path": path},
            None,
            None,
        )

    if name == "file_writer":
        path = params.get("path", "")
        content = params.get("content", "")
        if not path or ".." in path:
            raise ToolGatewayError("Path traversal or empty path forbidden")
        prev = {"path": path, "content": "previous content"}
        new = {"path": path, "content": content}
        return (
            {"status": "written", "path": path, "bytes_written": len(content)},
            prev,
            new,
        )

    if name == "system_inspector":
        return (
            {
                "status": "healthy",
                "uptime_seconds": 3600,
                "sandbox_isolation": "enforced",
            },
            None,
            None,
        )

    # Generic tool fallback
    return ({"status": "executed", "echo": params}, None, None)


async def register_tool_definition(
    session: AsyncSession,
    data: ToolDefinitionCreate,
    creator_id: uuid.UUID,
    creator_role: str,
) -> ToolDefinition:
    """Register a new tool definition in the catalog."""
    if creator_role != "OWNER":
        raise ToolGatewayError("Only System Owner can register tool definitions")

    existing = await session.execute(select(ToolDefinition).where(ToolDefinition.name == data.name))
    if existing.scalar_one_or_none():
        raise ToolGatewayError(f"Tool '{data.name}' already registered")

    tool = ToolDefinition(
        id=uuid.uuid4(),
        name=data.name,
        description=data.description,
        risk_level=data.risk_level,
        schema_definition=data.schema_definition,
        is_enabled=data.is_enabled,
        requires_approval=data.requires_approval,
        created_at=datetime.now(UTC),
    )
    session.add(tool)
    await session.flush()
    return tool


async def execute_tool(
    session: AsyncSession,
    request: ToolExecutionRequest,
    actor_id: uuid.UUID,
    actor_role: str,
) -> ToolExecution:
    """Validate policy, check permission grant, execute tool, and record execution."""
    start_time = time.monotonic()
    now = datetime.now(UTC)

    # 1. Check agent status
    agent_res = await session.execute(select(Agent).where(Agent.id == request.agent_id))
    agent = agent_res.scalar_one_or_none()
    if not agent or agent.status != AgentStatus.ACTIVE:
        raise ToolGatewayError("Agent not found or not active", status_code=403)

    # 2. Check tool catalog entry
    tool_res = await session.execute(
        select(ToolDefinition).where(ToolDefinition.name == request.tool_name)
    )
    tool = tool_res.scalar_one_or_none()
    if not tool:
        raise ToolGatewayError(f"Tool '{request.tool_name}' not found in catalog")
    if not tool.is_enabled:
        raise ToolGatewayError(f"Tool '{request.tool_name}' is currently disabled")

    # 3. Check active permission grant
    # If caller is not OWNER, must have active permission grant including tool_name
    if actor_role != "OWNER":
        grant_res = await session.execute(
            select(PermissionGrant).where(
                PermissionGrant.agent_id == request.agent_id,
                PermissionGrant.revoked_at.is_(None),
                (PermissionGrant.expires_at.is_(None)) | (PermissionGrant.expires_at > now),
            )
        )
        grants = grant_res.scalars().all()
        allowed_tools = {t for g in grants for t in g.allowed_tools}
        if request.tool_name not in allowed_tools:
            # Policy blocked
            execution = ToolExecution(
                id=uuid.uuid4(),
                tool_name=request.tool_name,
                agent_id=request.agent_id,
                task_id=request.task_id,
                status=ToolExecutionStatus.BLOCKED_BY_POLICY,
                parameters=request.parameters,
                result=None,
                error_message=f"Agent lacking permission grant for tool '{request.tool_name}'",
                execution_duration_ms=0,
                created_at=now,
            )
            session.add(execution)
            await session.flush()

            await log_audit_event(
                session,
                AuditEventCreate(
                    event_type="ACCESS",
                    actor_id=actor_id,
                    actor_role=actor_role,
                    action="tool_execution_blocked",
                    decision="DENY",
                    reason=f"Unauthorized tool invocation: {request.tool_name}",
                    target_id=execution.id,
                    target_type="TOOL_EXECUTION",
                ),
            )
            raise ToolGatewayError(
                f"Agent lacking permission grant for tool '{request.tool_name}'",
                status_code=403,
            )

    # 4. Execute tool in sandbox
    try:
        result_payload, prev_state, new_state = await _execute_builtin_tool(
            request.tool_name,
            request.parameters,
        )
        duration_ms = int((time.monotonic() - start_time) * 1000)

        execution = ToolExecution(
            id=uuid.uuid4(),
            tool_name=request.tool_name,
            agent_id=request.agent_id,
            task_id=request.task_id,
            status=ToolExecutionStatus.SUCCESS,
            parameters=request.parameters,
            result=result_payload,
            error_message=None,
            execution_duration_ms=duration_ms,
            created_at=datetime.now(UTC),
        )
        session.add(execution)

        # If mutating tool produced reversible state, record RollbackArtifact
        if prev_state and new_state and request.task_id:
            rollback = RollbackArtifact(
                id=uuid.uuid4(),
                task_id=request.task_id,
                agent_id=request.agent_id,
                tool_name=request.tool_name,
                target_resource=request.parameters.get("path", "generic_resource"),
                previous_state=prev_state,
                new_state=new_state,
                status=RollbackStatus.AVAILABLE,
                created_at=datetime.now(UTC),
            )
            session.add(rollback)

        await session.flush()

        await log_audit_event(
            session,
            AuditEventCreate(
                event_type="SYSTEM",
                actor_id=actor_id,
                actor_role=actor_role,
                action="tool_executed",
                decision="ALLOW",
                reason=f"Tool {request.tool_name} executed successfully",
                target_id=execution.id,
                target_type="TOOL_EXECUTION",
                payload={"tool_name": request.tool_name, "duration_ms": duration_ms},
            ),
        )
        return execution

    except Exception as e:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        execution = ToolExecution(
            id=uuid.uuid4(),
            tool_name=request.tool_name,
            agent_id=request.agent_id,
            task_id=request.task_id,
            status=ToolExecutionStatus.FAILED,
            parameters=request.parameters,
            result=None,
            error_message=str(e),
            execution_duration_ms=duration_ms,
            created_at=datetime.now(UTC),
        )
        session.add(execution)
        await session.flush()
        raise
