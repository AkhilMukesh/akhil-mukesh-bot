import asyncio
import time
from collections import defaultdict, deque


class RateLimitExceeded(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds


class InMemoryRateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()
        self._checks = 0

    async def check(self, client_ip: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        async with self._lock:
            requests = self._requests[client_ip]
            while requests and requests[0] <= cutoff:
                requests.popleft()
            if len(requests) >= self.limit:
                retry_after = max(1, int(requests[0] + self.window_seconds - now))
                raise RateLimitExceeded(retry_after)
            requests.append(now)
            self._checks += 1
            if self._checks % 128 == 0:
                expired_ips = [
                    ip
                    for ip, timestamps in self._requests.items()
                    if not timestamps or timestamps[-1] <= cutoff
                ]
                for ip in expired_ips:
                    del self._requests[ip]
