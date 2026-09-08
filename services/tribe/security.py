"""Security, verification, replay prevention, and idempotency for Tribe external webhooks."""

import asyncio
import hashlib
import hmac
import inspect
import secrets
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, TypeVar

import structlog

logger = structlog.get_logger()

T = TypeVar("T")


def verify_webhook_signature(
    raw_body: bytes | str,
    signature_header: str | None,
    secret: str,
) -> bool:
    """Verify HMAC-SHA256 signature for incoming external webhooks using constant-time comparison.

    Accepts signatures formatted as 'sha256=<hex>', 'sha256:<hex>', or raw hex.
    """
    if not signature_header or not secret:
        return False

    if isinstance(raw_body, str):
        raw_body = raw_body.encode("utf-8")

    sig_to_verify = signature_header.strip()
    if sig_to_verify.lower().startswith(("sha256=", "sha256:")):
        sig_to_verify = sig_to_verify[7:].strip()

    if not sig_to_verify:
        return False

    try:
        computed = hmac.new(
            secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(computed.lower(), sig_to_verify.lower())
    except Exception as exc:
        logger.warning("webhook_signature_verification_error", error=str(exc))
        return False


class NonceTracker:
    """Thread-safe in-memory cache tracking observed nonces with TTL pruning."""

    def __init__(self, default_ttl_seconds: int = 600) -> None:
        self._nonces: dict[str, float] = {}
        self._lock = threading.Lock()
        self._default_ttl = default_ttl_seconds

    def prune(self, current_time: float, max_age_seconds: int) -> None:
        """Prune nonces older than max_age_seconds."""
        cutoff = current_time - max_age_seconds
        expired = [n for n, ts in self._nonces.items() if ts < cutoff]
        for n in expired:
            del self._nonces[n]

    def check_and_record(
        self,
        nonce: str,
        current_time: float,
        tolerance_seconds: int = 300,
    ) -> bool:
        """Atomically verify if nonce is unique.

        Returns True if unique and recorded, False if replayed.
        """
        with self._lock:
            self.prune(current_time, tolerance_seconds * 2)
            if nonce in self._nonces:
                return False
            self._nonces[nonce] = current_time
            return True

    def clear(self) -> None:
        """Clear all nonces (useful for testing)."""
        with self._lock:
            self._nonces.clear()


_nonce_tracker = NonceTracker()


def clear_nonce_cache() -> None:
    """Helper to reset nonce tracker cache."""
    _nonce_tracker.clear()


def verify_timestamp_and_nonce(
    timestamp_str: str | int | float | None,
    nonce: str | None,
    tolerance_seconds: int = 300,
    current_time: float | None = None,
) -> tuple[bool, str]:
    """Validate request timestamp freshness and nonce uniqueness against replay attacks.

    Returns:
        tuple[bool, str]: (is_valid, message_or_reason)
    """
    if timestamp_str is None or (isinstance(timestamp_str, str) and not timestamp_str.strip()):
        return False, "missing_timestamp"

    try:
        ts = int(float(str(timestamp_str).strip()))
    except (ValueError, TypeError):
        return False, "invalid_timestamp"

    now = int(current_time if current_time is not None else time.time())
    if abs(now - ts) > tolerance_seconds:
        return False, f"timestamp_expired (diff={abs(now - ts)}s, tolerance={tolerance_seconds}s)"

    if not nonce or not str(nonce).strip():
        return False, "missing_nonce"

    cleaned_nonce = str(nonce).strip()
    is_unique = _nonce_tracker.check_and_record(
        cleaned_nonce,
        current_time=float(now),
        tolerance_seconds=tolerance_seconds,
    )
    if not is_unique:
        return False, "nonce_replayed"

    return True, "valid"


class IdempotencyStatus(StrEnum):
    """Status lifecycle for an idempotency key."""

    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class IdempotencyRecord:
    """Record representing a tracked idempotent request."""

    key: str
    status: IdempotencyStatus
    status_code: int = 200
    response_data: Any = None
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None


class IdempotencyTracker:
    """Thread-safe store for webhook idempotency keys and cached HTTP responses."""

    def __init__(self) -> None:
        self._records: dict[str, IdempotencyRecord] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> IdempotencyRecord | None:
        """Get an existing idempotency record."""
        with self._lock:
            return self._records.get(key)

    def start_processing(self, key: str) -> bool:
        """Attempt to start processing a request under the given idempotency key.

        Returns True if acquired (was not in PROCESSING or COMPLETED), False otherwise.
        """
        with self._lock:
            rec = self._records.get(key)
            if rec and rec.status in (IdempotencyStatus.PROCESSING, IdempotencyStatus.COMPLETED):
                return False
            self._records[key] = IdempotencyRecord(
                key=key,
                status=IdempotencyStatus.PROCESSING,
                created_at=time.time(),
            )
            return True

    def complete_processing(
        self,
        key: str,
        status_code: int,
        response_data: Any,
    ) -> None:
        """Mark an idempotency key as COMPLETED and cache its response."""
        with self._lock:
            rec = self._records.get(key)
            now = time.time()
            if rec:
                rec.status = IdempotencyStatus.COMPLETED
                rec.status_code = status_code
                rec.response_data = response_data
                rec.completed_at = now
            else:
                self._records[key] = IdempotencyRecord(
                    key=key,
                    status=IdempotencyStatus.COMPLETED,
                    status_code=status_code,
                    response_data=response_data,
                    created_at=now,
                    completed_at=now,
                )

    def fail_processing(self, key: str) -> None:
        """Release an in-flight key on error so retries can proceed."""
        with self._lock:
            rec = self._records.get(key)
            if rec and rec.status == IdempotencyStatus.PROCESSING:
                self._records.pop(key, None)

    def get_cached_response(self, key: str) -> tuple[int, Any] | None:
        """Return (status_code, response_data) if key is COMPLETED, else None."""
        with self._lock:
            rec = self._records.get(key)
            if rec and rec.status == IdempotencyStatus.COMPLETED:
                return rec.status_code, rec.response_data
            return None

    def clear(self) -> None:
        """Clear all records (useful for testing)."""
        with self._lock:
            self._records.clear()


idempotency_tracker = IdempotencyTracker()


def get_cached_idempotent_response(idempotency_key: str) -> Any | None:
    """Retrieve cached response data for an idempotency key if completed."""
    res = idempotency_tracker.get_cached_response(idempotency_key)
    return res[1] if res else None


def store_idempotent_response(
    idempotency_key: str,
    response: Any,
    status_code: int = 200,
) -> None:
    """Store cached response data for an idempotency key."""
    idempotency_tracker.complete_processing(idempotency_key, status_code, response)


async def retry_external_sync(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = 3,
    initial_delay: float = 0.5,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    jitter_factor: float = 0.1,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
    **kwargs: Any,
) -> Any:
    """Execute outbound synchronization calls with exponential backoff and jitter on failure.

    Args:
        func: Sync or async callable to execute.
        *args: Positional arguments for func.
        max_retries: Maximum number of retry attempts after initial failure.
        initial_delay: Initial backoff delay in seconds.
        backoff_factor: Multiplier applied per retry attempt.
        jitter: Whether to apply randomized jitter to delay.
        jitter_factor: Fraction of delay to apply as +/- randomized jitter.
        retryable_exceptions: Exceptions that trigger a retry.
        sleep_fn: Sleep function (injectable for instant unit tests).
        **kwargs: Keyword arguments for func.

    Returns:
        Result of func(*args, **kwargs).
    """
    sys_rand = secrets.SystemRandom()
    for attempt in range(max_retries + 1):
        try:
            result = func(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            return result
        except retryable_exceptions as exc:
            if attempt >= max_retries:
                logger.error(
                    "external_sync_retries_exhausted",
                    attempt=attempt,
                    max_retries=max_retries,
                    error=str(exc),
                )
                raise

            delay = initial_delay * (backoff_factor**attempt)
            if jitter and jitter_factor > 0.0:
                jitter_val = sys_rand.uniform(-jitter_factor * delay, jitter_factor * delay)
                delay = max(0.001, delay + jitter_val)

            logger.warning(
                "external_sync_failed_retrying",
                attempt=attempt + 1,
                max_retries=max_retries,
                next_delay=delay,
                error=str(exc),
            )
            await sleep_fn(delay)
