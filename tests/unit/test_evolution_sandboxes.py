"""Unit tests for Phase 7: Controlled Evolution, Sandboxes, and Shadow Deployments."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.enums.agent_status import AgentStatus
from domain.enums.evolution import EvolutionStatus, EvolutionType, SandboxVerdict
from domain.enums.roles import SystemRole
from domain.models.agents import Agent
from domain.models.evolution import EvolutionCandidate, SandboxRun
from domain.schemas.evolution import EvolutionCandidateCreate
from services.evolution.service import (
    EvolutionError,
    deploy_shadow,
    promote_to_production,
    propose_candidate,
    rollback_candidate,
    run_sandbox_benchmark,
)


@pytest.mark.asyncio
async def test_propose_candidate_inactive_agent():
    """Inactive agent cannot propose an evolution candidate."""
    mock_session = AsyncMock()
    mock_session.execute.return_value = MagicMock()

    proposer_id = uuid.uuid4()
    agent = Agent(
        id=proposer_id,
        display_name="Inactive Agent",
        role=SystemRole.WORKER.value,
        department_id=uuid.uuid4(),
        status=AgentStatus.SUSPENDED.value,
        persona_source="base",
        persona_disclosure="I am AI",
        system_prompt_version="1.0.0",
        created_at=datetime.now(UTC),
    )

    r_agent = MagicMock()
    r_agent.scalar_one_or_none.return_value = agent
    mock_session.execute.return_value = r_agent

    create_data = EvolutionCandidateCreate(
        title="Optimized Prompts",
        evolution_type=EvolutionType.SYSTEM_PROMPT,
        target_identifier="worker_prompt_v2",
        proposed_change={"prompt": "Be super efficient."},
    )

    with pytest.raises(EvolutionError, match="active registered agent"):
        await propose_candidate(mock_session, proposer_id, create_data)


@pytest.mark.asyncio
async def test_propose_candidate_success():
    """Active agent can successfully propose an evolution candidate."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    proposer_id = uuid.uuid4()
    agent = Agent(
        id=proposer_id,
        display_name="Active Worker",
        role=SystemRole.WORKER.value,
        department_id=uuid.uuid4(),
        status=AgentStatus.ACTIVE.value,
        persona_source="base",
        persona_disclosure="I am AI",
        system_prompt_version="1.0.0",
        created_at=datetime.now(UTC),
    )

    r_agent = MagicMock()
    r_agent.scalar_one_or_none.return_value = agent
    mock_session.execute.return_value = r_agent

    create_data = EvolutionCandidateCreate(
        title="Refactored Tool Pipeline",
        evolution_type=EvolutionType.WORKFLOW_PIPELINE,
        target_identifier="data_pipeline_v2",
        proposed_change={"steps": ["extract", "transform", "load"]},
    )

    cand = await propose_candidate(mock_session, proposer_id, create_data)

    assert cand.title == "Refactored Tool Pipeline"
    assert cand.evolution_type == EvolutionType.WORKFLOW_PIPELINE.value
    assert cand.status == EvolutionStatus.PROPOSED.value
    assert cand.shadow_traffic_percentage == 0
    assert mock_session.add.call_count >= 1


@pytest.mark.asyncio
async def test_run_sandbox_benchmark_pass():
    """Candidate with candidate_score >= baseline_score and >= 70 earns PASSED verdict."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    candidate_id = uuid.uuid4()
    candidate = EvolutionCandidate(
        id=candidate_id,
        title="Prompt Tuning",
        evolution_type=EvolutionType.SYSTEM_PROMPT.value,
        target_identifier="support_prompt",
        proposed_change={"prompt": "helpful response"},
        status=EvolutionStatus.PROPOSED.value,
        proposer_agent_id=uuid.uuid4(),
        shadow_traffic_percentage=0,
        created_at=datetime.now(UTC),
    )

    r_cand = MagicMock()
    r_cand.scalar_one_or_none.return_value = candidate
    mock_session.execute.return_value = r_cand

    sandbox_run = await run_sandbox_benchmark(
        session=mock_session,
        candidate_id=candidate_id,
        test_suite_name="qa_eval_suite",
        baseline_score=80.0,
        candidate_score=88.5,
        metrics={"latency_ms": 120},
    )

    assert sandbox_run.verdict == SandboxVerdict.PASSED.value
    assert candidate.status == EvolutionStatus.SANDBOX_TESTING.value
    assert candidate.benchmark_results["verdict"] == SandboxVerdict.PASSED.value


@pytest.mark.asyncio
async def test_run_sandbox_benchmark_regressed():
    """Candidate with lower score than baseline earns REGRESSED verdict."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    candidate_id = uuid.uuid4()
    candidate = EvolutionCandidate(
        id=candidate_id,
        title="Tool optimization",
        evolution_type=EvolutionType.TOOL_DEFINITION.value,
        target_identifier="search_tool",
        proposed_change={"timeout": 5},
        status=EvolutionStatus.SANDBOX_TESTING.value,
        proposer_agent_id=uuid.uuid4(),
        shadow_traffic_percentage=0,
        created_at=datetime.now(UTC),
    )

    r_cand = MagicMock()
    r_cand.scalar_one_or_none.return_value = candidate
    mock_session.execute.return_value = r_cand

    sandbox_run = await run_sandbox_benchmark(
        session=mock_session,
        candidate_id=candidate_id,
        test_suite_name="latency_suite",
        baseline_score=90.0,
        candidate_score=75.0,
    )

    assert sandbox_run.verdict == SandboxVerdict.REGRESSED.value
    assert candidate.benchmark_results["verdict"] == SandboxVerdict.REGRESSED.value


