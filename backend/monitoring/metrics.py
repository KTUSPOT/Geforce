import time
from fastapi import Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from backend.cache.manager import cache_manager
from backend.cache.singleflight import single_flight

# Prometheus Metrics Definitions
HTTP_REQUESTS_TOTAL = Counter(
    "ktu_http_requests_total",
    "Total number of HTTP requests processed",
    ["method", "endpoint", "status"]
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "ktu_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["endpoint"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0]
)

CACHE_HITS_TOTAL = Counter(
    "ktu_cache_hits_total",
    "Total cache hits",
    ["tier"]  # l1 or l2
)

CACHE_MISSES_TOTAL = Counter(
    "ktu_cache_misses_total",
    "Total cache misses"
)

SINGLEFLIGHT_SAVED_TOTAL = Counter(
    "ktu_singleflight_coalesced_requests_total",
    "Total database queries prevented by SingleFlight request coalescing"
)

ACTIVE_REQUESTS = Gauge(
    "ktu_active_requests",
    "Number of concurrent active in-flight requests"
)

def export_metrics() -> Response:
    """Generate Prometheus scrape format response."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
