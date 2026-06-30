#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

INTERVAL_SECONDS="${CATALOG_WEEKLY_INTERVAL_SECONDS:-604800}"
RUN_ON_START="${CATALOG_WEEKLY_RUN_ON_START:-false}"

echo "catalog_worker=starting interval_seconds=${INTERVAL_SECONDS} run_on_start=${RUN_ON_START}"

alembic upgrade head
python scripts/ops/sembrar_base.py

run_update() {
  local started_at
  started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "catalog_worker_run=started at=${started_at}"
  if [[ "${DIGEMID_WEEKLY_ENABLED:-1}" == "1" ]]; then
    bash scripts/scraping/actualizar_digemid_semanal.sh || echo "digemid_worker_run=retained_previous at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  fi
  IMPORT_TO_POSTGRES="${IMPORT_TO_POSTGRES:-1}" \
    PYTHON_BIN="${PYTHON_BIN:-python}" \
    bash scripts/scraping/run_weekly_supplement_update.sh
  python scripts/ops/generar_reportes_operativos.py --skip-condition || true
  python scripts/ops/evaluar_senales_reales.py || true
  echo "catalog_worker_run=finished at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}

if [[ "${RUN_ON_START}" == "true" || "${RUN_ON_START}" == "1" ]]; then
  run_update || echo "catalog_worker_run=failed at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
fi

while true; do
  sleep "${INTERVAL_SECONDS}"
  run_update || echo "catalog_worker_run=failed at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
done
