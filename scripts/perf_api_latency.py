"""
Lightweight API latency benchmark (in-process ASGI).

Usage:
    python scripts/perf_api_latency.py --requests 20 --concurrency 5
"""

import argparse
import asyncio
import time
from statistics import mean

import httpx

from app.main import app


async def run_benchmark(requests: int, concurrency: int) -> None:
    """Helper for run benchmark."""
    sem = asyncio.Semaphore(concurrency)
    latencies = []

    transport = httpx.ASGITransport(app=app)
    # Use localhost to match ALLOWED_HOSTS in most envs and avoid TrustedHost rejections.
    async with httpx.AsyncClient(
        transport=transport, base_url="http://localhost"
    ) as client:

        async def hit_root():
            async with sem:
                start = time.perf_counter()
                resp = await client.get("/livez")
                elapsed = (time.perf_counter() - start) * 1000
                latencies.append(elapsed)
                resp.raise_for_status()

        await asyncio.gather(*(hit_root() for _ in range(requests)))

    latencies.sort()
    p50 = latencies[int(len(latencies) * 0.5)]
    p95 = latencies[int(len(latencies) * 0.95)]
    print(f"Requests: {requests}, Concurrency: {concurrency}")
    print(f"p50: {p50:.2f} ms, p95: {p95:.2f} ms, avg: {mean(latencies):.2f} ms")


def main():
    """Helper for main."""
    parser = argparse.ArgumentParser(description="In-process API latency benchmark.")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()

    asyncio.run(run_benchmark(args.requests, args.concurrency))


if __name__ == "__main__":
    main()
