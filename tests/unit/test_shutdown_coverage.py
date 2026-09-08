"""Unit tests for Milestone 4 (R4): Exhaustive Emergency Shutdown Coverage Audit.

Verifies:
- Centralized `verify_shutdown_state` dependency in `apps/api/dependencies.py`
- All 11 functional route modules enforce shutdown state checks:
  1) `agent_registry`
  2) `bridges`
  3) `tasks`
  4) `tools` (router + `gateway.py:execute_tool`)
  5) `memory`
  6) `rollback`
  7) `judging`
  8) `evolution`
  9) `tribe`
  10) `workspace`
  11) `governance` (approvals)
- Under `DEGRADED`: safe read-only queries (GET) succeed with 200 OK, while all 45 mutation
  endpoints return `HTTP 503 Service Unavailable`.
- Under `EMERGENCY_SHUTDOWN`: all state-altering mutation endpoints
  return `HTTP 503 Service Unavailable`.
- Under `EMERGENCY_SHUTDOWN`: non-owner operations are halted
  immediately with `HTTP 503 Service Unavailable`.
- Under `EMERGENCY_SHUTDOWN`: Owner recovery endpoints (`/owner/dashboard`, `/owner/override`,
  `/owner/console/summary`, `/owner/audit`, `/auth/logout`) remain fully accessible.
- Under `NORMAL`: endpoints are never blocked with 503 shutdown errors.
"""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException, Request
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from apps.api.config import RuntimeSettings
from apps.api.dependencies import (
    AuthenticatedOwner,
    get_audit_engine,
    get_current_owner,
    get_db,
    get_optional_db,
    get_settings,
    verify_shutdown_state,
)
from domain.enums.governance import SystemRunState
from domain.schemas.tools import ToolExecutionRequest
from services.agent_registry.router import router as agent_router
from services.bridges.router import router as bridge_router
from services.evolution.router import router as evolution_router
from services.governance.router import router as governance_router
from services.governance.shutdown import (
    get_cached_run_state,
    set_cached_run_state,
)
from services.identity.tokens import create_access_token
from services.judging.router import router as judging_router
from services.memory.router import router as memory_router
from services.rollback.router import router as rollback_router
from services.tasks.router import router as task_router
from services.tools.gateway import ToolGatewayError, execute_tool
from services.tools.router import router as tool_router
from services.tribe.router import router as tribe_router
from services.workspace.router import router as workspace_router

TEST_JWT_SECRET = "test-secret-key-minimum-32-characters-required-for-jwt"
TEST_OWNER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
TEST_SESSION_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")

