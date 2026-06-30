#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
LOG_DIR="${ROOT_DIR}/data/reports/scraping"
SCRAPED_CSV="${SCRAPED_CSV:-${ROOT_DIR}/data/raw/pharmacies/supplements_exhaustive_clean.csv}"
REJECTED_CSV="${REJECTED_CSV:-${LOG_DIR}/supplements_rejected.csv}"
APPROVED_CSV="${APPROVED_CSV:-${ROOT_DIR}/data/catalog/approved_catalog.csv}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_LABEL="${RUN_LABEL:-weekly}"
VALIDATION_MODE="${VALIDATION_MODE:-${RUN_LABEL}}"
if [[ "${VALIDATION_MODE}" != "weekly" && "${VALIDATION_MODE}" != "monthly" && "${VALIDATION_MODE}" != "manual" ]]; then
  VALIDATION_MODE="manual"
fi
REPORT_JSON="${LOG_DIR}/${RUN_LABEL}_catalog_validation_${STAMP}.json"
CURRENT_REPORT_JSON="${LOG_DIR}/catalog_pipeline_current_report.json"
ALERT_JSON="${LOG_DIR}/catalog_pipeline_alert.json"
IMPORT_TO_POSTGRES="${IMPORT_TO_POSTGRES:-0}"

mkdir -p "${LOG_DIR}" "${ROOT_DIR}/data/raw/pharmacies" "${ROOT_DIR}/data/catalog"

run_postgres_import() {
  local import_log="${LOG_DIR}/${RUN_LABEL}_postgres_import_${STAMP}.log"
  local compose_file="${POSTGRES_IMPORT_COMPOSE_FILE:-${ROOT_DIR}/../docker-compose.staging.yml}"
  local compose_env_file="${POSTGRES_IMPORT_ENV_FILE:-${ROOT_DIR}/../.env.staging}"
  local compose_mode="${POSTGRES_IMPORT_VIA_COMPOSE:-auto}"
  local container_catalog="${POSTGRES_IMPORT_CONTAINER_CATALOG:-}"
  local should_use_compose=0

  if [[ -z "${container_catalog}" ]]; then
    if [[ "${APPROVED_CSV}" == "${ROOT_DIR}/"* ]]; then
      container_catalog="${APPROVED_CSV#"${ROOT_DIR}/"}"
    else
      container_catalog="${APPROVED_CSV}"
    fi
  fi

  if [[ "${compose_mode}" == "1" ]]; then
    should_use_compose=1
  elif [[ "${compose_mode}" == "auto" ]]; then
    if command -v docker >/dev/null 2>&1 \
      && [[ -f "${compose_file}" ]] \
      && [[ -f "${compose_env_file}" ]] \
      && docker compose --env-file "${compose_env_file}" -f "${compose_file}" ps -q backend >/dev/null 2>&1; then
      case "${DATABASE_URL:-}" in
        ""|*localhost*|*127.0.0.1*) should_use_compose=1 ;;
      esac
    fi
  fi

  set +e
  if [[ "${should_use_compose}" == "1" ]]; then
    echo "postgres_import=via_docker_compose backend catalog=${container_catalog}" | tee "${import_log}"
    docker compose --env-file "${compose_env_file}" -f "${compose_file}" exec -T backend \
      python scripts/catalog/importar_catalogo_postgres.py \
      --catalog "${container_catalog}" \
      2>&1 | tee -a "${import_log}"
  else
    echo "postgres_import=direct catalog=${APPROVED_CSV}" | tee "${import_log}"
    "${PYTHON_BIN}" "${ROOT_DIR}/scripts/catalog/importar_catalogo_postgres.py" \
      --catalog "${APPROVED_CSV}" \
      2>&1 | tee -a "${import_log}"
  fi
  local import_status="${PIPESTATUS[0]}"
  set -e
  return "${import_status}"
}

