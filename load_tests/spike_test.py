#!/usr/bin/env python3
"""
KTU High-Performance Load Testing Engine
Simulates massive traffic spikes (1,000 to 50,000+ requests) during result announcements.
Measures Throughput (RPS), Latency Percentiles (P50, P90, P95, P99), and Cache Hit Rates.
"""

import sys
import time
import asyncio
import random
import statistics
from typing import List, Dict, Any
import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://localhost:8000"
EXAM_ID = "BT_S6_MAY26"

# Sample KTU Register Numbers across CET, TKM, GEC, MEC
SAMPLE_REGS = [
    f"TVE21CS{i:03d}" for i in range(1, 61)
] + [
    f"TKM21EC{i:03d}" for i in range(1, 61)
] + [
    f"GEC21ME{i:03d}" for i in range(1, 61)
] + [
    f"MEC21CS{i:03d}" for i in range(1, 61)
]

async def send_single_request(client: httpx.AsyncClient, reg_no: str, client_ip: str = "10.0.1.1") -> Dict[str, Any]:
    url = f"{BASE_URL}/api/v1/results?registerNumber={reg_no}&examId={EXAM_ID}"
    t0 = time.perf_counter()
    try:
        resp = await client.get(url, headers={"X-Forwarded-For": client_ip}, timeout=5.0)
        dur = (time.perf_counter() - t0) * 1000
        is_cached = False
        if resp.status_code == 200:
            data = resp.json()
            is_cached = data.get("cached", False)
        return {
            "status": resp.status_code,
            "duration_ms": dur,
            "cached": is_cached,
            "error": None
        }
    except Exception as e:
        dur = (time.perf_counter() - t0) * 1000
        return {
            "status": 0,
            "duration_ms": dur,
            "cached": False,
            "error": str(e)
        }

async def run_load_test(total_requests: int = 2000, concurrency: int = 100):
    print(f"\n{'='*70}")
    print(f"🚀 KTU Result Application — Traffic Spike Simulator")
    print(f"Target URL:    {BASE_URL}/api/v1/results")
    print(f"Total Queries: {total_requests:,}")
    print(f"Concurrency:   {concurrency} concurrent connections")
    print(f"{'='*70}\n")

    limits = httpx.Limits(max_keepalive_connections=concurrency, max_connections=concurrency * 2)
    async with httpx.AsyncClient(limits=limits) as client:
        # Pre-warm connection pool with 5 initial requests
        for reg in SAMPLE_REGS[:5]:
            await send_single_request(client, reg)

        print(f"⚡ Firing {total_requests:,} queries under high concurrency...")
        sem = asyncio.Semaphore(concurrency)

        async def worker(reg_no, idx):
            client_ip = f"10.0.{idx // 250}.{idx % 250 + 1}"
            async with sem:
                return await send_single_request(client, reg_no, client_ip)

        start_time = time.perf_counter()
        tasks = [worker(random.choice(SAMPLE_REGS), i) for i in range(total_requests)]
        results = await asyncio.gather(*tasks)
        total_time = time.perf_counter() - start_time

    # Calculate statistics
    latencies = [r["duration_ms"] for r in results]
    successes = [r for r in results if r["status"] == 200]
    cached_hits = [r for r in results if r["cached"]]
    errors = [r for r in results if r["status"] != 200]

    latencies.sort()
    p50 = statistics.median(latencies)
    p90 = latencies[int(len(latencies) * 0.90)]
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]
    avg_lat = statistics.mean(latencies)
    rps = total_requests / total_time

    print(f"\n📊 LOAD TEST RESULTS SUMMARY:")
    print(f"{'-'*70}")
    print(f"Total Requests Completed:   {total_requests:,}")
    print(f"Successful (200 OK):        {len(successes):,} ({(len(successes)/total_requests)*100:.1f}%)")
    print(f"Cache Hits:                 {len(cached_hits):,} ({(len(cached_hits)/total_requests)*100:.1f}%)")
    print(f"Failed / Rate Limited:      {len(errors):,}")
    print(f"Total Test Duration:        {total_time:.2f} seconds")
    print(f"Throughput (RPS):           {rps:,.1f} requests/sec")
    print(f"{'-'*70}")
    print(f"LATENCY PERCENTILES:")
    print(f"  • Min:    {min(latencies):.2f} ms")
    print(f"  • P50:    {p50:.2f} ms (50% under this)")
    print(f"  • P90:    {p90:.2f} ms")
    print(f"  • P95:    {p95:.2f} ms")
    print(f"  • P99:    {p99:.2f} ms")
    print(f"  • Max:    {max(latencies):.2f} ms")
    print(f"  • Mean:   {avg_lat:.2f} ms")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    n_req = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    n_con = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    asyncio.run(run_load_test(n_req, n_con))
