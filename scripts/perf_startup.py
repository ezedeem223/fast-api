"""
Lightweight startup benchmark for the FastAPI application.

Usage:
    python scripts/perf_startup.py --iterations 3 --threshold 2.5
"""

from __future__ import annotations

import argparse
import statistics
import time
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Ensure the app runs in lightweight "test" mode so schedulers/heavy services stay disabled
os.environ.setdefault("APP_ENV", "test")


def measure_startup(iterations: int) -> list[float]:
    """Helper for measure startup."""
    from app.core.app_factory import create_app

    timings: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        create_app()
        timings.append(time.perf_counter() - start)
    return timings


def main() -> int:
    """Helper for main."""
    parser = argparse.ArgumentParser(description="Measure FastAPI startup time.")
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Number of times to instantiate the app (default: 3).",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=2.5,
        help="Fail if average startup time exceeds this value in seconds (default: 2.5).",
    )
    args = parser.parse_args()

    timings = measure_startup(args.iterations)
    avg = statistics.mean(timings)
    print("Startup timings (s):", ", ".join(f"{t:.3f}" for t in timings))
    print(f"Average startup time: {avg:.3f}s (threshold {args.threshold:.3f}s)")

    if avg > args.threshold:
        print("Startup exceeded threshold.")
        return 1
    print("Startup within threshold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
