"""Model provider abstraction, live HTTP adapters, and cost/token accounting."""

import abc
import asyncio
import json
import os
import re
import secrets
import time
from typing import Any

import httpx
import structlog
from pydantic import SecretStr, ValidationError

from services.agent_runtime.models import (
    AgentDecision,
    AgentDecisionType,
    AgentExecutionContext,
    UsageMetrics,
)
from services.agent_runtime.sanitizer import wrap_tool_result, wrap_untrusted_task

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

# Bounded network timeouts (seconds)
DEFAULT_CONNECT_TIMEOUT: float = 5.0
DEFAULT_READ_TIMEOUT: float = 30.0
DEFAULT_WRITE_TIMEOUT: float = 10.0
DEFAULT_POOL_TIMEOUT: float = 5.0


class ModelProviderError(Exception):
    """Exception raised for provider communication, schema, or timeout failures."""

    def __init__(
        self,
        message: str,
        raw_output: str | None = None,
        metrics: UsageMetrics | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.raw_output = raw_output
        self.metrics = metrics or UsageMetrics()


def extract_json_decision(raw_text: str) -> AgentDecision:
    """Extract and validate AgentDecision JSON from model response text.

    Handles:
    - Markdown code fences (```json ... ``` or ``` ... ```)
    - Surrounding prose or whitespace
    - Strict validation against AgentDecision schema (fail-closed on extra/missing fields)
    """
    if not raw_text or not raw_text.strip():
        raise ModelProviderError("Empty response from model provider", raw_output=raw_text)

    cleaned = raw_text.strip()

    # 1. Check for markdown code fences
    fence_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
    match = fence_pattern.search(cleaned)
    json_candidate = match.group(1).strip() if match else cleaned

    # 2. If not cleanly bounded, find outermost { and }
    if not (json_candidate.startswith("{") and json_candidate.endswith("}")):
        start = json_candidate.find("{")
        end = json_candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            json_candidate = json_candidate[start : end + 1]

    # 3. Parse JSON
    try:
        data = json.loads(json_candidate)
    except json.JSONDecodeError as exc:
        raise ModelProviderError(
            f"Malformed JSON in model output: {exc}",
            raw_output=raw_text,
        ) from exc

    if not isinstance(data, dict):
        raise ModelProviderError(
            f"Expected JSON object in model output, got {type(data).__name__}",
            raw_output=raw_text,
        )

    # 4. Strictly validate schema
    try:
        return AgentDecision.model_validate(data)
    except ValidationError as exc:
        raise ModelProviderError(
            f"Schema validation failed for AgentDecision: {exc}",
            raw_output=raw_text,
        ) from exc


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


class HttpModelProvider(BaseModelProvider):
    """Live-capable HTTP model provider adapter supporting Claude and OpenAI formats.

    Features:
    - Injectable httpx.AsyncClient or transport for mock testing.
    - Bounded connect (5s) and read (30s) timeouts.
    - Exponential backoff retries with jitter on TimeoutException, 5xx, and 429.
    - Exact token usage extraction and USD cost calculation.
    - Fail-closed JSON extraction and schema validation.
    """

    def __init__(
        self,
        model_name: str = "claude-3-5-sonnet",
        api_key: str | SecretStr | None = None,
        api_url: str | None = None,
        timeout: httpx.Timeout | None = None,
        timeout_seconds: float = DEFAULT_READ_TIMEOUT,
        max_retries: int = 3,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        backoff_base_seconds: float = 0.5,
    ):
        super().__init__(
            model_name=model_name,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

        # Unpack SecretStr safely
        if isinstance(api_key, SecretStr):
            self._api_key = api_key.get_secret_value()
        elif api_key is not None:
            self._api_key = str(api_key)
        else:
            if model_name.startswith("claude"):
                self._api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            else:
                self._api_key = os.environ.get("OPENAI_API_KEY", "")

        self.api_url = api_url
        self.backoff_base_seconds = backoff_base_seconds

        # Enforce bounded timeout
        if timeout is not None:
            self.timeout = timeout
        else:
            self.timeout = httpx.Timeout(
                connect=DEFAULT_CONNECT_TIMEOUT,
                read=timeout_seconds,
                write=DEFAULT_WRITE_TIMEOUT,
                pool=DEFAULT_POOL_TIMEOUT,
            )

        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            self._client = httpx.AsyncClient(transport=transport, timeout=self.timeout)
            self._owns_client = True

    async def aclose(self) -> None:
        """Close the underlying client session if owned."""
        if self._owns_client and self._client:
            await self._client.aclose()

    async def __aenter__(self) -> "HttpModelProvider":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.aclose()

    def _get_backoff_delay(self, attempt: int) -> float:
        """Compute exponential backoff delay with jitter."""
        base = self.backoff_base_seconds * (2 ** (attempt - 1))
        jitter = secrets.SystemRandom().uniform(0.0, 0.05) if base > 0 else 0.0
        return base + jitter

    def _format_user_message(self, execution_context: AgentExecutionContext) -> str:
        """Format the execution context into an untrusted-safe structured user prompt."""
        parts = [
            f"Agent Role: {execution_context.agent_role}",
            f"Agent ID: {execution_context.agent_id}",
        ]
        if execution_context.department_id:
            parts.append(f"Department ID: {execution_context.department_id}")
        if execution_context.task_id:
            parts.append(f"Task ID: {execution_context.task_id}")

        if execution_context.context_data:
            task_desc = execution_context.context_data.get("task_description")
            task_title = execution_context.context_data.get("task_title")
            if task_desc:
                parts.append(wrap_untrusted_task(task_desc, task_title))

            tool_output = execution_context.context_data.get("tool_output")
            if tool_output:
                parts.append(wrap_tool_result("previous_tool", tool_output))

            other_data = {
                k: v
                for k, v in execution_context.context_data.items()
                if k not in ("task_description", "task_title", "tool_output")
            }
            if other_data:
                meta_json = json.dumps(other_data, default=str)
                parts.append(f"<context_metadata>\n{meta_json}\n</context_metadata>")

        parts.append(
            "Instructions: Formulate your next decision strictly matching the "
            "AgentDecision JSON schema. Output ONLY the JSON object without any commentary."
        )
        return "\n\n".join(parts)

    def _prepare_request(
        self,
        system_prompt: str,
        user_message: str,
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        """Prepare URL, headers, and payload according to model provider format."""
        is_anthropic = self.model_name.startswith("claude")

        if is_anthropic:
            url = self.api_url or "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": self._api_key or "",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            payload = {
                "model": self.model_name,
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_message}],
            }
        else:
            url = self.api_url or "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self._api_key or ''}",
                "content-type": "application/json",
            }
            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            }

        return url, headers, payload

    def _parse_response_content_and_tokens(
        self,
        response_data: dict[str, Any],
    ) -> tuple[str, int, int]:
        """Extract text content and exact token metrics from API response payload."""
        is_anthropic = self.model_name.startswith("claude")

        if is_anthropic:
            content_blocks = response_data.get("content", [])
            text_blocks = [
                b.get("text", "")
                for b in content_blocks
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            raw_text = "\n".join(text_blocks)
            usage = response_data.get("usage", {})
            prompt_tokens = int(usage.get("input_tokens", 0))
            completion_tokens = int(usage.get("output_tokens", 0))
        else:
            choices = response_data.get("choices", [])
            if choices and isinstance(choices[0], dict):
                raw_text = choices[0].get("message", {}).get("content", "")
            else:
                raw_text = ""
            usage = response_data.get("usage", {})
            prompt_tokens = int(usage.get("prompt_tokens", 0))
            completion_tokens = int(usage.get("completion_tokens", 0))

        return raw_text, prompt_tokens, completion_tokens

    async def generate_decision(
        self,
        system_prompt: str,
        execution_context: AgentExecutionContext,
    ) -> tuple[AgentDecision, UsageMetrics]:
        """Invoke HTTP model API with bounded retries and fail-closed validation."""
        start_time = time.perf_counter()
        user_message = self._format_user_message(execution_context)
        url, headers, payload = self._prepare_request(system_prompt, user_message)

        attempt = 0
        response: httpx.Response | None = None

        while True:
            try:
                response = await self._client.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                break  # Successful HTTP call
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                attempt += 1
                logger.warning(
                    "model_provider_network_retry",
                    model=self.model_name,
                    attempt=attempt,
                    max_retries=self.max_retries,
                    error=str(exc),
                )
                if attempt > self.max_retries:
                    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    raise ModelProviderError(
                        f"Model request timed out after {self.max_retries} retries: {exc}",
                        metrics=UsageMetrics(latency_ms=latency_ms),
                    ) from exc
                await asyncio.sleep(self._get_backoff_delay(attempt))
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status >= 500 or status == 429:
                    attempt += 1
                    logger.warning(
                        "model_provider_http_retry",
                        model=self.model_name,
                        status=status,
                        attempt=attempt,
                        max_retries=self.max_retries,
                    )
                    if attempt > self.max_retries:
                        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
                        raise ModelProviderError(
                            f"Model request failed with status {status} "
                            f"after {self.max_retries} retries",
                            metrics=UsageMetrics(latency_ms=latency_ms),
                        ) from exc
                    await asyncio.sleep(self._get_backoff_delay(attempt))
                else:
                    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    raise ModelProviderError(
                        f"Model HTTP request failed with non-retryable status {status}: "
                        f"{exc.response.text}",
                        metrics=UsageMetrics(latency_ms=latency_ms),
                    ) from exc
            except Exception as exc:
                latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
                raise ModelProviderError(
                    f"Unexpected model provider error: {exc}",
                    metrics=UsageMetrics(latency_ms=latency_ms),
                ) from exc

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        try:
            response_json = response.json()
        except Exception as exc:
            raise ModelProviderError(
                f"Invalid JSON response from provider endpoint: {exc}",
                raw_output=response.text,
                metrics=UsageMetrics(latency_ms=latency_ms),
            ) from exc

        raw_text, prompt_tokens, completion_tokens = (
            self._parse_response_content_and_tokens(response_json)
        )
        total_tokens = prompt_tokens + completion_tokens
        cost_usd = self.compute_cost(prompt_tokens, completion_tokens)

        metrics = UsageMetrics(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=cost_usd,
            latency_ms=latency_ms,
        )

        try:
            decision = extract_json_decision(raw_text)
        except ModelProviderError as exc:
            # Preserve raw output and accumulated metrics for audit
            exc.raw_output = raw_text
            exc.metrics = metrics
            raise exc

        return decision, metrics


class AnthropicModelProvider(HttpModelProvider):
    """Convenience adapter specialized for Anthropic Claude models."""

    def __init__(
        self,
        model_name: str = "claude-3-5-sonnet",
        **kwargs: Any,
    ):
        super().__init__(model_name=model_name, **kwargs)


class OpenAIModelProvider(HttpModelProvider):
    """Convenience adapter specialized for OpenAI GPT models."""

    def __init__(
        self,
        model_name: str = "gpt-4o",
        **kwargs: Any,
    ):
        super().__init__(model_name=model_name, **kwargs)


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
