"""Sliding-window rate limiter for authentication and sensitive endpoints.

Provides defense against brute-force credential stuffing and denial-of-service.
Thread-safe and asyncio-compatible.
"""

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field

from fastapi import HTTPException, status


@dataclass
class RateLimitWindow:
    """Tracks timestamps of requests within a sliding window."""

    timestamps: list[float] = field(default_factory=list)


class SlidingWindowRateLimiter:
    """In-memory sliding window rate limiter."""

    def __init__(self, max_requests: int = 5, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._records: dict[str, RateLimitWindow] = defaultdict(RateLimitWindow)
        self._locks: dict[asyncio.AbstractEventLoop, asyncio.Lock] = {}
        self._fallback_lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        """Use a lock bound to the current running event loop.

        The same limiter instance can be reused across async test cases and
        multiple event loops; creating one asyncio.Lock at import time binds it to
        the first loop and can deadlock when later methods run under another loop.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            if self._fallback_lock is None:
                self._fallback_lock = asyncio.Lock()
            return self._fallback_lock

        if loop not in self._locks:
            self._locks[loop] = asyncio.Lock()
        return self._locks[loop]

    async def check(self, key: str) -> None:
        """Check if request is allowed for key. Raises 429 if exceeded."""
        now = time.monotonic()
        cutoff = now - self.window_seconds

        async with self._get_lock():
            window = self._records[key]
            # Prune expired timestamps
            window.timestamps = [t for t in window.timestamps if t > cutoff]

            if len(window.timestamps) >= self.max_requests:
                oldest = window.timestamps[0]
                retry_after = int(self.window_seconds - (now - oldest)) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many attempts. Please try again later.",
                    headers={"Retry-After": str(max(1, retry_after))},
                )

    async def record_attempt(self, key: str) -> None:
        """Record an attempt against the rate limit window."""
        now = time.monotonic()
        cutoff = now - self.window_seconds

        async with self._get_lock():
            window = self._records[key]
            window.timestamps = [t for t in window.timestamps if t > cutoff]
            window.timestamps.append(now)

    async def reset(self, key: str) -> None:
        """Reset rate limit history for a key upon successful auth."""
        async with self._get_lock():
            self._records.pop(key, None)

    async def clear_all(self) -> None:
        """Clear all records (primarily for testing)."""
        async with self._get_lock():
            self._records.clear()


# Global rate limiter instances for authentication routes
login_rate_limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60)
refresh_rate_limiter = SlidingWindowRateLimiter(max_requests=20, window_seconds=60)
