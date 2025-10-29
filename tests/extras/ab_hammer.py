#!/usr/bin/env python3
import os
import random
import statistics
import sys

import anyio
import httpx

HOST = os.environ.get("HOST", "http://localhost:8000")
N = int(os.environ.get("N", "500"))
CONCURRENCY = int(os.environ.get("C", "50"))

payload_template = {
    "birthdate": "1990-06-12",
    "driver_license_date": "2010-07-01",
    "car_model": "Golf",
    "car_brand": "VW",
    # postal_code will vary
}


async def one(client):
    data = dict(payload_template)
    data["postal_code"] = str(random.randint(10000, 99999))
    r = await client.post(f"{HOST}/price", json=data)
    r.raise_for_status()
    j = r.json()
    model = j["gateway_metadata"]["model_id"]
    # header has X-Process-Time in seconds
    pt = float(r.headers.get("X-Process-Time", "0"))
    return model, pt


async def main():
    counts = {}
    times = {}
    async with httpx.AsyncClient(timeout=5.0) as client:

        async def worker(_):
            m, t = await one(client)
            counts[m] = counts.get(m, 0) + 1
            times.setdefault(m, []).append(t)

        async with anyio.create_task_group() as tg:
            for i in range(N):
                await tg.spawn(worker, i)

    total = sum(counts.values())
    print(f"Total: {total}")
    for m in sorted(counts):
        c = counts[m]
        pct = 100.0 * c / total if total else 0
        avg = statistics.mean(times[m]) if times[m] else 0
        print(f"{m:8s}  count={c:5d}  share={pct:5.1f}%  avg_gateway_time={avg:.4f}s")


if __name__ == "__main__":
    try:
        anyio.run(main)
    except KeyboardInterrupt:
        sys.exit(1)
