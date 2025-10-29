#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-http://localhost:8000}"

echo "== Current config:"
curl -s "$HOST/config" | jq '{routing_rules, ab_testing}'

echo -e "\n== If you changed models.yaml (routing_rules.default), call /config/reload:"
curl -s -X POST "$HOST/config/reload" | jq .

echo -e "\n== Verify routing rule now in /config:"
curl -s "$HOST/config" | jq '{routing_rules}'
