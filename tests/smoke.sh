#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-http://localhost:8000}"

echo "== GET /health"
curl -s "$HOST/health" | jq .

echo -e "\n== GET /config"
curl -s "$HOST/config" | jq .

echo -e "\n== POST /price (single request)"
payload='{
  "birthdate":"1990-06-12",
  "driver_license_date":"2010-07-01",
  "car_model":"Golf",
  "car_brand":"VW",
  "postal_code":"11000"
}'
resp=$(curl -s -D /tmp/headers.txt -X POST "$HOST/price" -H "Content-Type: application/json" -d "$payload")
echo "$resp" | jq .
echo -e "\n-- Response headers:"
grep -E 'X-Request-ID|X-Process-Time' /tmp/headers.txt || true