# Exhaustive list of all 45 state-altering mutation endpoints across all 11 modules
MUTATION_ENDPOINTS = [
    # 1. Agent Registry (10 endpoints)
    (
        "POST",
        "/agents",
        {"display_name": "Test Bot", "role": "WORKER", "department_id": str(uuid.uuid4())},
    ),
    ("PATCH", f"/agents/{uuid.uuid4()}", {"display_name": "Patched Bot"}),
    ("POST", f"/agents/{uuid.uuid4()}/suspend", {"reason": "Suspension reason"}),
    ("POST", f"/agents/{uuid.uuid4()}/terminate", {"reason": "Termination reason"}),
    ("POST", f"/agents/{uuid.uuid4()}/restore", {"reason": "Restoration reason"}),
    ("POST", "/departments/proposals", {"name": "Test Dept", "purpose": "Propose dept"}),
    ("POST", f"/departments/{uuid.uuid4()}/approve", None),
    ("POST", f"/departments/{uuid.uuid4()}/suspend", {"reason": "Suspend dept"}),
    (
        "POST",
        "/permissions/grant",
        {
            "agent_id": str(uuid.uuid4()),
            "allowed_tools": ["file_reader"],
            "allowed_actions": ["READ"],
        },
    ),
    ("POST", f"/permissions/{uuid.uuid4()}/revoke", {"reason": "Revoke grant"}),
    # 2. Bridges (3 endpoints)
    (
        "POST",
        "/bridges",
        {
            "source_department_id": str(uuid.uuid4()),
            "target_department_id": str(uuid.uuid4()),
            "purpose": "Test bridge",
        },
    ),
    ("POST", f"/bridges/{uuid.uuid4()}/approve", {"reason": "Approve bridge"}),
    ("POST", f"/bridges/{uuid.uuid4()}/revoke", {"reason": "Revoke bridge"}),
    # 3. Tasks (4 endpoints)
    (
        "POST",
        "/tasks",
        {"title": "Test Task", "department_id": str(uuid.uuid4()), "priority": "HIGH"},
    ),
    ("POST", f"/tasks/{uuid.uuid4()}/assign?agent_id={uuid.uuid4()}", None),
    (
        "POST",
        f"/tasks/{uuid.uuid4()}/transition",
        {"target_status": "IN_PROGRESS", "reason": "Begin execution"},
    ),
    (
        "POST",
        "/tasks/delegate",
        {
            "task_id": str(uuid.uuid4()),
            "bridge_id": str(uuid.uuid4()),
            "target_department_id": str(uuid.uuid4()),
        },
    ),
    # 4. Tools (2 endpoints)
    (
        "POST",
        "/tools/catalog",
        {
            "name": "test_tool",
            "description": "Test tool",
            "risk_level": "LOW",
            "schema_definition": {},
        },
    ),
    (
        "POST",
        "/tools/execute",
        {"tool_name": "test_tool", "agent_id": str(uuid.uuid4()), "parameters": {}},
    ),
    # 5. Memory (1 endpoint)
    (
        "POST",
        f"/memory/{uuid.uuid4()}",
        {"scope": "AGENT", "key": "cache", "value": {"status": "ok"}},
    ),
    # 6. Rollback (1 endpoint)
    ("POST", f"/rollbacks/{uuid.uuid4()}/execute", {"reason": "Revert change"}),
    # 7. Judging (4 endpoints)
    (
        "POST",
        "/judging/rubrics",
        {"title": "Quality", "criteria": [{"name": "perf", "weight": 1.0, "max_score": 10.0}]},
    ),
    (
        "POST",
        f"/judging/submissions?author_agent_id={uuid.uuid4()}",
        {"task_id": str(uuid.uuid4()), "deliverable_payload": {}},
    ),
    (
        "POST",
        "/judging/sessions",
        {
            "rubric_id": str(uuid.uuid4()),
            "submission_id": str(uuid.uuid4()),
            "assigned_judge_ids": [str(uuid.uuid4())],
        },
    ),
    (
        "POST",
        f"/judging/sessions/{uuid.uuid4()}/score?judge_agent_id={uuid.uuid4()}",
        {"scores": {"perf": 8.0}, "rationale": "Pass"},
    ),
    # 8. Evolution (5 endpoints)
    (
        "POST",
        f"/evolution/candidates?proposer_agent_id={uuid.uuid4()}",
        {"candidate_type": "PROMPT", "title": "Prompt v2", "change_payload": {}},
    ),
    (
        "POST",
        f"/evolution/candidates/{uuid.uuid4()}/sandbox",
        {"test_suite_name": "suite1", "baseline_score": 0.8, "candidate_score": 0.9, "metrics": {}},
    ),
    ("POST", f"/evolution/candidates/{uuid.uuid4()}/shadow", {"percentage": 20}),
    ("POST", f"/evolution/candidates/{uuid.uuid4()}/promote", {"notes": "Promotion"}),
    ("POST", f"/evolution/candidates/{uuid.uuid4()}/rollback", {"reason": "Rollback evo"}),
    # 9. Tribe (6 endpoints)
    (
        "POST",
        "/tribe/mappings",
        {"department_id": str(uuid.uuid4()), "external_tribe": "Eng", "external_squad": "Core"},
    ),
    (
        "POST",
        f"/tribe/skills/{uuid.uuid4()}",
        {"skill_name": "Coding", "proficiency_level": "EXPERT"},
    ),
    ("POST", f"/tribe/skills/{uuid.uuid4()}/verify", {"is_verified": True}),
    (
        "POST",
        "/tribe/tasks/sync",
        {"task_id": str(uuid.uuid4()), "external_system": "Jira", "external_task_id": "J-1"},
    ),
    (
        "POST",
        "/tribe/tasks/ingest",
        {
            "external_system": "GitHub",
            "external_task_id": "GH-1",
            "title": "Issue",
            "department_id": str(uuid.uuid4()),
        },
    ),
    ("POST", "/tribe/webhook", {"event": "ping"}),
    # 10. Workspace (6 endpoints)
    ("POST", "/workspace/zones", {"name": "Lounge", "zone_type": "COMMUNAL", "capacity": 20}),
    (
        "POST",
        "/workspace/avatars",
        {"agent_id": str(uuid.uuid4()), "attire_class": "CASUAL", "visual_customizations": {}},
    ),
    (
        "POST",
        "/workspace/presence",
        {"zone_id": str(uuid.uuid4()), "presence_state": "ONLINE", "spatial_position": [0, 0, 0]},
    ),
    (
        "POST",
        "/workspace/meetings",
        {
            "title": "Standup",
            "zone_id": str(uuid.uuid4()),
            "scheduled_start": "2026-09-08T12:00:00Z",
        },
    ),
    ("POST", f"/workspace/meetings/{uuid.uuid4()}/start", None),
    ("POST", f"/workspace/meetings/{uuid.uuid4()}/conclude", {"meeting_minutes": "Minutes"}),
    # 11. Governance Approvals (3 endpoints)
    (
        "POST",
        "/approvals",
        {"action_type": "TOOL_EXECUTION", "description": "Run tool", "payload": {}},
    ),
    ("POST", f"/approvals/{uuid.uuid4()}/approve", {"reason": "Owner approve"}),
    ("POST", f"/approvals/{uuid.uuid4()}/reject", {"reason": "Owner reject"}),
]

