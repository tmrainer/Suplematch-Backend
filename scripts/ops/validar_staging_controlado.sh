#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://localhost:18080}"
ADMIN_TOKEN="${ADMIN_TOKEN:-}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-10}"

fail() {
  echo "staging_validation=failed reason=$1" >&2
  exit 1
}

request() {
  local path="$1"
  local auth_header=()
  if [[ -n "$ADMIN_TOKEN" ]]; then
    auth_header=(-H "Authorization: Bearer $ADMIN_TOKEN")
  fi
  curl -fsS --max-time "$TIMEOUT_SECONDS" "${auth_header[@]}" "$API_BASE_URL$path"
}

echo "== Basic health =="
health="$(request /api/v1/health)" || fail "health_unreachable"
echo "$health" | grep -q '"status":"ok"' || echo "$health" | grep -q '"status": "ok"' || fail "health_not_ok"

echo "== Readiness =="
ready="$(request /api/v1/health/ready)" || fail "readiness_unreachable"
echo "$ready" | grep -Eq '"status"[[:space:]]*:[[:space:]]*"(ready|degraded)"' || fail "readiness_bad_payload"

echo "== Metrics =="
metrics="$(request /api/v1/metrics)" || fail "metrics_unreachable"
echo "$metrics" | grep -q "suplematch_" || fail "metrics_missing_suplematch_prefix"

if [[ -n "$ADMIN_TOKEN" ]]; then
  echo "== Ops health =="
  ops="$(request /api/v1/health/ops)" || fail "ops_unreachable"
  echo "$ops" | grep -q '"checks"' || fail "ops_missing_checks"

  echo "== Admin catalog quality =="
  quality="$(request /api/v1/admin/catalog/quality)" || fail "catalog_quality_unreachable"
  echo "$quality" | grep -q '"traceability_rate"' || fail "catalog_quality_bad_payload"
else
  echo "== Admin checks skipped =="
  echo "ADMIN_TOKEN not provided"
fi

echo "staging_validation=ok"
