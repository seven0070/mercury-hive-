"""Unit tests for Milestone 3 (R3): External Integration Webhook Security & Idempotency.

Verifies:
- HMAC-SHA256 signature verification (constant-time comparison, invalid/missing rejection)
- Timestamp freshness window (<= 300s) and nonce uniqueness replay prevention
- Idempotency key tracking and response caching (at-most-once processing)
- Outbound exponential backoff with randomized jitter
- Inbound POST /tribe/webhook endpoint security and response semantics
"""

import hashlib
import hmac
import time
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from apps.api.config import RuntimeSettings
from services.tribe.router import (
    get_webhook_execution_count,
    reset_webhook_execution_count,
)
from services.tribe.router import (
    router as tribe_router,
)
from services.tribe.security import (
    IdempotencyStatus,
    IdempotencyTracker,
    clear_nonce_cache,
    get_cached_idempotent_response,
    idempotency_tracker,
    retry_external_sync,
    store_idempotent_response,
    verify_timestamp_and_nonce,
    verify_webhook_signature,
)

TEST_SECRET = "test-tribe-webhook-secret-1234567890"


def generate_hmac_header(
    raw_body: bytes,
    secret: str = TEST_SECRET,
    prefix: str = "sha256=",
) -> str:
    """Helper to generate HMAC-SHA256 signature header."""
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return f"{prefix}{digest}" if prefix else digest


@pytest.fixture(autouse=True)
def clean_security_state():
    """Ensure clean security caches before and after each test."""
    clear_nonce_cache()
    idempotency_tracker.clear()
    reset_webhook_execution_count()
    yield
    clear_nonce_cache()
    idempotency_tracker.clear()
    reset_webhook_execution_count()


@pytest.fixture
def runtime_settings() -> RuntimeSettings:
    """Create test RuntimeSettings with configured webhook secret."""
    return RuntimeSettings(
        database_url="postgresql+asyncpg://mercury_runtime:test@localhost:5432/test_db",
        jwt_secret_key="test-secret-key-minimum-32-characters-required-for-jwt",
        tribe_webhook_secret=SecretStr(TEST_SECRET),
    )


@pytest.fixture
def app(runtime_settings: RuntimeSettings) -> FastAPI:
    """Create test FastAPI application hosting the Tribe router."""
    test_app = FastAPI()
    test_app.state.settings = runtime_settings
    test_app.include_router(tribe_router)
    return test_app


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Provide AsyncClient connected to the test application."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


# =====================================================================
# 1. HMAC-SHA256 Signature Verification Tests
# =====================================================================


def test_hmac_signature_verification_success():
    """Valid HMAC signature matches computed digest using constant-time comparison."""
    body = b'{"event": "task.created", "external_id": "ext-101"}'
    sig_standard = generate_hmac_header(body, TEST_SECRET, prefix="sha256=")
    sig_raw = generate_hmac_header(body, TEST_SECRET, prefix="")
    sig_colon = generate_hmac_header(body, TEST_SECRET, prefix="sha256:")

    assert verify_webhook_signature(body, sig_standard, TEST_SECRET) is True
    assert verify_webhook_signature(body, sig_raw, TEST_SECRET) is True
    assert verify_webhook_signature(body, sig_colon, TEST_SECRET) is True


def test_hmac_signature_verification_invalid():
    """Invalid signature, wrong secret, or tampered payload returns False."""
    body = b'{"event": "task.created", "amount": 100}'
    sig = generate_hmac_header(body, TEST_SECRET)

    # Wrong secret
    assert verify_webhook_signature(body, sig, "wrong-secret-key") is False

    # Tampered body
    tampered_body = b'{"event": "task.created", "amount": 9999}'
    assert verify_webhook_signature(tampered_body, sig, TEST_SECRET) is False

    # Corrupt signature string
    assert verify_webhook_signature(body, "sha256=invalidhex0000", TEST_SECRET) is False


def test_hmac_signature_verification_missing_or_empty():
    """Missing, empty, or None signature/secret returns False."""
    body = b'{"test": 1}'
    assert verify_webhook_signature(body, None, TEST_SECRET) is False
    assert verify_webhook_signature(body, "", TEST_SECRET) is False
    assert verify_webhook_signature(body, "   ", TEST_SECRET) is False
    assert verify_webhook_signature(body, "sha256=", TEST_SECRET) is False
    assert verify_webhook_signature(body, "sha256=valid", "") is False