# Read-only GET endpoints to verify accessibility under DEGRADED mode
READ_ONLY_ENDPOINTS = [
    # Agent Registry
    "/agents",
    "/departments",
    f"/agents/{uuid.uuid4()}/grants",
    # Bridges
    "/bridges",
    # Tasks
    "/tasks",
    # Tools
    "/tools/catalog",
    # Memory
    f"/memory/{uuid.uuid4()}",
    # Rollback
    "/rollbacks",
    # Judging
    "/judging/rubrics",
    # Evolution
    "/evolution/candidates",
    # Tribe
    "/tribe/mappings",
    f"/tribe/skills/{uuid.uuid4()}",
    "/tribe/tasks/sync",
    # Workspace
    "/workspace/zones",
    "/workspace/presence",
    # Governance Approvals
    "/approvals",
]


@pytest.fixture(autouse=True)
def reset_shutdown_state():
    """Ensure shutdown state is always reset to NORMAL after each test."""
    set_cached_run_state(SystemRunState.NORMAL, None)
    yield
    set_cached_run_state(SystemRunState.NORMAL, None)


@pytest.fixture
def test_settings() -> RuntimeSettings:
    """Runtime settings for test environment."""
    return RuntimeSettings(
        database_url="postgresql+asyncpg://mercury_runtime:test@localhost:5432/test_db",
        jwt_secret_key=TEST_JWT_SECRET,
        tribe_webhook_secret=SecretStr("test-tribe-secret"),
    )


@pytest.fixture
def owner_token(test_settings: RuntimeSettings) -> str:
    """Generate a valid owner access token."""
    return create_access_token(
        owner_id=TEST_OWNER_ID,
        secret_key=test_settings.jwt_secret_key,
        session_id=TEST_SESSION_ID,
    )


@pytest.fixture
def owner_headers(owner_token: str) -> dict[str, str]:
    """Provide valid authorization headers for owner."""
    return {"Authorization": f"Bearer {owner_token}"}