@pytest.mark.asyncio
async def test_deploy_shadow_without_passed_benchmark_fails():
    """Cannot route shadow traffic to a candidate with no passing benchmarks."""
    mock_session = AsyncMock()

    candidate_id = uuid.uuid4()
    candidate = EvolutionCandidate(
        id=candidate_id,
        title="Untested Candidate",
        evolution_type=EvolutionType.SYSTEM_PROMPT.value,
        target_identifier="router_prompt",
        proposed_change={"temperature": 0.2},
        status=EvolutionStatus.SANDBOX_TESTING.value,
        proposer_agent_id=uuid.uuid4(),
        shadow_traffic_percentage=0,
        created_at=datetime.now(UTC),
    )

    r_cand = MagicMock()
    r_cand.scalar_one_or_none.return_value = candidate

    r_runs = MagicMock()
    r_runs.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [r_cand, r_runs]

    with pytest.raises(EvolutionError, match="not achieved any PASSED"):
        await deploy_shadow(mock_session, candidate_id, percentage=15)


@pytest.mark.asyncio
async def test_deploy_shadow_success():
    """Candidate with passing benchmark can be deployed to shadow traffic."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    candidate_id = uuid.uuid4()
    candidate = EvolutionCandidate(
        id=candidate_id,
        title="Passed Candidate",
        evolution_type=EvolutionType.SYSTEM_PROMPT.value,
        target_identifier="router_prompt",
        proposed_change={"temperature": 0.2},
        status=EvolutionStatus.SANDBOX_TESTING.value,
        proposer_agent_id=uuid.uuid4(),
        shadow_traffic_percentage=0,
        created_at=datetime.now(UTC),
    )

    passing_run = SandboxRun(
        id=uuid.uuid4(),
        candidate_id=candidate_id,
        test_suite_name="accuracy_suite",
        baseline_score=85.0,
        candidate_score=92.0,
        verdict=SandboxVerdict.PASSED.value,
        executed_at=datetime.now(UTC),
    )

    r_cand = MagicMock()
    r_cand.scalar_one_or_none.return_value = candidate

    r_runs = MagicMock()
    r_runs.scalars.return_value.all.return_value = [passing_run]

    r_audit = MagicMock()
    r_audit.scalar_one_or_none.return_value = uuid.uuid4()

    mock_session.execute.side_effect = [r_cand, r_runs, r_audit]

    res = await deploy_shadow(mock_session, candidate_id, percentage=20)

    assert res.status == EvolutionStatus.SHADOW_DEPLOYED.value
    assert res.shadow_traffic_percentage == 20


@pytest.mark.asyncio
async def test_promote_to_production_success():
    """Owner promotion sets candidate to PROMOTED and 100% traffic."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    candidate_id = uuid.uuid4()
    owner_id = uuid.uuid4()

    candidate = EvolutionCandidate(
        id=candidate_id,
        title="Candidate For Promotion",
        evolution_type=EvolutionType.POLICY_RULE.value,
        target_identifier="safety_guardrail",
        proposed_change={"rule": "deny_destructive_commands"},
        status=EvolutionStatus.SHADOW_DEPLOYED.value,
        proposer_agent_id=uuid.uuid4(),
        shadow_traffic_percentage=30,
        created_at=datetime.now(UTC),
    )

    passing_run = SandboxRun(
        id=uuid.uuid4(),
        candidate_id=candidate_id,
        test_suite_name="guardrail_suite",
        baseline_score=95.0,
        candidate_score=99.0,
        verdict=SandboxVerdict.PASSED.value,
        executed_at=datetime.now(UTC),
    )

    r_cand = MagicMock()
    r_cand.scalar_one_or_none.return_value = candidate

    r_runs = MagicMock()
    r_runs.scalars.return_value.all.return_value = [passing_run]

    r_audit = MagicMock()
    r_audit.scalar_one_or_none.return_value = uuid.uuid4()

    mock_session.execute.side_effect = [r_cand, r_runs, r_audit]

    promoted = await promote_to_production(
        session=mock_session,
        candidate_id=candidate_id,
        owner_id=owner_id,
        notes="Validated over 72h shadow testing.",
    )

    assert promoted.status == EvolutionStatus.PROMOTED.value
    assert promoted.approved_by == owner_id
    assert promoted.shadow_traffic_percentage == 100
    assert promoted.promoted_at is not None


@pytest.mark.asyncio
async def test_rollback_candidate_success():
    """Rollback resets status to ROLLED_BACK and traffic to 0%."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    candidate_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    candidate = EvolutionCandidate(
        id=candidate_id,
        title="Faulty Candidate",
        evolution_type=EvolutionType.SYSTEM_PROMPT.value,
        target_identifier="support_prompt",
        proposed_change={"prompt": "flawed logic"},
        status=EvolutionStatus.PROMOTED.value,
        proposer_agent_id=uuid.uuid4(),
        shadow_traffic_percentage=100,
        created_at=datetime.now(UTC),
    )

    r_cand = MagicMock()
    r_cand.scalar_one_or_none.return_value = candidate
    mock_session.execute.return_value = r_cand

    reverted = await rollback_candidate(
        session=mock_session,
        candidate_id=candidate_id,
        actor_id=actor_id,
        actor_role="OWNER",
        reason="Spike in user misunderstandings observed.",
    )

    assert reverted.status == EvolutionStatus.ROLLED_BACK.value
    assert reverted.shadow_traffic_percentage == 0
    assert reverted.reversion_reason == "Spike in user misunderstandings observed."
    assert reverted.reverted_at is not None