# =====================================================================
# 2. Timestamp Freshness and Nonce Replay Prevention Tests
# =====================================================================


def test_timestamp_and_nonce_valid():
    """Fresh timestamp within 300s and unique nonce succeeds."""
    now = time.time()
    nonce = str(uuid.uuid4())

    is_valid, reason = verify_timestamp_and_nonce(
        timestamp_str=str(int(now)),
        nonce=nonce,
        tolerance_seconds=300,
        current_time=now,
    )
    assert is_valid is True
    assert reason == "valid"


def test_timestamp_expired_rejection():
    """Timestamp older than tolerance (> 300s) is rejected."""
    now = 1700000000.0
    expired_ts = now - 301.0  # 301 seconds old
    nonce = str(uuid.uuid4())

    is_valid, reason = verify_timestamp_and_nonce(
        timestamp_str=str(int(expired_ts)),
        nonce=nonce,
        tolerance_seconds=300,
        current_time=now,
    )
    assert is_valid is False
    assert "timestamp_expired" in reason


def test_future_timestamp_beyond_tolerance_rejection():
    """Timestamp far in the future (> 300s clock drift) is rejected."""
    now = 1700000000.0
    future_ts = now + 350.0
    nonce = str(uuid.uuid4())

    is_valid, reason = verify_timestamp_and_nonce(
        timestamp_str=str(int(future_ts)),
        nonce=nonce,
        tolerance_seconds=300,
        current_time=now,
    )
    assert is_valid is False
    assert "timestamp_expired" in reason


def test_nonce_replay_rejection():
    """Replaying the same nonce within the freshness window is rejected."""
    now = 1700000000.0
    nonce = "fixed-nonce-xyz"

    # First attempt with this nonce succeeds
    is_valid_1, _ = verify_timestamp_and_nonce(
        timestamp_str=str(int(now)),
        nonce=nonce,
        tolerance_seconds=300,
        current_time=now,
    )
    assert is_valid_1 is True

    # Immediate replay with same nonce fails
    is_valid_2, reason_2 = verify_timestamp_and_nonce(
        timestamp_str=str(int(now + 10)),
        nonce=nonce,
        tolerance_seconds=300,
        current_time=now + 10,
    )
    assert is_valid_2 is False
    assert reason_2 == "nonce_replayed"


def test_missing_or_malformed_timestamp_and_nonce():
    """Missing or malformed timestamp or nonce are cleanly rejected."""
    now = time.time()
    nonce = "nonce-1"

    # Missing timestamp
    is_valid, reason = verify_timestamp_and_nonce(None, nonce)
    assert is_valid is False
    assert reason == "missing_timestamp"

    # Invalid timestamp format
    is_valid, reason = verify_timestamp_and_nonce("not-a-number", nonce)
    assert is_valid is False
    assert reason == "invalid_timestamp"

    # Missing nonce
    is_valid, reason = verify_timestamp_and_nonce(str(int(now)), None)
    assert is_valid is False
    assert reason == "missing_nonce"

    is_valid, reason = verify_timestamp_and_nonce(str(int(now)), "   ")
    assert is_valid is False
    assert reason == "missing_nonce"


# =====================================================================
# 3. Idempotency Tracking & Response Cache Tests
# =====================================================================


def test_idempotency_tracker_lifecycle():
    """IdempotencyTracker tracks in-flight and completed requests."""
    tracker = IdempotencyTracker()
    key = "idemp-test-123"

    # Initially empty
    assert tracker.get(key) is None
    assert tracker.get_cached_response(key) is None

    # Start processing acquires the key
    assert tracker.start_processing(key) is True
    rec = tracker.get(key)
    assert rec is not None
    assert rec.status == IdempotencyStatus.PROCESSING

    # Concurrent start on same key is denied
    assert tracker.start_processing(key) is False

    # Complete processing stores cached status code and payload
    payload = {"status": "ok", "task_id": "task-abc"}
    tracker.complete_processing(key, status_code=200, response_data=payload)

    cached = tracker.get_cached_response(key)
    assert cached is not None
    status_code, cached_payload = cached
    assert status_code == 200
    assert cached_payload == payload

    # Start processing on completed key is denied
    assert tracker.start_processing(key) is False


