"""Autonomous agent execution engine and control plane dispatcher."""

import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums.governance import SystemRunState
from domain.models.agents import Agent
from domain.models.tasks import Task
from domain.schemas.audit import AuditEventCreate
from domain.schemas.tools import ToolExecutionRequest
from services.agent_runtime.models import (
    AgentDecision,
    AgentDecisionType,
    AgentExecutionContext,
    UsageMetrics,
)
from services.agent_runtime.prompts import get_system_prompt_for_role
from services.agent_runtime.provider import BaseModelProvider, ModelProviderError
from services.audit.service import log_audit_event
from services.permissions.engine import Decision, authorize
from services.tools.gateway import ToolGatewayError, execute_tool

logger = structlog.get_logger()


@dataclass(frozen=True)
class AgentExecutionResult:
    """Outcome of a single autonomous agent execution cycle."""

    success: bool
    decision: AgentDecision | None = None
    usage: UsageMetrics = UsageMetrics()
    tool_output: dict[str, Any] | None = None
    error: str | None = None


def _accumulate_task_budget(task: Task | None, cost_usd: float) -> None:
    """Increment task.budget_spent by cycle expenditure if a task is active."""
    if task is not None and cost_usd > 0:
        current_spent = float(task.budget_spent or 0.0)
        task.budget_spent = round(current_spent + cost_usd, 4)


