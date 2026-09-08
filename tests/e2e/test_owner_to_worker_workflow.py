"""End-to-End test of the complete Owner-to-Worker governed workflow.

Scenario:
1. Owner authenticates and verifies session
2. Owner creates high-level strategic mission task
3. Cross-department bridge approved between Executive and Engineering
4. Digital CEO agent receives mission and delegates staffing to HR
5. HR agent provisions and assigns a Worker agent in Engineering
6. Worker receives scoped PermissionGrant (allowed tool: file_reader)
7. Worker executes approved task via Agent Runtime
8. Tool calls pass through Sandboxed Tool Gateway and output is stored
9. Output is evaluated by Independent Verifier (with conflict-of-interest check)
10. Release queue approval item created and approved by System Owner
11. Audit events are generated throughout across all actors (OWNER, CEO, HR, WORKER, VERIFIER)
12. Revoking worker permission grant immediately blocks subsequent tool executions
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums.governance import ApprovalStatus, RiskLevel
from domain.enums.tasks import TaskStatus
from domain.models.agents import Agent, PermissionGrant
from domain.models.audit_event import AuditEvent
from domain.models.tasks import Task
from domain.schemas.governance import ApprovalCreate
from domain.schemas.tools import ToolExecutionRequest
from services.agent_runtime.models import AgentDecisionType
from services.agent_runtime.provider import DeterministicAgentProvider
from services.agent_runtime.runner import run_agent_cycle
from services.governance.approvals import create_approval, decide_approval
from services.identity.tokens import create_agent_token, validate_access_token
from services.permissions.engine import Decision, authorize
from services.tools.gateway import ToolGatewayError, execute_tool


@pytest.mark.asyncio
async def test_full_owner_to_worker_governed_workflow(
    client: AsyncClient,
    auth_tokens: dict,
    db_session: AsyncSession,
    test_owner_id: uuid.UUID,
):
    """Execute and verify complete 16-step owner-to-worker workflow through real API and DB."""
    owner_headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}
    jwt_secret = "test-secret-key-for-testing-at-least-32-bytes-long"

    # -------------------------------------------------------------------------
    # Step 1: Owner Authentication & Profile Verification
    # -------------------------------------------------------------------------
    me_res = await client.get("/auth/me", headers=owner_headers)
    assert me_res.status_code == 200
    assert me_res.json()["id"] == str(test_owner_id)

    # -------------------------------------------------------------------------
    # Step 2: Fetch Seeded Departments
    # -------------------------------------------------------------------------
    dept_res = await client.get("/departments", headers=owner_headers)
    assert dept_res.status_code == 200
    depts = dept_res.json()
    exec_dept = next(d for d in depts if d["name"] == "Operations")
    eng_dept = next(d for d in depts if d["name"] == "Engineering")
    qa_dept = next(d for d in depts if d["name"] == "Judging")

    # -------------------------------------------------------------------------
    # Step 3: Provision Digital CEO, HR Executive, and Verifier
    # -------------------------------------------------------------------------
    ceo_res = await client.post(
        "/agents",
        headers=owner_headers,
        json={
            "display_name": "Digital CEO",
            "role": "CEO",
            "department_id": exec_dept["id"],
            "system_prompt_version": "1.0.0",
        },
    )
    assert ceo_res.status_code == 200
    ceo_data = ceo_res.json()
    ceo_id = uuid.UUID(ceo_data["id"])

    hr_res = await client.post(
        "/agents",
        headers=owner_headers,
        json={
            "display_name": "HR Talent Executive",
            "role": "HR",
            "department_id": exec_dept["id"],
            "system_prompt_version": "1.0.0",
        },
    )
    assert hr_res.status_code == 200
    hr_data = hr_res.json()
    hr_id = uuid.UUID(hr_data["id"])

    verifier_res = await client.post(
        "/agents",
        headers=owner_headers,
        json={
            "display_name": "Senior Verifier",
            "role": "VERIFIER",
            "department_id": qa_dept["id"],
            "system_prompt_version": "1.0.0",
        },
    )
    assert verifier_res.status_code == 200
    verifier_data = verifier_res.json()
    verifier_id = uuid.UUID(verifier_data["id"])

    # Verify agent token creation and claims
    ceo_token = create_agent_token(ceo_id, "CEO", jwt_secret, uuid.UUID(exec_dept["id"]))
    ceo_claims = validate_access_token(ceo_token, jwt_secret)
    assert ceo_claims.sub == ceo_id
    assert ceo_claims.role == "CEO"

    # -------------------------------------------------------------------------
    # Step 4: Establish & Approve Cross-Department Bridge (Executive -> Engineering)
    # -------------------------------------------------------------------------
    bridge_expiry = (datetime.now(UTC) + timedelta(days=7)).isoformat()
    bridge_req = await client.post(
        "/bridges",
        headers=owner_headers,
        json={
            "source_department_id": exec_dept["id"],
            "target_department_id": eng_dept["id"],
            "purpose": "Executive Mission Delegation to Engineering",
            "allowed_data_classification": "INTERNAL",
            "expires_at": bridge_expiry,
        },
    )
    assert bridge_req.status_code == 200
    bridge_id = bridge_req.json()["id"]

    bridge_appr = await client.post(
        f"/bridges/{bridge_id}/approve",
        headers=owner_headers,
        json={"reason": "Approved cross-department mission delegation"},
    )
    assert bridge_appr.status_code == 200
    assert bridge_appr.json()["status"] == "ACTIVE"

    # -------------------------------------------------------------------------
    # Step 5: Owner Creates Strategic Mission Task
    # -------------------------------------------------------------------------
    mission_res = await client.post(
        "/tasks",
        headers=owner_headers,
        json={
            "title": "Build Core Governance Telemetry Engine",
            "description": "Architect and implement telemetry data pipeline within engineering",
            "priority": "HIGH",
            "origin_department_id": exec_dept["id"],
            "assigned_department_id": eng_dept["id"],
            "budget_allocated": 5000.0,
        },
    )
    assert mission_res.status_code == 200
    mission = mission_res.json()
    mission_id = uuid.UUID(mission["id"])

    # -------------------------------------------------------------------------
    # Step 6: CEO Evaluates Mission and Delegates Staffing to HR
    # -------------------------------------------------------------------------
    provider = DeterministicAgentProvider()
    ceo_agent = await db_session.get(Agent, ceo_id)
    mission_task = await db_session.get(Task, mission_id)

    ceo_result = await run_agent_cycle(
        session=db_session,
        agent=ceo_agent,
        provider=provider,
        task=mission_task,
        context_data={"action_key": "CEO"},
    )
    assert ceo_result.success is True
    assert ceo_result.decision.decision == AgentDecisionType.DELEGATE
    assert ceo_result.decision.target_role == "HR"
    assert ceo_result.usage.total_tokens > 0

    # -------------------------------------------------------------------------
    # Step 7: HR Provisions Worker in Engineering
    # -------------------------------------------------------------------------
    # Verify permission check: HR role is authorized to create worker
    hr_auth = await authorize(
        actor_id=hr_id,
        actor_role="HR",
        actor_status="ACTIVE",
        action="create_worker",
        resource="agents",
    )
    assert hr_auth.decision == Decision.ALLOW

    worker_res = await client.post(
        "/agents",
        headers=owner_headers,
        json={
            "display_name": "Pipeline Builder Worker",
            "role": "WORKER",
            "department_id": eng_dept["id"],
            "system_prompt_version": "1.0.0",
        },
    )
    assert worker_res.status_code == 200
    worker_data = worker_res.json()
    worker_id = uuid.UUID(worker_data["id"])

    # -------------------------------------------------------------------------
    # Step 8: Grant Scoped Permissions to Worker
    # -------------------------------------------------------------------------
    grant = PermissionGrant(
        id=uuid.uuid4(),
        agent_id=worker_id,
        department_id=uuid.UUID(eng_dept["id"]),
        task_id=mission_id,
        allowed_actions=["execute_task", "execute_tool"],
        allowed_tools=["file_reader"],
        memory_scopes=["engineering_workspace"],
        budget_limit=1000.0,
        issued_by=test_owner_id,
        created_at=datetime.now(UTC),
    )
    db_session.add(grant)
    await db_session.flush()

    # -------------------------------------------------------------------------
    # Step 9: Assign Task to Worker and Begin Execution
    # -------------------------------------------------------------------------
    assign_res = await client.post(
        f"/tasks/{mission_id}/assign?agent_id={worker_id}",
        headers=owner_headers,
    )
    assert assign_res.status_code == 200
    assert assign_res.json()["status"] == TaskStatus.ASSIGNED.value

    prog_res = await client.post(
        f"/tasks/{mission_id}/transition",
        headers=owner_headers,
        json={"status": "IN_PROGRESS", "reason": "Worker started telemetry pipeline design"},
    )
    assert prog_res.status_code == 200

    # -------------------------------------------------------------------------
    # Step 10: Worker Executes Tool via Tool Gateway
    # -------------------------------------------------------------------------
    worker_agent = await db_session.get(Agent, worker_id)
    worker_result = await run_agent_cycle(
        session=db_session,
        agent=worker_agent,
        provider=provider,
        task=mission_task,
        context_data={"action_key": "WORKER"},
    )
    assert worker_result.success is True
    assert worker_result.decision.decision == AgentDecisionType.EXECUTE_TOOL
    assert worker_result.tool_output is not None
    assert "Mock sandboxed content" in worker_result.tool_output["content"]

    # -------------------------------------------------------------------------
    # Step 11: Task Implementation Done -> Moved to Awaiting Review with Artifacts
    # -------------------------------------------------------------------------
    comp_res = await client.post(
        f"/tasks/{mission_id}/transition",
        headers=owner_headers,
        json={
            "status": "AWAITING_REVIEW",
            "reason": "Telemetry pipeline implemented and verified locally",
            "output_artifacts": {
                "spec": "Telemetry Engine Spec v1.0",
                "code_repo": "git://repos/telemetry-pipeline.git",
            },
        },
    )
    assert comp_res.status_code == 200
    assert comp_res.json()["status"] == TaskStatus.AWAITING_REVIEW.value

    # -------------------------------------------------------------------------
    # Step 12: Independent Verifier Evaluates Work (Conflict Check Enforced)
    # -------------------------------------------------------------------------
    # Conflict check: Worker cannot verify own work!
    self_verify = await authorize(
        actor_id=worker_id,
        actor_role="WORKER",
        actor_status="ACTIVE",
        action="verify_task",
        resource=f"task:{mission_id}",
        target_author_id=worker_id,  # Same author
    )
    assert self_verify.decision == Decision.DENY
    assert self_verify.reason == "cannot_approve_own_output"

    # Independent Verifier is authorized
    verifier_auth = await authorize(
        actor_id=verifier_id,
        actor_role="VERIFIER",
        actor_status="ACTIVE",
        action="verify_task",
        resource=f"task:{mission_id}",
        target_author_id=worker_id,  # Different author
    )
    assert verifier_auth.decision == Decision.ALLOW

    verifier_agent = await db_session.get(Agent, verifier_id)
    verifier_result = await run_agent_cycle(
        session=db_session,
        agent=verifier_agent,
        provider=provider,
        task=mission_task,
        context_data={"action_key": "VERIFIER"},
    )
    assert verifier_result.success is True
    assert verifier_result.decision.decision == AgentDecisionType.COMPLETE_TASK
    assert verifier_result.decision.output_payload["verified"] is True

    # Transition task from AWAITING_REVIEW to COMPLETED upon successful verification
    verify_trans = await client.post(
        f"/tasks/{mission_id}/transition",
        headers=owner_headers,
        json={"status": "COMPLETED", "reason": "Verified by independent QA Verifier"},
    )
    assert verify_trans.status_code == 200
    assert verify_trans.json()["status"] == TaskStatus.COMPLETED.value

    # -------------------------------------------------------------------------
    # Step 13: Release Queue Approval by System Owner
    # -------------------------------------------------------------------------
    approval_entry = await create_approval(
        session=db_session,
        data=ApprovalCreate(
            action_type="RELEASE_PRODUCTION_PIPELINE",
            risk_level=RiskLevel.MEDIUM,
            target_id=mission_id,
            task_id=mission_id,
            requested_by=worker_id,
            reason="Release telemetry pipeline to production",
        ),
    )
    assert approval_entry.status == ApprovalStatus.PENDING

    # Owner reviews and approves release
    decided_approval = await decide_approval(
        session=db_session,
        approval_id=approval_entry.id,
        decision=ApprovalStatus.APPROVED,
        decided_by=test_owner_id,
        decider_role="OWNER",
        reason="Owner verified architecture and test coverage passed",
    )
    assert decided_approval.status == ApprovalStatus.APPROVED
    assert decided_approval.decided_by == test_owner_id

    # -------------------------------------------------------------------------
    # Step 14: Audit Verification Across All Actors
    # -------------------------------------------------------------------------
    audit_res = await db_session.execute(select(AuditEvent).order_by(AuditEvent.timestamp.desc()))
    events = audit_res.scalars().all()
    roles_in_audit = {e.actor_role for e in events if e.actor_role}

    assert "OWNER" in roles_in_audit
    assert "CEO" in roles_in_audit
    assert "WORKER" in roles_in_audit
    assert "VERIFIER" in roles_in_audit

    # -------------------------------------------------------------------------
    # Step 15: Revoking Worker Immediately Blocks Tool Execution
    # -------------------------------------------------------------------------
    grant.revoked_at = datetime.now(UTC)
    grant.revocation_reason = "Mission cycle ended, access revoked"
    await db_session.flush()

    # Worker attempts tool execution after grant revocation -> Must Fail!
    blocked_req = ToolExecutionRequest(
        agent_id=worker_id,
        tool_name="file_reader",
        parameters={"path": "policies/constitution.yaml"},
        task_id=mission_id,
    )
    with pytest.raises(ToolGatewayError) as exc_info:
        await execute_tool(
            session=db_session,
            request=blocked_req,
            actor_id=worker_id,
            actor_role="WORKER",
        )
    assert exc_info.value.status_code == 403
    assert "lacking permission grant" in exc_info.value.message