def test_idempotency_tracker_failure_recovery():
    """Failure releases the key so subsequent retries can proceed."""
    tracker = IdempotencyTracker()
    key = "fail-test-key"

    assert tracker.start_processing(key) is True
    tracker.fail_processing(key)
    assert tracker.get(key) is None

    # Can now be acquired again
    assert tracker.start_processing(key) is True


def test_module_level_idempotency_helpers():
    """Verify module-level helpers get_cached_idempotent_response and store_idempotent_response."""
    key = "helper-key-99"
    assert get_cached_idempotent_response(key) is None

    data = {"result": "ingested"}
    store_idempotent_response(key, response=data, status_code=200)

    cached = get_cached_idempotent_response(key)
    assert cached == data


# =====================================================================
# 4. Outbound Exponential Backoff & Jitter Tests
# =====================================================================


@pytest.mark.asyncio
async def test_retry_external_sync_success_first_attempt():
    """Call succeeds on first attempt without any sleep or retry."""
    mock_func = AsyncMock(return_value={"synced": True})
    mock_sleep = AsyncMock()

    result = await retry_external_sync(
        mock_func,
        max_retries=3,
        initial_delay=0.5,
        sleep_fn=mock_sleep,
    )

    assert result == {"synced": True}
    assert mock_func.call_count == 1
    assert mock_sleep.call_count == 0


@pytest.mark.asyncio
async def test_retry_external_sync_backoff_and_jitter():
    """Transient failures trigger exponential backoff with jitter and succeed eventually."""
    attempts = 0

    async def flaky_call(val: int) -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionResetError(f"Network glitch attempt {attempts}")
        return f"success-{val}"

    delays: list[float] = []

    async def recording_sleep(d: float) -> None:
        delays.append(d)

    result = await retry_external_sync(
        flaky_call,
        42,
        max_retries=3,
        initial_delay=1.0,
        backoff_factor=2.0,
        jitter=True,
        jitter_factor=0.1,
        sleep_fn=recording_sleep,
    )

    assert result == "success-42"
    assert attempts == 3
    assert len(delays) == 2

    # Delay 1: baseline 1.0, with +/- 10% jitter -> [0.9, 1.1]
    assert 0.89 <= delays[0] <= 1.11
    # Delay 2: baseline 2.0, with +/- 10% jitter -> [1.8, 2.2]
    assert 1.79 <= delays[1] <= 2.21


@pytest.mark.asyncio
async def test_retry_external_sync_exhausted_raises():
    """Permanent failure raises after exhausting max_retries."""
    mock_func = AsyncMock(side_effect=TimeoutError("Remote service unreachable"))
    mock_sleep = AsyncMock()

    with pytest.raises(TimeoutError, match="Remote service unreachable"):
        await retry_external_sync(
            mock_func,
            max_retries=2,
            initial_delay=0.1,
            sleep_fn=mock_sleep,
        )

    assert mock_func.call_count == 3  # Initial + 2 retries
    assert mock_sleep.call_count == 2


# =====================================================================
# 5. POST /tribe/webhook HTTP Endpoint Integration Tests
# =====================================================================


