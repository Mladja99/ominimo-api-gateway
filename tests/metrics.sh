#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-http://localhost:8000}"

echo "== /metrics (requests/errors/latency/exposures)"
curl -s "$HOST/metrics" | grep -E 'gateway_model_(requests|errors|latency)|gateway_exposures_total' | sed -n '1,120p'