@pytest.fixture
def mock_session():
    """Mock database session returning empty results for queries and handling flushes."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalar_one.return_value = 0
    session.execute.return_value = mock_result
    session.get.return_value = None
    return session


@pytest.fixture
def app(test_settings: RuntimeSettings, mock_session: AsyncMock) -> FastAPI:
    """Create comprehensive test application mounting all 11 route modules."""
    test_app = FastAPI(title="Mercury Hive Shutdown Coverage Test App")
    test_app.state.settings = test_settings
    test_app.state.audit_engine = AsyncMock()

    # Mount all 11 route modules
    test_app.include_router(agent_router)
    test_app.include_router(bridge_router)
    test_app.include_router(task_router)
    test_app.include_router(tool_router)
    test_app.include_router(memory_router)
    test_app.include_router(rollback_router)
    test_app.include_router(judging_router)
    test_app.include_router(evolution_router)
    test_app.include_router(tribe_router)
    test_app.include_router(workspace_router)
    test_app.include_router(governance_router)

    # Dependency overrides for unit testing
    mock_owner = AuthenticatedOwner(
        owner_id=TEST_OWNER_ID,
        session_id=TEST_SESSION_ID,
        token_id=uuid.uuid4(),
    )

    test_app.dependency_overrides[get_settings] = lambda: test_settings
    test_app.dependency_overrides[get_current_owner] = lambda: mock_owner
    test_app.dependency_overrides[get_db] = lambda: mock_session
    test_app.dependency_overrides[get_optional_db] = lambda: mock_session
    test_app.dependency_overrides[get_audit_engine] = lambda: test_app.state.audit_engine

    return test_app


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """HTTP client wired to test application."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


# =====================================================================
# 1. Direct Unit Tests for `verify_shutdown_state` Dependency
# =====================================================================


@pytest.mark.asyncio
async def test_verify_shutdown_state_dependency_unit(test_settings: RuntimeSettings):
    """Direct unit testing of verify_shutdown_state dependency logic."""
    app = FastAPI()
    app.state.settings = test_settings

    # Helper request factory
    def make_request(
        method: str = "POST", path: str = "/tasks", auth_header: str | None = None
    ) -> Request:
        headers = []
        if auth_header:
            headers.append((b"authorization", auth_header.encode("utf-8")))
        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "headers": headers,
            "app": app,
        }
        return Request(scope)

    token = create_access_token(
        owner_id=TEST_OWNER_ID,
        secret_key=test_settings.jwt_secret_key,
        session_id=TEST_SESSION_ID,
    )
    auth_header = f"Bearer {token}"

    # A. NORMAL state: mutations and queries allowed
    set_cached_run_state(SystemRunState.NORMAL)
    verifier_mut = verify_shutdown_state(mutation=True)
    verifier_read = verify_shutdown_state(mutation=False)

    await verifier_mut(make_request("POST", "/tasks", auth_header))
    await verifier_read(make_request("GET", "/tasks", auth_header))

    # B. DEGRADED state: GET allowed, POST blocked with 503
    set_cached_run_state(SystemRunState.DEGRADED, "Routine maintenance")
    await verifier_read(make_request("GET", "/tasks", auth_header))

    with pytest.raises(HTTPException) as exc_info:
        await verifier_mut(make_request("POST", "/tasks", auth_header))
    assert exc_info.value.status_code == 503
    assert "System in degraded mode" in exc_info.value.detail
    assert "Routine maintenance" in exc_info.value.detail

    # C. EMERGENCY_SHUTDOWN state: mutation blocked for owner with 503
    set_cached_run_state(SystemRunState.EMERGENCY_SHUTDOWN, "Security breach")
    with pytest.raises(HTTPException) as exc_info:
        await verifier_mut(make_request("POST", "/tasks", auth_header))
    assert exc_info.value.status_code == 503
    assert "Emergency shutdown active: all mutations halted" in exc_info.value.detail
    assert "Security breach" in exc_info.value.detail

    # D. EMERGENCY_SHUTDOWN state: recovery endpoints permitted
    verifier_rec = verify_shutdown_state(mutation=True)
    await verifier_rec(make_request("POST", "/owner/emergency-shutdown", auth_header))
    await verifier_rec(make_request("POST", "/owner/override", auth_header))

    # E. EMERGENCY_SHUTDOWN state: non-owner blocked with 503 on read-only endpoints
    with pytest.raises(HTTPException) as exc_info:
        await verifier_read(make_request("GET", "/tasks", auth_header=None))
    assert exc_info.value.status_code == 503
    assert "non-owner operations halted" in exc_info.value.detail