async def run_agent_cycle(
    session: AsyncSession,
    agent: Agent,
    provider: BaseModelProvider,
    task: Task | None = None,
    context_data: dict[str, Any] | None = None,
    system_run_state: SystemRunState = SystemRunState.NORMAL,
) -> AgentExecutionResult:
    """Execute one autonomous cycle for an AI agent through the governed control plane.

    Sequence:
    1. Retrieve authority-hierarchy system prompt for agent's role
    2. Query Model Provider to produce a strictly typed AgentDecision (with graceful degradation)
    3. Evaluate decision against governance permission engine (Control Plane check)
    4. If tool execution is requested, dispatch through Sandboxed Tool Gateway
    5. Log full audit event with actor attribution and token metrics across ALL outcomes
    6. Update task budget accounting if active task is assigned
    7. Return structured result
    """
    correlation_id = uuid.uuid4()
    sys_prompt = get_system_prompt_for_role(agent.role, agent.system_prompt_version)

    # Populate context data with task information if available
    merged_context: dict[str, Any] = dict(context_data or {})
    if task and "task_description" not in merged_context:
        merged_context["task_description"] = task.description
        if task.title:
            merged_context["task_title"] = task.title

    exec_context = AgentExecutionContext(
        agent_id=agent.id,
        agent_role=agent.role,
        department_id=agent.department_id,
        task_id=task.id if task else None,
        system_prompt_version=agent.system_prompt_version,
        context_data=merged_context,
    )

    # 1. Generate typed decision from Model Provider (guarded against network/schema faults)
    try:
        decision, metrics = await provider.generate_decision(sys_prompt, exec_context)
    except (ModelProviderError, Exception) as exc:
        err_msg = str(exc)
        logger.error("agent_cycle_provider_failed", agent_id=str(agent.id), error=err_msg)
        raw_output = getattr(exc, "raw_output", None)
        metrics = getattr(exc, "metrics", UsageMetrics())

        # Audit provider failure per Constitution Rule 10
        await log_audit_event(
            session,
            AuditEventCreate(
                event_type="SYSTEM",
                actor_id=agent.id,
                actor_role=agent.role,
                target_type="TASK" if task else "AGENT",
                target_id=task.id if task else agent.id,
                action="generate_decision",
                decision="ERROR",
                reason=f"Model provider failed: {err_msg}",
                payload={
                    "error": err_msg,
                    "raw_output": raw_output,
                    "prompt_tokens": metrics.prompt_tokens,
                    "completion_tokens": metrics.completion_tokens,
                    "cost_usd": metrics.estimated_cost_usd,
                },
                correlation_id=correlation_id,
            ),
        )
        _accumulate_task_budget(task, metrics.estimated_cost_usd)

        fallback_decision = AgentDecision(
            decision=AgentDecisionType.REJECT_TASK,
            reason=f"Execution aborted due to provider error: {err_msg}",
            confidence=0.0,
        )
        return AgentExecutionResult(
            success=False,
            decision=fallback_decision,
            usage=metrics,
            error=err_msg,
        )

    # Map decision type to action string for permission kernel
    action_map = {
        AgentDecisionType.DELEGATE: "execute_task",
        AgentDecisionType.EXECUTE_TOOL: "execute_tool",
        AgentDecisionType.COMPLETE_TASK: "execute_task",
        AgentDecisionType.REQUEST_APPROVAL: "request_approval",
        AgentDecisionType.REJECT_TASK: "execute_task",
    }
    action_str = action_map.get(decision.decision, "execute_task")

    # 2. Control Plane Authorization Check
    auth_res = await authorize(
        actor_id=agent.id,
        actor_role=agent.role,
        actor_status=agent.status,
        action=action_str,
        resource=f"task:{task.id}" if task else "agent:cycle",
        system_run_state=system_run_state,
        actor_department_id=agent.department_id,
    )

    if auth_res.decision != Decision.ALLOW:
        _accumulate_task_budget(task, metrics.estimated_cost_usd)
        await log_audit_event(
            session,
            AuditEventCreate(
                event_type="GOVERNANCE",
                actor_id=agent.id,
                actor_role=agent.role,
                target_type="TASK" if task else "AGENT",
                target_id=task.id if task else agent.id,
                action=action_str,
                decision="DENY",
                reason=auth_res.reason,
                payload={
                    "decision_type": str(decision.decision),
                    "confidence": decision.confidence,
                    "prompt_tokens": metrics.prompt_tokens,
                    "completion_tokens": metrics.completion_tokens,
                    "cost_usd": metrics.estimated_cost_usd,
                },
                correlation_id=correlation_id,
            ),
        )
        return AgentExecutionResult(
            success=False,
            decision=decision,
            usage=metrics,
            error=f"Control plane blocked action: {auth_res.reason}",
        )

    # 3. Action Dispatch
    tool_result = None
    if decision.decision == AgentDecisionType.EXECUTE_TOOL and decision.requested_tools:
        tool_name = decision.requested_tools[0]
        try:
            tool_req = ToolExecutionRequest(
                agent_id=agent.id,
                tool_name=tool_name,
                parameters=decision.tool_arguments,
                task_id=task.id if task else None,
            )
            exec_record = await execute_tool(
                session=session,
                request=tool_req,
                actor_id=agent.id,
                actor_role=agent.role,
            )
            tool_result = exec_record.result
        except ToolGatewayError as e:
            _accumulate_task_budget(task, metrics.estimated_cost_usd)
            await log_audit_event(
                session,
                AuditEventCreate(
                    event_type="GOVERNANCE",
                    actor_id=agent.id,
                    actor_role=agent.role,
                    target_type="TASK" if task else "AGENT",
                    target_id=task.id if task else agent.id,
                    action=action_str,
                    decision="ERROR",
                    reason=f"Tool execution failed: {e.message}",
                    payload={
                        "decision_type": str(decision.decision),
                        "tool_name": tool_name,
                        "prompt_tokens": metrics.prompt_tokens,
                        "completion_tokens": metrics.completion_tokens,
                        "cost_usd": metrics.estimated_cost_usd,
                    },
                    correlation_id=correlation_id,
                ),
            )
            return AgentExecutionResult(
                success=False,
                decision=decision,
                usage=metrics,
                error=f"Tool execution failed: {e.message}",
            )

    # 4. Audit Successful Agent Decision & Execution
    _accumulate_task_budget(task, metrics.estimated_cost_usd)
    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="GOVERNANCE",
            actor_id=agent.id,
            actor_role=agent.role,
            target_type="TASK" if task else "AGENT",
            target_id=task.id if task else agent.id,
            action=action_str,
            decision="ALLOW",
            reason=decision.reason,
            payload={
                "decision_type": str(decision.decision),
                "confidence": decision.confidence,
                "prompt_tokens": metrics.prompt_tokens,
                "completion_tokens": metrics.completion_tokens,
                "cost_usd": metrics.estimated_cost_usd,
            },
            correlation_id=correlation_id,
        ),
    )

    return AgentExecutionResult(
        success=True,
        decision=decision,
        usage=metrics,
        tool_output=tool_result,
    )
