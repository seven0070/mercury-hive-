"""Model provider abstraction and cost/token accounting."""

import abc
import time

import structlog

from services.agent_runtime.models import (
    AgentDecision,
    AgentDecisionType,
    AgentExecutionContext,
    UsageMetrics,
)

logger = structlog.get_logger()

# Model Pricing per 1,000,000 tokens (USD)
MODEL_PRICING_PER_1M = {
    "claude-3-5-sonnet": {"prompt": 3.00, "completion": 15.00},
    "claude-3-haiku": {"prompt": 0.25, "completion": 1.25},
    "gpt-4o": {"prompt": 5.00, "completion": 15.00},
    "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
    "mock-agent-v1": {"prompt": 0.00, "completion": 0.00},
}

ALLOWED_MODELS = frozenset(MODEL_PRICING_PER_1M.keys())


class ModelProviderError(Exception):
    """Exception raised for provider communication, schema, or timeout failures."""


class BaseModelProvider(abc.ABC):
    """Abstract model provider interface for autonomous agent execution."""

    def __init__(
        self,
        model_name: str = "mock-agent-v1",
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
    ):
        if model_name not in ALLOWED_MODELS:
            models_list = sorted(ALLOWED_MODELS)
            raise ValueError(f"Model '{model_name}' is not allowed. Allowed: {models_list}")
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def compute_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate USD cost based on token counts and model pricing."""
        rates = MODEL_PRICING_PER_1M.get(self.model_name, {"prompt": 0.0, "completion": 0.0})
        prompt_cost = (prompt_tokens / 1_000_000.0) * rates["prompt"]
        completion_cost = (completion_tokens / 1_000_000.0) * rates["completion"]
        return round(prompt_cost + completion_cost, 6)

    @abc.abstractmethod
    async def generate_decision(
        self,
        system_prompt: str,
        execution_context: AgentExecutionContext,
    ) -> tuple[AgentDecision, UsageMetrics]:
        """Invoke the model provider and return a validated, strictly typed AgentDecision."""


class DeterministicAgentProvider(BaseModelProvider):
    """Deterministic, reproducible provider for integration and E2E verification."""

    def __init__(
        self,
        model_name: str = "mock-agent-v1",
        timeout_seconds: float = 30.0,
    ):
        super().__init__(model_name=model_name, timeout_seconds=timeout_seconds)
        self._preset_decisions: dict[str, AgentDecision] = {}

    def register_decision(self, key: str, decision: AgentDecision) -> None:
        """Register a scripted decision for a specific role or context key."""
        self._preset_decisions[key] = decision

    async def generate_decision(
        self,
        system_prompt: str,
        execution_context: AgentExecutionContext,
    ) -> tuple[AgentDecision, UsageMetrics]:
        """Produce a validated decision according to registered rules or role defaults."""
        start_time = time.perf_counter()

        role = execution_context.agent_role
        context_data = execution_context.context_data or {}
        context_key = context_data.get("action_key") or role

        # Check for explicitly registered decision
        if context_key in self._preset_decisions:
            decision = self._preset_decisions[context_key]
        else:
            # Default realistic behavior per role
            if role == "CEO":
                decision = AgentDecision(
                    decision=AgentDecisionType.DELEGATE,
                    reason="Mission parsed. Delegating staffing to HR Executive.",
                    target_role="HR",
                    task_id=str(execution_context.task_id) if execution_context.task_id else None,
                    confidence=0.98,
                )
            elif role == "HR":
                decision = AgentDecision(
                    decision=AgentDecisionType.DELEGATE,
                    reason="Workforce evaluated. Selecting active Engineering worker.",
                    target_role="WORKER",
                    task_id=str(execution_context.task_id) if execution_context.task_id else None,
                    confidence=0.95,
                )
            elif role == "WORKER":
                decision = AgentDecision(
                    decision=AgentDecisionType.EXECUTE_TOOL,
                    reason="Executing task requirement using authorized system tool.",
                    requested_tools=["file_reader"],
                    tool_arguments={"path": "policies/constitution.yaml"},
                    task_id=str(execution_context.task_id) if execution_context.task_id else None,
                    confidence=0.92,
                )
            elif role == "VERIFIER":
                decision = AgentDecision(
                    decision=AgentDecisionType.COMPLETE_TASK,
                    reason="Verification criteria verified: spec fully compliant.",
                    task_id=str(execution_context.task_id) if execution_context.task_id else None,
                    output_payload={"verified": True, "score": 95.0},
                    confidence=0.99,
                )
            else:
                decision = AgentDecision(
                    decision=AgentDecisionType.COMPLETE_TASK,
                    reason=f"Default automated execution step for role {role}.",
                    task_id=str(execution_context.task_id) if execution_context.task_id else None,
                    confidence=0.90,
                )

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        prompt_tokens = len(system_prompt.split()) * 4
        completion_tokens = len(decision.reason.split()) * 4
        total_tokens = prompt_tokens + completion_tokens
        cost = self.compute_cost(prompt_tokens, completion_tokens)

        metrics = UsageMetrics(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=cost,
            latency_ms=latency_ms,
        )

        return decision, metrics
