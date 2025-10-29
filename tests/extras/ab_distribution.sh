#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-http://localhost:8000}"
N="${N:-300}"

echo "== Hitting $HOST/price $N times with random postal_code…"
# Generate N requests; print the routed model_id each line
seq "$N" | while read -r i; do
  pc=$((10000 + RANDOM % 90000))
  payload=$(jq -n --arg pc "$pc" '{
    birthdate: "1990-06-12",
    driver_license_date: "2010-07-01",
    car_model: "Golf",
    car_brand: "VW",
    postal_code: $pc
  }')
  curl -s -X POST "$HOST/price" -H "Content-Type: application/json" -d "$payload" \
    | jq -r '.gateway_metadata.model_id'
done | sort | uniq -c | awk '{printf "%-8s %s\n",$2,$1}'

echo -e "\n== Expected split (from config): ~33%/33%/34%"
echo "Check exposures in Prometheus (/metrics):"
curl -s "$HOST/metrics" | grep '^gateway_exposures_total' || true