# =====================================================================
# 2. Tool Execution Gateway Direct Shutdown Tests
# =====================================================================


@pytest.mark.asyncio
async def test_execute_tool_gateway_shutdown_checks():
    """Tool gateway directly blocks tool executions in DEGRADED and EMERGENCY_SHUTDOWN."""
    mock_session = AsyncMock()
    req = ToolExecutionRequest(
        tool_name="test_tool",
        agent_id=uuid.uuid4(),
        parameters={},
    )

    # 1. In EMERGENCY_SHUTDOWN
    set_cached_run_state(SystemRunState.EMERGENCY_SHUTDOWN, "Containment protocol")
    with pytest.raises(ToolGatewayError) as exc_info:
        await execute_tool(
            session=mock_session,
            request=req,
            actor_id=TEST_OWNER_ID,
            actor_role="OWNER",
        )
    assert exc_info.value.status_code == 503
    assert "emergency shutdown active" in exc_info.value.message
    assert "Containment protocol" in exc_info.value.message

    # 2. In DEGRADED
    set_cached_run_state(SystemRunState.DEGRADED, "Hardware degrade")
    with pytest.raises(ToolGatewayError) as exc_info:
        await execute_tool(
            session=mock_session,
            request=req,
            actor_id=TEST_OWNER_ID,
            actor_role="OWNER",
        )
    assert exc_info.value.status_code == 503
    assert "system in degraded mode" in exc_info.value.message
    assert "Hardware degrade" in exc_info.value.message


# =====================================================================
# 3. Exhaustive Verification: 45 Mutation Endpoints in EMERGENCY_SHUTDOWN
# =====================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,payload", MUTATION_ENDPOINTS)
async def test_all_mutation_endpoints_blocked_in_emergency_shutdown(
    client: AsyncClient,
    owner_headers: dict[str, str],
    method: str,
    path: str,
    payload: dict | None,
):
    """Every mutation endpoint across all 11 modules must return 503 in EMERGENCY_SHUTDOWN."""
    set_cached_run_state(
        SystemRunState.EMERGENCY_SHUTDOWN,
        "System compromised by adversary",
    )

    if method == "POST":
        resp = await client.post(path, json=payload, headers=owner_headers)
    elif method == "PATCH":
        resp = await client.patch(path, json=payload, headers=owner_headers)
    else:
        pytest.fail(f"Unsupported mutation method: {method}")

    assert resp.status_code == 503, f"{method} {path} returned {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "Emergency shutdown active" in data["detail"]
    assert "System compromised by adversary" in data["detail"]


# =====================================================================
# 4. Exhaustive Verification: 45 Mutation Endpoints in DEGRADED Mode
# =====================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,payload", MUTATION_ENDPOINTS)
async def test_all_mutation_endpoints_blocked_in_degraded_mode(
    client: AsyncClient,
    owner_headers: dict[str, str],
    method: str,
    path: str,
    payload: dict | None,
):
    """Every mutation endpoint across all 11 modules must return 503 in DEGRADED mode."""
    set_cached_run_state(
        SystemRunState.DEGRADED,
        "Database maintenance underway",
    )

    if method == "POST":
        resp = await client.post(path, json=payload, headers=owner_headers)
    elif method == "PATCH":
        resp = await client.patch(path, json=payload, headers=owner_headers)
    else:
        pytest.fail(f"Unsupported mutation method: {method}")

    assert resp.status_code == 503, f"{method} {path} returned {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "System in degraded mode: mutations temporarily suspended" in data["detail"]
    assert "Database maintenance underway" in data["detail"]


# =====================================================================
# 5. Read-Only Queries Remain Accessible in DEGRADED Mode
# =====================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("path", READ_ONLY_ENDPOINTS)
async def test_read_only_endpoints_accessible_in_degraded_mode(
    client: AsyncClient,
    owner_headers: dict[str, str],
    path: str,
):
    """Safe read-only GET endpoints remain functional (return 200 OK) in DEGRADED mode."""
    set_cached_run_state(
        SystemRunState.DEGRADED,
        "Read-only maintenance window",
    )

    resp = await client.get(path, headers=owner_headers)
    assert resp.status_code == 200, f"GET {path} returned {resp.status_code}: {resp.text}"


