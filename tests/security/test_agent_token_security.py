"""Security tests for Agent Token verification, database-backed authority,
and immediate revocation.
"""

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import RuntimeSettings
from apps.api.dependencies import get_current_agent
from domain.enums.agent_status import AgentStatus
from domain.models.agents import Agent
from services.identity.tokens import create_agent_token


class DummyRequest:
    """Mock Request for dependency testing."""

    def __init__(self, headers: dict[str, str]):
        self.headers = headers


@pytest.mark.asyncio
async def test_db_role_change_immediately_changes_authority_with_same_token(
    db_session: AsyncSession,
    admin_engine,
):
    """Database role is authoritative. Token claims cannot freeze or falsify agent role."""
    agent_id = uuid.uuid4()
    agent = Agent(
        id=agent_id,
        display_name="Role Shifting Agent",
        role="WORKER",
        status=AgentStatus.ACTIVE.value,
        system_prompt_version="1.0.0",
    )
    db_session.add(agent)
    await db_session.commit()

    settings = RuntimeSettings(
        database_url="sqlite+aiosqlite://",
        jwt_secret_key="test-secret-key-for-testing-at-least-32-bytes-long",
    )

    # Issue token indicating WORKER
    token = create_agent_token(agent_id, "WORKER", settings.jwt_secret_key)
    request = DummyRequest(headers={"Authorization": f"Bearer {token}"})

    auth_agent = await get_current_agent(request, db_session, settings)
    assert auth_agent.role == "WORKER"

    # Promote agent in database to DEPARTMENT_MANAGER via admin
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("UPDATE agents SET role = 'DEPARTMENT_MANAGER' WHERE id = :id"),
            {"id": agent_id},
        )
    db_session.expire_all()

    # Same token immediately resolves to DEPARTMENT_MANAGER without reissue
    updated_auth = await get_current_agent(request, db_session, settings)
    assert updated_auth.role == "DEPARTMENT_MANAGER"


@pytest.mark.asyncio
async def test_agent_suspension_immediately_blocks_access_without_token_reissue(
    db_session: AsyncSession,
):
    """Suspending an agent in PostgreSQL immediately revokes authentication (403)."""
    agent_id = uuid.uuid4()
    agent = Agent(
        id=agent_id,
        display_name="Suspended Agent",
        role="WORKER",
        status=AgentStatus.ACTIVE.value,
        system_prompt_version="1.0.0",
    )
    db_session.add(agent)
    await db_session.flush()

    settings = RuntimeSettings(
        database_url="sqlite+aiosqlite://",
        jwt_secret_key="test-secret-key-for-testing-at-least-32-bytes-long",
    )

    token = create_agent_token(agent_id, "WORKER", settings.jwt_secret_key)
    request = DummyRequest(headers={"Authorization": f"Bearer {token}"})

    # Active succeeds
    auth_agent = await get_current_agent(request, db_session, settings)
    assert auth_agent.agent_id == agent_id

    # Suspend in DB
    agent.status = AgentStatus.SUSPENDED.value
    await db_session.flush()

    # Same valid JWT is immediately rejected
    with pytest.raises(HTTPException) as exc_info:
        await get_current_agent(request, db_session, settings)
    assert exc_info.value.status_code == 403
    assert "not active" in exc_info.value.detail


@pytest.mark.asyncio
async def test_agent_termination_immediately_blocks_access(
    db_session: AsyncSession,
):
    """Terminating an agent in PostgreSQL immediately revokes authentication (403)."""
    agent_id = uuid.uuid4()
    agent = Agent(
        id=agent_id,
        display_name="Terminated Agent",
        role="WORKER",
        status=AgentStatus.ACTIVE.value,
        system_prompt_version="1.0.0",
    )
    db_session.add(agent)
    await db_session.flush()

    settings = RuntimeSettings(
        database_url="sqlite+aiosqlite://",
        jwt_secret_key="test-secret-key-for-testing-at-least-32-bytes-long",
    )

    token = create_agent_token(agent_id, "WORKER", settings.jwt_secret_key)
    request = DummyRequest(headers={"Authorization": f"Bearer {token}"})

    # Terminate in DB
    agent.status = AgentStatus.TERMINATED.value
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_agent(request, db_session, settings)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_stale_or_forged_role_claims_cannot_elevate_privileges(
    db_session: AsyncSession,
):
    """Even if a JWT claims role is CEO, the database record forces WORKER authority."""
    agent_id = uuid.uuid4()
    agent = Agent(
        id=agent_id,
        display_name="Subservient Worker",
        role="WORKER",
        status=AgentStatus.ACTIVE.value,
        system_prompt_version="1.0.0",
    )
    db_session.add(agent)
    await db_session.flush()

    settings = RuntimeSettings(
        database_url="sqlite+aiosqlite://",
        jwt_secret_key="test-secret-key-for-testing-at-least-32-bytes-long",
    )

    # Forged or stale claim: JWT signed with secret but contains role="CEO"
    forged_token = create_agent_token(agent_id, "CEO", settings.jwt_secret_key)
    request = DummyRequest(headers={"Authorization": f"Bearer {forged_token}"})

    auth_agent = await get_current_agent(request, db_session, settings)
    assert auth_agent.role == "WORKER"  # Enforced from PostgreSQL!
    assert auth_agent.role != "CEO"
