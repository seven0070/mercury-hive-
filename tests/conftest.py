"""Test fixtures for Mercury Hive.

Test infrastructure:
- Uses isolated test database (mercury_hive_test)
- Test admin role for setup, test runtime role for application
- Async fixtures with pytest-asyncio
- Pre-created owner for auth tests

Environment variables (set by make test or docker-compose.test.yml):
- DATABASE_TEST_URL: async connection string for test runtime role
- DATABASE_TEST_ADMIN_URL: async connection string for test admin role
- DATABASE_TEST_RUNTIME_SYNC: sync connection string for privilege tests
- CONSTITUTION_PATH: path to constitution.yaml
"""

import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import create_async_engine

from apps.api.config import RuntimeSettings
from apps.api.main import create_app
from services.identity.hashing import hash_password

# Test constants
TEST_OWNER_EMAIL = "owner@mercury-hive.test"
TEST_OWNER_PASSWORD = "test-password-long-enough-16"
TEST_JWT_SECRET = "test-disposable-secret-key-32-chars-long"


@pytest_asyncio.fixture
async def admin_engine():
    """Admin engine for test setup (create owner, etc.)."""
    url = os.environ.get(
        "DATABASE_TEST_ADMIN_URL",
        "postgresql+asyncpg://mercury_test_admin:test_admin_disposable_pw@postgres-test:5432/mercury_hive_test",
    )
    engine = create_async_engine(url, poolclass=pool.NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def test_owner_id(admin_engine) -> uuid.UUID:
    """Create test owner using admin credentials. Returns owner ID."""
    owner_id = uuid.uuid4()
    password_hash_value = hash_password(TEST_OWNER_PASSWORD)

    async with admin_engine.begin() as conn:
        # Clean up transient test-created data
        await conn.execute(text("DELETE FROM meeting_participants"))
        await conn.execute(text("DELETE FROM virtual_meetings"))
        await conn.execute(text("DELETE FROM presence_sessions"))
        await conn.execute(text("DELETE FROM avatar_profiles"))
        await conn.execute(text("DELETE FROM workspace_zones WHERE department_id IS NOT NULL"))
        await conn.execute(text("DELETE FROM task_sync_mappings"))
        await conn.execute(text("DELETE FROM agent_skills"))
        await conn.execute(text("DELETE FROM tribe_mappings"))
        await conn.execute(text("DELETE FROM sandbox_runs"))
        await conn.execute(text("DELETE FROM evolution_candidates"))
        await conn.execute(text("DELETE FROM judge_scorecards"))
        await conn.execute(text("DELETE FROM judging_sessions"))
        await conn.execute(text("DELETE FROM evaluation_submissions"))
        await conn.execute(text("DELETE FROM rollback_artifacts"))
        await conn.execute(text("DELETE FROM agent_memories"))
        await conn.execute(text("DELETE FROM tool_executions"))
        await conn.execute(
            text(
                "DELETE FROM tool_definitions WHERE name NOT IN "
                "('file_reader', 'file_writer', 'memory_store', 'memory_fetch', 'system_inspector')"
            )
        )
        await conn.execute(text("DELETE FROM task_delegations"))
        await conn.execute(text("DELETE FROM cross_department_bridges"))
        await conn.execute(text("DELETE FROM tasks"))
        await conn.execute(text("DELETE FROM permission_grants"))
        await conn.execute(text("DELETE FROM agents"))
        await conn.execute(text("DELETE FROM approvals"))
        await conn.execute(
            text(
                "DELETE FROM departments WHERE status = 'PROPOSED' OR name LIKE 'Special Projects%'"
            )
        )
        await conn.execute(text("DELETE FROM refresh_tokens"))
        await conn.execute(text("DELETE FROM owner_sessions"))
        await conn.execute(text("DELETE FROM audit_events"))
        await conn.execute(text("DELETE FROM owners"))

        # Create test owner
        await conn.execute(
            text(
                "INSERT INTO owners (id, singleton, email, password_hash, status) "
                "VALUES (:id, true, :email, :password_hash, 'ACTIVE')"
            ),
            {
                "id": owner_id,
                "email": TEST_OWNER_EMAIL,
                "password_hash": password_hash_value,
            },
        )

    return owner_id


@pytest.fixture
def settings() -> RuntimeSettings:
    """Runtime settings for tests."""
    return RuntimeSettings(
        database_url=os.environ.get(
            "DATABASE_TEST_URL",
            os.environ.get(
                "DATABASE_URL",
                "postgresql+asyncpg://mercury_test_runtime:test_runtime_disposable_pw@postgres-test:5432/mercury_hive_test",
            ),
        ),
        jwt_secret_key=os.environ.get("JWT_SECRET_KEY", TEST_JWT_SECRET),
        jwt_algorithm=os.environ.get("JWT_ALGORITHM", "HS256"),
        jwt_issuer=os.environ.get("JWT_ISSUER", "mercury-hive"),
        jwt_audience=os.environ.get("JWT_AUDIENCE", "mercury-hive-api"),
        jwt_access_token_minutes=5,
        jwt_refresh_token_hours=24,
        jwt_session_days=7,
        constitution_path=os.environ.get("CONSTITUTION_PATH", "policies/constitution.yaml"),
    )


@pytest_asyncio.fixture
async def app(settings, test_owner_id):
    """Create test FastAPI application with lifespan context."""
    os.environ["DATABASE_URL"] = settings.database_url
    os.environ["JWT_SECRET_KEY"] = settings.jwt_secret_key
    os.environ["CONSTITUTION_PATH"] = settings.constitution_path

    application = create_app()
    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture
async def client(app) -> AsyncClient:
    """Async HTTP test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_tokens(client) -> dict:
    """Login and return access + refresh tokens."""
    response = await client.post(
        "/auth/login",
        json={"email": TEST_OWNER_EMAIL, "password": TEST_OWNER_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()
