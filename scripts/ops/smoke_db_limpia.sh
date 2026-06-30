#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x "${ROOT_DIR}/../.venv/bin/python" ]]; then
    PYTHON_BIN="${ROOT_DIR}/../.venv/bin/python"
  elif [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
    PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-suplematch-postgres}"
POSTGRES_USER="${POSTGRES_USER:-suplematch}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-suplematch}"
POSTGRES_HOST_PORT="${POSTGRES_HOST_PORT:-5432}"
SMOKE_DB="${SMOKE_DB:-suplematch_smoke_$(date -u +%Y%m%d%H%M%S)}"
SMOKE_PORT="${SMOKE_PORT:-18001}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin-smoke@suplematch.test}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-AdminSmoke12345}"
USER_EMAIL="${USER_EMAIL:-user-smoke@suplematch.test}"
USER_PASSWORD="${USER_PASSWORD:-UserSmoke12345}"
KEEP_SMOKE_DB="${KEEP_SMOKE_DB:-0}"

DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${POSTGRES_HOST_PORT}/${SMOKE_DB}"
API_BASE_URL="http://127.0.0.1:${SMOKE_PORT}"
SERVER_PID=""

json_get() {
  "${PYTHON_BIN}" -c 'import json,sys; data=json.load(sys.stdin); print(data'"$1"')'
}

cleanup() {
  if [[ -n "${SERVER_PID}" ]] && kill -0 "${SERVER_PID}" 2>/dev/null; then
    kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
  if [[ "${KEEP_SMOKE_DB}" != "1" ]]; then
    docker exec "${POSTGRES_CONTAINER}" psql -U "${POSTGRES_USER}" -d postgres -v ON_ERROR_STOP=1 \
      -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${SMOKE_DB}' AND pid <> pg_backend_pid();" >/dev/null
    docker exec "${POSTGRES_CONTAINER}" dropdb -U "${POSTGRES_USER}" --if-exists "${SMOKE_DB}" >/dev/null
  fi
}
trap cleanup EXIT

echo "== PostgreSQL container =="
docker compose up -d postgres >/dev/null
docker exec "${POSTGRES_CONTAINER}" pg_isready -U "${POSTGRES_USER}" -d postgres >/dev/null

echo "== Clean database: ${SMOKE_DB} =="
docker exec "${POSTGRES_CONTAINER}" dropdb -U "${POSTGRES_USER}" --if-exists "${SMOKE_DB}" >/dev/null
docker exec "${POSTGRES_CONTAINER}" createdb -U "${POSTGRES_USER}" "${SMOKE_DB}"

echo "== Alembic + seed + catalog =="
DATABASE_URL="${DATABASE_URL}" "${PYTHON_BIN}" -m alembic upgrade head
DATABASE_URL="${DATABASE_URL}" "${PYTHON_BIN}" scripts/init_postgres_schema.py
DATABASE_URL="${DATABASE_URL}" ADMIN_EMAIL="${ADMIN_EMAIL}" ADMIN_PASSWORD="${ADMIN_PASSWORD}" "${PYTHON_BIN}" scripts/seed_database.py
DATABASE_URL="${DATABASE_URL}" "${PYTHON_BIN}" scripts/import_catalog_to_postgres.py --catalog data/catalog/approved_catalog.csv

echo "== API startup =="
DATABASE_URL="${DATABASE_URL}" \
ENVIRONMENT=staging \
JWT_SECRET_KEY="smoke-secret-key-with-more-than-32-chars" \
PASSWORD_RESET_RETURN_TOKEN=false \
PUBLIC_FRONTEND_URL="http://127.0.0.1:${SMOKE_PORT}" \
CORS_ORIGINS="[\"http://127.0.0.1:${SMOKE_PORT}\"]" \
ADMIN_EMAIL="${ADMIN_EMAIL}" \
ADMIN_PASSWORD="${ADMIN_PASSWORD}" \
"${PYTHON_BIN}" -m uvicorn app.main:app --host 127.0.0.1 --port "${SMOKE_PORT}" > "data/reports/smoke_db_limpia_uvicorn.log" 2>&1 &
SERVER_PID="$!"

for _ in $(seq 1 60); do
  if curl -fsS "${API_BASE_URL}/api/v1/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS "${API_BASE_URL}/api/v1/health" >/dev/null
curl -fsS "${API_BASE_URL}/api/v1/health/ready" | grep -Eq '"status"[[:space:]]*:[[:space:]]*"(ready|degraded)"'

