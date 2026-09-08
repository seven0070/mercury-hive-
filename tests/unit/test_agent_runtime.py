"""Unit tests for AI Agent Runtime, typed schemas, cost accounting, and execution loop."""

import uuid

import pytest
from pydantic import ValidationError

from domain.enums.governance import SystemRunState
from domain.models.agents import Agent
from services.agent_runtime.models import (
    AgentDecision,
    AgentDecisionType,
    AgentExecutionContext,
    UsageMetrics,
)
from services.agent_runtime.prompts import (
    AUTHORITY_HIERARCHY_HEADER,
    get_system_prompt_for_role,
)
from services.agent_runtime.provider import (
    ALLOWED_MODELS,
    DeterministicAgentProvider,
)
from services.agent_runtime.runner import run_agent_cycle


def test_agent_decision_schema_validation():
    """AgentDecision validates structured fields and rejects unknown extra attributes."""
    decision = AgentDecision(
        decision=AgentDecisionType.DELEGATE,
        reason="Delegating engineering tasks to worker agent.",
        target_role="WORKER",
        confidence=0.95,
    )
    assert decision.decision == "delegate"
    assert decision.confidence == 0.95
    assert decision.requires_approval is False

    # Extra fields must be forbidden
    with pytest.raises(ValidationError):
        AgentDecision(
            decision=AgentDecisionType.DELEGATE,
            reason="Invalid decision with extra field",
            unauthorized_mutation="DROP TABLE users;",  # Should trigger extra forbidden
        )


def test_model_provider_allowlist_and_cost_accounting():
    """Provider computes accurate costs and restricts unapproved models."""
    provider = DeterministicAgentProvider(model_name="claude-3-5-sonnet")
    assert provider.model_name in ALLOWED_MODELS

    # 10,000 prompt tokens ($3.00/1M = $0.03) + 2,000 completion tokens ($15.00/1M = $0.03)
    cost = provider.compute_cost(10_000, 2_000)
    assert cost == 0.06

    # Unapproved model must raise ValueError
    with pytest.raises(ValueError, match="not allowed"):
        DeterministicAgentProvider(model_name="unapproved-experimental-model")


def test_authority_hierarchy_prompts():
    """Authority hierarchy is embedded in system prompts for every agent role."""
    for role in ["CEO", "HR", "DEPARTMENT_MANAGER", "WORKER", "VERIFIER"]:
        prompt = get_system_prompt_for_role(role)
        assert AUTHORITY_HIERARCHY_HEADER in prompt
        assert "CONSTITUTION" in prompt
        assert "EXTERNAL DATA" in prompt


@pytest.mark.asyncio
async def test_deterministic_provider_decisions():
    """Deterministic provider returns typed decisions and usage metrics."""
    provider = DeterministicAgentProvider()
    context = AgentExecutionContext(
        agent_id=uuid.uuid4(),
        agent_role="CEO",
        department_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
    )

    decision, metrics = await provider.generate_decision(
        system_prompt="Test CEO Prompt",
        execution_context=context,
    )
    assert isinstance(decision, AgentDecision)
    assert decision.decision == AgentDecisionType.DELEGATE
    assert decision.target_role == "HR"
    assert isinstance(metrics, UsageMetrics)
    assert metrics.total_tokens > 0


@pytest.mark.asyncio
async def test_agent_cycle_emergency_shutdown_blocked():
    """Agent cycle instantly aborts execution if system is in EMERGENCY_SHUTDOWN."""
    provider = DeterministicAgentProvider()
    agent = Agent(
        id=uuid.uuid4(),
        display_name="Engineering Worker",
        role="WORKER",
        status="ACTIVE",
    )

    from unittest.mock import AsyncMock, MagicMock

    mock_result = MagicMock()
    mock_result.fetchone.return_value = [uuid.uuid4()]
    dummy_session = MagicMock()
    dummy_session.execute = AsyncMock(return_value=mock_result)

    result = await run_agent_cycle(
        session=dummy_session,  # type: ignore
        agent=agent,
        provider=provider,
        system_run_state=SystemRunState.EMERGENCY_SHUTDOWN,
    )
    assert result.success is False
    assert "emergency_shutdown_active" in (result.error or "")