# =====================================================================
# 6. Owner Recovery Endpoints Accessible in EMERGENCY_SHUTDOWN
# =====================================================================


@pytest.mark.asyncio
async def test_owner_recovery_endpoints_accessible_in_emergency_shutdown(
    client: AsyncClient,
    owner_headers: dict[str, str],
    mock_session: AsyncMock,
):
    """Owner can access recovery controls (dashboard, audit, override) during EMERGENCY_SHUTDOWN."""
    set_cached_run_state(
        SystemRunState.EMERGENCY_SHUTDOWN,
        "Critical incident isolation",
    )

    # 1. Owner Dashboard must be accessible (200)
    dash_resp = await client.get("/owner/dashboard", headers=owner_headers)
    assert dash_resp.status_code == 200, dash_resp.text
    assert dash_resp.json()["system_run_state"] == "EMERGENCY_SHUTDOWN"

    # 2. Owner Console Summary must be accessible (200)
    summary_resp = await client.get("/owner/console/summary", headers=owner_headers)
    assert summary_resp.status_code == 200, summary_resp.text
    assert summary_resp.json()["system_run_state"] == "EMERGENCY_SHUTDOWN"

    # 3. Owner Audit logs must be accessible (200)
    audit_resp = await client.get("/owner/audit", headers=owner_headers)
    assert audit_resp.status_code == 200, audit_resp.text

    # 4. Owner Override must be permitted to transition system back to NORMAL
    override_resp = await client.post(
        "/owner/override",
        headers=owner_headers,
        json={"target_state": "NORMAL", "reason": "Incident resolved"},
    )
    assert override_resp.status_code == 200, override_resp.text
    assert override_resp.json()["run_state"] == "NORMAL"

    # Verify cached state reflects NORMAL restoration
    cached_state, _ = get_cached_run_state()
    assert cached_state == SystemRunState.NORMAL


# =====================================================================
# 7. Non-Owner Callers Halted in EMERGENCY_SHUTDOWN
# =====================================================================


@pytest.mark.asyncio
async def test_non_owner_halted_in_emergency_shutdown(client: AsyncClient):
    """Non-owner callers are immediately halted with 503 in EMERGENCY_SHUTDOWN."""
    set_cached_run_state(
        SystemRunState.EMERGENCY_SHUTDOWN,
        "System sealed",
    )

    # Calling read-only endpoint without owner token
    resp = await client.get("/agents")
    assert resp.status_code == 503
    assert "non-owner operations halted" in resp.json()["detail"]


# =====================================================================
# 8. Normal State Verifications: No 503 Shutdown Errors
# =====================================================================


@pytest.mark.asyncio
async def test_normal_mode_does_not_block_operations(
    client: AsyncClient,
    owner_headers: dict[str, str],
):
    """In NORMAL run state, neither GET queries nor mutation endpoints return 503."""
    set_cached_run_state(SystemRunState.NORMAL)

    # Read endpoint succeeds with 200
    get_resp = await client.get("/agents", headers=owner_headers)
    assert get_resp.status_code == 200

    # Mutation endpoint does not return 503
    post_resp = await client.post(
        "/tools/catalog",
        headers=owner_headers,
        json={
            "name": "calc_tool",
            "description": "Calculator",
            "risk_level": "LOW",
            "schema_definition": {},
        },
    )
    assert post_resp.status_code != 503


# =====================================================================
# 9. Custom Shutdown Reason Propagation
# =====================================================================


@pytest.mark.asyncio
async def test_custom_shutdown_reason_propagation(
    client: AsyncClient,
    owner_headers: dict[str, str],
):
    """Custom shutdown reasons are cleanly returned in the 503 response detail."""
    unique_reason = f"Security audit code: {uuid.uuid4()}"
    set_cached_run_state(SystemRunState.EMERGENCY_SHUTDOWN, unique_reason)

    resp = await client.post(
        "/tasks",
        headers=owner_headers,
        json={"title": "Task", "department_id": str(uuid.uuid4()), "priority": "HIGH"},
    )
    assert resp.status_code == 503
    assert unique_reason in resp.json()["detail"]
