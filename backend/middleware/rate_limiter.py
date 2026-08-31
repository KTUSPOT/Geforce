import time
import logging
from collections import defaultdict
from typing import Dict, List
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from backend.config import settings

logger = logging.getLogger("ktu.ratelimit")

class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    High-Throughput In-Memory Sliding Window Rate Limiter.
    Protects the result API against DDoS, bot scrapers, and malicious flooding.
    """
    def __init__(self, app, requests_per_minute: int = 60, burst_limit: int = 15):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.burst_limit = burst_limit
        self.window_seconds = 60.0
        # Maps client_ip -> list of timestamps
        self.clients: Dict[str, List[float]] = defaultdict(list)
        self._last_cleanup = time.time()

    def _get_client_ip(self, request: Request) -> str:
        # Check X-Forwarded-For if behind Load Balancer / Nginx / Cloudflare
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
        return request.client.host if request.client else "127.0.0.1"

    def _is_rate_limited(self, client_ip: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds
        
        # Clean timestamps older than 60s for this IP
        timestamps = [t for t in self.clients[client_ip] if t > window_start]
        self.clients[client_ip] = timestamps

        # Periodic cleanup of completely stale IPs (every 5 minutes)
        if now - self._last_cleanup > 300:
            stale_ips = [ip for ip, ts in self.clients.items() if not ts or ts[-1] < window_start]
            for ip in stale_ips:
                del self.clients[ip]
            self._last_cleanup = now

        # Check threshold
        if len(timestamps) >= (self.requests_per_minute + self.burst_limit):
            return True
        
        timestamps.append(now)
        return False

    async def dispatch(self, request: Request, call_next):
        # Exclude static assets, health checks, and metrics from rate limiting
        path = request.url.path
        if (
            not settings.RATE_LIMIT_ENABLED or 
            path.startswith("/assets") or 
            path.startswith("/static") or 
            path.startswith("/health") or 
            path == "/metrics" or
            path.startswith("/admin/auth") or
            path == "/" or 
            path == "/admin"
        ):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        if self._is_rate_limited(client_ip):
            logger.warning(f"Rate limit exceeded for IP: {client_ip} on {path}")
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "message": "Too many requests. Please wait a few seconds before trying again.",
                    "retry_after_seconds": 10
                },
                headers={"Retry-After": "10"}
            )

        return await call_next(request)