echo "== Auth =="
admin_login="$(curl -fsS -X POST "${API_BASE_URL}/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PASSWORD}\"}")"
admin_token="$(printf '%s' "${admin_login}" | json_get '["access_token"]')"

user_register="$(curl -fsS -X POST "${API_BASE_URL}/api/v1/auth/register" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${USER_EMAIL}\",\"password\":\"${USER_PASSWORD}\",\"first_name\":\"Usuario\",\"last_name\":\"Smoke\",\"age\":34,\"weight_value\":68,\"weight_unit\":\"kg\"}")"
user_token="$(printf '%s' "${user_register}" | json_get '["access_token"]')"

echo "== Admin catalog =="
products="$(curl -fsS "${API_BASE_URL}/api/v1/admin/products?limit=1" -H "Authorization: Bearer ${admin_token}")"
product_id="$(printf '%s' "${products}" | "${PYTHON_BIN}" -c 'import json,sys; data=json.load(sys.stdin); print(data[0]["id"])')"
curl -fsS "${API_BASE_URL}/api/v1/admin/catalog/quality" -H "Authorization: Bearer ${admin_token}" | grep -q "traceability_rate"

echo "== Recommendation =="
recommend_payload='{
  "edad_rango":"31_50",
  "sexo":"masculino",
  "tipo_dieta":"omnivoro",
  "horas_sueno":"5_7h",
  "frecuencia_ejercicio":"1_2_semana",
  "dieta":"regular",
  "fatiga":"a_menudo",
  "exposicion_solar":"menos_15min",
  "frecuencia_enfermedad":"1_2_anio",
  "estres":"moderado",
  "alcohol":"ocasional",
  "toma_suplementos":"no",
  "restricciones":["sin_restricciones"],
  "condiciones_seguridad":["ninguna"],
  "objetivos":["energia","salud_osea"]
}'
recommendation="$(curl -fsS -X POST "${API_BASE_URL}/api/v1/recommend" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${user_token}" \
  -d "${recommend_payload}")"
recommendation_id="$(printf '%s' "${recommendation}" | json_get '["recommendation_id"]')"
pack_id="$(printf '%s' "${recommendation}" | "${PYTHON_BIN}" -c 'import json,sys; data=json.load(sys.stdin); packs=data.get("packs_ranked") or []; print(packs[0]["pack_id"] if packs else "pack_smoke")')"

echo "== Feedback =="
curl -fsS -X POST "${API_BASE_URL}/api/v1/feedback" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${user_token}" \
  -d "{\"recommendation_id\":\"${recommendation_id}\",\"pack_id\":\"${pack_id}\",\"component_ids\":[\"COMP_94DFE28A9A5C\"],\"selected_product_ids\":[\"${product_id}\"],\"chosen_product_id\":\"${product_id}\",\"rating\":5,\"conditions\":[\"DEFICIT_VIT_D\"],\"product_context\":{\"selected_products\":[{\"product_id\":\"${product_id}\",\"commercial_score\":0.9}]}}" >/dev/null

echo "== Review =="
curl -fsS -X POST "${API_BASE_URL}/api/v1/reviews/supplements" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${user_token}" \
  -d "{\"product_id\":\"${product_id}\",\"rating\":5,\"effectiveness_score\":4,\"side_effects_score\":5,\"price_value_score\":4,\"comment\":\"Review smoke controlada para validar flujo.\"}" >/dev/null

echo "== Labs OCR/text =="
curl -fsS -X POST "${API_BASE_URL}/api/v1/labs/text" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${user_token}" \
  -d '{"consent_health_data":true,"persist":true,"source_type":"text","raw_text":"Hemoglobina 11.8 g/dL 12.0 - 16.0\nFerritina 14 ng/mL 13 - 150\nVitamina D 25-OH 18.3 ng/mL 30 - 100\nGlucosa 95 mg/dL 70 - 100\nTSH 0.32 mUI/L 0.4 - 4.0"}' | grep -q "biomarkers"

echo "== Ops =="
curl -fsS "${API_BASE_URL}/api/v1/health/ops" -H "Authorization: Bearer ${admin_token}" | grep -q '"checks"'
curl -fsS "${API_BASE_URL}/api/v1/metrics" | grep -q "suplematch_"

echo "smoke_db_limpia=ok db=${SMOKE_DB}"