@pytest.mark.asyncio
async def test_webhook_missing_signature_returns_401(client: AsyncClient):
    """Missing HMAC signature header returns 401 Unauthorized."""
    body = b'{"event": "ping"}'
    response = await client.post(
        "/tribe/webhook",
        content=body,
        headers={
            "X-Webhook-Timestamp": str(int(time.time())),
            "X-Webhook-Nonce": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 401
    assert "Missing HMAC signature" in response.json()["detail"]


@pytest.mark.asyncio
async def test_webhook_invalid_signature_returns_401(client: AsyncClient):
    """Invalid HMAC signature returns 401 Unauthorized."""
    body = b'{"event": "task.created"}'
    invalid_sig = "sha256=" + "a" * 64
    response = await client.post(
        "/tribe/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": invalid_sig,
            "X-Webhook-Timestamp": str(int(time.time())),
            "X-Webhook-Nonce": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 401
    assert "Invalid HMAC signature" in response.json()["detail"]


@pytest.mark.asyncio
async def test_webhook_valid_signature_succeeds_200(client: AsyncClient):
    """Valid HMAC signature and timestamp succeeds with HTTP 200."""
    body = b'{"event": "task.sync", "source": "jira", "id": "TASK-100"}'
    sig = generate_hmac_header(body, TEST_SECRET)
    ts = str(int(time.time()))
    nonce = str(uuid.uuid4())

    response = await client.post(
        "/tribe/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": sig,
            "X-Webhook-Timestamp": ts,
            "X-Webhook-Nonce": nonce,
            "Idempotency-Key": "idemp-success-01",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processed"
    assert data["idempotency_key"] == "idemp-success-01"
    assert data["event"] == "task.sync"
    assert get_webhook_execution_count() == 1


@pytest.mark.asyncio
async def test_webhook_expired_timestamp_rejected_400(client: AsyncClient):
    """Webhook with timestamp older than 300 seconds is rejected with HTTP 400."""
    body = b'{"event": "task.sync"}'
    sig = generate_hmac_header(body, TEST_SECRET)
    expired_ts = str(int(time.time()) - 350)
    nonce = str(uuid.uuid4())

    response = await client.post(
        "/tribe/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": sig,
            "X-Webhook-Timestamp": expired_ts,
            "X-Webhook-Nonce": nonce,
        },
    )
    assert response.status_code == 400
    assert "Replay attack prevented: timestamp_expired" in response.json()["detail"]
    assert get_webhook_execution_count() == 0


@pytest.mark.asyncio
async def test_webhook_replayed_nonce_rejected_400(client: AsyncClient):
    """Webhook replaying an already observed nonce is rejected with HTTP 400."""
    body = b'{"event": "task.sync"}'
    sig = generate_hmac_header(body, TEST_SECRET)
    ts = str(int(time.time()))
    replayed_nonce = "replayed-nonce-12345"

    # Request 1: Succeeds
    res1 = await client.post(
        "/tribe/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": sig,
            "X-Webhook-Timestamp": ts,
            "X-Webhook-Nonce": replayed_nonce,
        },
    )
    assert res1.status_code == 200

    # Request 2: Different idempotency key or no idempotency key, but same nonce replayed
    res2 = await client.post(
        "/tribe/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": sig,
            "X-Webhook-Timestamp": ts,
            "X-Webhook-Nonce": replayed_nonce,
        },
    )
    assert res2.status_code == 400
    assert "Replay attack prevented: nonce_replayed" in res2.json()["detail"]


@pytest.mark.asyncio
async def test_webhook_duplicate_idempotency_key_returns_cached_response_no_reexecution(
    client: AsyncClient,
):
    """Duplicate idempotency key returns cached response with 200 without re-executing logic."""
    body = b'{"event": "critical.task.assign", "task_id": "T-500", "payload_data": "secret"}'
    sig = generate_hmac_header(body, TEST_SECRET)
    ts = str(int(time.time()))
    nonce1 = str(uuid.uuid4())
    idempotency_key = "idemp-fixed-single-execution-key"

    # 1. First execution
    res1 = await client.post(
        "/tribe/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": sig,
            "X-Webhook-Timestamp": ts,
            "X-Webhook-Nonce": nonce1,
            "Idempotency-Key": idempotency_key,
        },
    )
    assert res1.status_code == 200
    initial_content = res1.json()
    assert initial_content["status"] == "processed"
    assert get_webhook_execution_count() == 1

    # 2. Replayed execution (can have replayed nonce / old timestamp)
    # The endpoint MUST return the cached response with HTTP 200 without re-executing logic!
    nonce2 = str(uuid.uuid4())
    res2 = await client.post(
        "/tribe/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": sig,
            "X-Webhook-Timestamp": ts,
            "X-Webhook-Nonce": nonce2,
            "Idempotency-Key": idempotency_key,
        },
    )
    assert res2.status_code == 200
    cached_content = res2.json()

    # Verify identical response content
    assert cached_content == initial_content
    # CRITICAL: Verify business logic was NOT re-executed! Execution count remains exactly 1.
    assert get_webhook_execution_count() == 1