write_alert() {
  local status="$1"
  local reason="${2:-}"
  "${PYTHON_BIN}" - "$ALERT_JSON" "$status" "$reason" "$RUN_LABEL" "$STAMP" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
payload = {
    "status": sys.argv[2],
    "reason": sys.argv[3],
    "run_label": sys.argv[4],
    "stamp": sys.argv[5],
    "generated_at": datetime.now(timezone.utc).isoformat(),
}
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

on_error() {
  local line="$1"
  write_alert "failed" "line_${line}"
}
trap 'on_error "$LINENO"' ERR

LOCK_DIR="${LOG_DIR}/${LOCK_NAME:-${RUN_LABEL}}.lock"
if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  echo "another_${RUN_LABEL}_scraping_run_is_active lock=${LOCK_DIR}" >&2
  exit 75
fi
trap 'rm -rf "${LOCK_DIR}"' EXIT

echo "run_label=${RUN_LABEL}"
echo "stamp=${STAMP}"
echo "root=${ROOT_DIR}"

REQUIRE_PHARMACY_ARGS=()
if [[ -n "${REQUIRE_PHARMACIES:-}" ]]; then
  IFS=',' read -ra REQUIRED_PHARMACY_LIST <<< "${REQUIRE_PHARMACIES}"
  for pharmacy in "${REQUIRED_PHARMACY_LIST[@]}"; do
    pharmacy="$(echo "${pharmacy}" | xargs)"
    if [[ -n "${pharmacy}" ]]; then
      REQUIRE_PHARMACY_ARGS+=(--require-pharmacy "${pharmacy}")
    fi
  done
fi

SCRAPER_PHARMACY_ARGS=()
if [[ -n "${SCRAPER_PHARMACIES:-}" ]]; then
  IFS=',' read -ra SCRAPER_PHARMACY_LIST <<< "${SCRAPER_PHARMACIES}"
  for pharmacy in "${SCRAPER_PHARMACY_LIST[@]}"; do
    pharmacy="$(echo "${pharmacy}" | xargs)"
    if [[ -n "${pharmacy}" ]]; then
      SCRAPER_PHARMACY_ARGS+=(--pharmacy "${pharmacy}")
    fi
  done
fi

SCRAPER_DETAIL_ARGS=()
if [[ "${SCRAPER_FETCH_DETAIL_PAGES:-1}" == "1" ]]; then
  SCRAPER_DETAIL_ARGS+=(--fetch-detail-pages)
fi
if [[ "${SCRAPER_OCR_PRODUCT_IMAGES:-0}" == "1" ]]; then
  SCRAPER_DETAIL_ARGS+=(--ocr-product-images)
fi
if [[ "${SCRAPER_DOWNLOAD_PRODUCT_IMAGES:-0}" == "1" ]]; then
  SCRAPER_DETAIL_ARGS+=(--download-product-images --image-dir "${SCRAPER_IMAGE_DIR:-${ROOT_DIR}/data/raw/pharmacies/product_images}")
fi

if [[ "${VALIDATE_ONLY:-0}" == "1" ]]; then
  echo "validate_only=1"
  set +e
  "${PYTHON_BIN}" "${ROOT_DIR}/scripts/validation/validar_pipeline_catalogo.py" \
    --mode "${VALIDATION_MODE}" \
    --raw "${SCRAPED_CSV}" \
    --approved "${APPROVED_CSV}" \
    --rejects "${REJECTED_CSV}" \
    --report-out "${REPORT_JSON}" \
    --min-raw-rows "${MIN_RAW_ROWS:-500}" \
    --min-approved-rows "${MIN_APPROVED_ROWS:-250}" \
    --min-pharmacies "${MIN_PHARMACIES:-3}" \
    --max-invalid-price-ratio "${MAX_INVALID_PRICE_RATIO:-0.01}" \
    --max-raw-age-hours "${MAX_RAW_AGE_HOURS:-48}" \
    "${REQUIRE_PHARMACY_ARGS[@]}" \
    2>&1 | tee "${LOG_DIR}/${RUN_LABEL}_validation_${STAMP}.log"
  VALIDATION_STATUS="${PIPESTATUS[0]}"
  set -e
  echo "validation_report=${REPORT_JSON}"
  cp "${REPORT_JSON}" "${CURRENT_REPORT_JSON}"
  if [[ "${VALIDATION_STATUS}" == "0" ]]; then
    write_alert "passed" "validate_only"
  else
    write_alert "failed" "validation_failed"
  fi
  echo "completed=${RUN_LABEL}_${STAMP}"
  exit "${VALIDATION_STATUS}"
fi

"${PYTHON_BIN}" "${ROOT_DIR}/scripts/scraping/scraper_suplementos.py" \
  --limit-per-pharmacy "${LIMIT_PER_PHARMACY:-1000}" \
  --delay "${SCRAPER_DELAY:-0.25}" \
  "${SCRAPER_PHARMACY_ARGS[@]}" \
  "${SCRAPER_DETAIL_ARGS[@]}" \
  --infer-registro \
  --out "${SCRAPED_CSV}" \
  --rejects-out "${REJECTED_CSV}" \
  2>&1 | tee "${LOG_DIR}/${RUN_LABEL}_scrape_${STAMP}.log"

"${PYTHON_BIN}" "${ROOT_DIR}/scripts/catalog/construir_catalogo_aprobado.py" \
  --scraped "${SCRAPED_CSV}" \
  --digemid "${ROOT_DIR}/data/raw/digemid/digemid_limpio.csv" \
  --components "${ROOT_DIR}/data/training/supplement_model/product_components.csv" \
  --out "${APPROVED_CSV}" \
  --rejects-out "${LOG_DIR}/${RUN_LABEL}_approved_catalog_rejections_${STAMP}.csv" \
  2>&1 | tee "${LOG_DIR}/${RUN_LABEL}_catalog_${STAMP}.log"

if [[ "${ENRICH_CATALOG_FLAGS:-1}" == "1" ]]; then
  "${PYTHON_BIN}" "${ROOT_DIR}/scripts/catalog/enriquecer_catalogo_verificable.py" \
    --input "${APPROVED_CSV}" \
    2>&1 | tee "${LOG_DIR}/${RUN_LABEL}_catalog_enrichment_${STAMP}.log"
fi

set +e
"${PYTHON_BIN}" "${ROOT_DIR}/scripts/validation/validar_pipeline_catalogo.py" \
  --mode "${VALIDATION_MODE}" \
  --raw "${SCRAPED_CSV}" \
  --approved "${APPROVED_CSV}" \
  --rejects "${REJECTED_CSV}" \
  --report-out "${REPORT_JSON}" \
  --min-raw-rows "${MIN_RAW_ROWS:-500}" \
  --min-approved-rows "${MIN_APPROVED_ROWS:-250}" \
  --min-pharmacies "${MIN_PHARMACIES:-3}" \
  --max-invalid-price-ratio "${MAX_INVALID_PRICE_RATIO:-0.01}" \
  --max-raw-age-hours "${MAX_RAW_AGE_HOURS:-48}" \
  "${REQUIRE_PHARMACY_ARGS[@]}" \
  2>&1 | tee "${LOG_DIR}/${RUN_LABEL}_validation_${STAMP}.log"
VALIDATION_STATUS="${PIPESTATUS[0]}"
set -e

echo "validation_report=${REPORT_JSON}"
cp "${REPORT_JSON}" "${CURRENT_REPORT_JSON}"
if [[ "${VALIDATION_STATUS}" != "0" ]]; then
  write_alert "failed" "validation_failed"
  exit "${VALIDATION_STATUS}"
fi

cp "${SCRAPED_CSV}" "${LOG_DIR}/${RUN_LABEL}_supplements_exhaustive_clean_${STAMP}.csv"
cp "${APPROVED_CSV}" "${LOG_DIR}/${RUN_LABEL}_approved_catalog_${STAMP}.csv"
cp "${REJECTED_CSV}" "${LOG_DIR}/${RUN_LABEL}_supplements_rejected_${STAMP}.csv"

if [[ "${IMPORT_TO_POSTGRES}" == "1" ]]; then
  run_postgres_import
fi

write_alert "passed" "catalog_updated"
echo "completed=${RUN_LABEL}_${STAMP}"
