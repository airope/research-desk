"""Local Django request-stack benchmark, not network/production load simulation."""

import argparse
import json
import os
import platform
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "srr.settings")
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import django

django.setup()


def measure(output, readers=10, requests=10):
    from django.db import close_old_connections, connection
    from django.test import Client

    from records.models import CandidatePair, SourceRecord
    from records.services import generate_candidates

    start = time.perf_counter()
    created = generate_candidates()
    generation = time.perf_counter() - start
    endpoint = "/api/v1/publications?page_size=20"
    client = Client()
    assert client.get(endpoint).status_code == 200

    def reader(_):
        close_old_connections()
        client = Client()
        elapsed = []
        try:
            for _ in range(requests):
                start = time.perf_counter()
                response = client.get(endpoint)
                if response.status_code != 200:
                    raise RuntimeError(f"Unexpected status {response.status_code}")
                elapsed.append((time.perf_counter() - start) * 1000)
            return elapsed
        finally:
            connection.close()

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=readers) as pool:
        latencies = sorted(value for batch in pool.map(reader, range(readers)) for value in batch)
    report = {
        "method": "Django in-process Client, full middleware/serialization/DB; excludes HTTP socket/server",
        "records": SourceRecord.objects.count(),
        "candidate_pairs": CandidatePair.objects.count(),
        "new_candidates": created,
        "candidate_generation_seconds": generation,
        "readers": readers,
        "requests_per_reader": requests,
        "warmup_requests": 1,
        "duration_seconds": time.perf_counter() - start,
        "p50_ms": latencies[len(latencies) // 2],
        "p95_ms": latencies[int(0.95 * (len(latencies) - 1))],
        "max_ms": max(latencies),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "limits": [
            "1000 real provider records; not the PRD 10000-record workload.",
            "Local in-process clients, not end-to-end HTTP load.",
            "No production capacity or availability inference.",
        ],
    }
    Path(output).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/performance-report.json")
    args = parser.parse_args()
    measure(args.output)
