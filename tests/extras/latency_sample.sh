#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-http://localhost:8000}"
COUNT="${COUNT:-10}"

echo "== Collecting $COUNT latency samples (gateway process time + model timing in logs/metrics)"
tmp=$(mktemp)

for i in $(seq 1 "$COUNT"); do
  pc=$((10000 + RANDOM % 90000))
  payload=$(jq -n --arg pc "$pc" '{
    birthdate: "1990-06-12",
    driver_license_date: "2010-07-01",
    car_model: "Golf",
    car_brand: "VW",
    postal_code: $pc
  }')
  curl -s -D "$tmp" -X POST "$HOST/price" -H "Content-Type: application/json" -d "$payload" -o /dev/null
  hdr=$(grep -i '^X-Process-Time:' "$tmp" | awk '{print $2}')
  echo "${hdr:-0}" | sed 's/\r$//'   # seconds (as returned by header)
done > /tmp/latencies.txt

echo -e "\n-- Gateway process time (header) summary:"
awk '
  {sum+=$1; count+=1; if(min==""||$1<min)min=$1; if($1>max)max=$1}
  END {printf "n=%d min=%.4fs p50~(n/a via awk) avg=%.4fs max=%.4fs\n",count,min,sum/count,max}
' /tmp/latencies.txt

echo -e "\n-- Check Prometheus for model latency histogram (server side):"
bash tests/metrics.sh | grep gateway_model_latency_seconds | head -n 10 || true