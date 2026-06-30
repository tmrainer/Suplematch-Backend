#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
REPORT_DIR="${DIGEMID_REPORT_DIR:-${ROOT_DIR}/data/reports/digemid}"
REPORT_OUT="${DIGEMID_REPORT_OUT:-${REPORT_DIR}/digemid_update_report.json}"
CURRENT_CSV="${DIGEMID_CURRENT_CSV:-${ROOT_DIR}/data/raw/digemid/digemid_limpio.csv}"
COMPONENTS_CSV="${DIGEMID_COMPONENTS_CSV:-${ROOT_DIR}/data/training/supplement_model/product_components.csv}"
VISUAL_CANDIDATES_CSV="${DIGEMID_VISUAL_CANDIDATES_CSV:-${REPORT_DIR}/digemid_visual_candidates.csv}"
VISUAL_REPORT_OUT="${DIGEMID_VISUAL_REPORT_OUT:-${REPORT_DIR}/digemid_visual_scrape_report.json}"

mkdir -p "${REPORT_DIR}"

if [[ "${DIGEMID_VISUAL_SCRAPER_ENABLED:-0}" == "1" ]]; then
  VISUAL_ARGS=(
    "${ROOT_DIR}/scripts/digemid/scrapear_digemid_visual.py"
    --out "${VISUAL_CANDIDATES_CSV}"
    --report-out "${VISUAL_REPORT_OUT}"
  )

  if [[ -n "${DIGEMID_VISUAL_URL:-}" ]]; then
    VISUAL_ARGS+=(--url "${DIGEMID_VISUAL_URL}")
  fi
  if [[ -n "${DIGEMID_VISUAL_QUERY_FILE:-}" ]]; then
    VISUAL_ARGS+=(--query-file "${DIGEMID_VISUAL_QUERY_FILE}")
  fi
  if [[ -n "${DIGEMID_VISUAL_QUERIES:-}" ]]; then
    VISUAL_ARGS+=(--query "${DIGEMID_VISUAL_QUERIES}")
  fi
  if [[ -n "${DIGEMID_VISUAL_MAX_QUERIES:-}" ]]; then
    VISUAL_ARGS+=(--max-queries "${DIGEMID_VISUAL_MAX_QUERIES}")
  fi
  if [[ -n "${DIGEMID_VISUAL_MAX_PAGES_PER_QUERY:-}" ]]; then
    VISUAL_ARGS+=(--max-pages-per-query "${DIGEMID_VISUAL_MAX_PAGES_PER_QUERY}")
  fi
  if [[ -n "${DIGEMID_VISUAL_STORAGE_STATE:-}" ]]; then
    VISUAL_ARGS+=(--storage-state "${DIGEMID_VISUAL_STORAGE_STATE}")
  fi
  if [[ -n "${DIGEMID_VISUAL_SAVE_STORAGE_STATE:-}" ]]; then
    VISUAL_ARGS+=(--save-storage-state "${DIGEMID_VISUAL_SAVE_STORAGE_STATE}")
  fi

  echo "digemid_visual_worker=starting report=${VISUAL_REPORT_OUT}"
  "${PYTHON_BIN}" "${VISUAL_ARGS[@]}" || echo "digemid_visual_worker=failed_or_unavailable report=${VISUAL_REPORT_OUT}"

  if [[ "${DIGEMID_VISUAL_PROMOTE_TO_SOURCE:-0}" == "1" && -s "${VISUAL_CANDIDATES_CSV}" ]]; then
    export DIGEMID_SOURCE_FILE="${VISUAL_CANDIDATES_CSV}"
    export DIGEMID_MIN_ROWS="${DIGEMID_VISUAL_MIN_PROMOTE_ROWS:-1}"
  fi
fi

ARGS=(
  "${ROOT_DIR}/scripts/digemid/actualizar_digemid.py"
  --out "${CURRENT_CSV}"
  --snapshot-dir "${REPORT_DIR}"
  --report-out "${REPORT_OUT}"
  --components "${COMPONENTS_CSV}"
)

if [[ -n "${DIGEMID_SOURCE_FILE:-}" ]]; then
  ARGS+=(--source-file "${DIGEMID_SOURCE_FILE}")
fi

if [[ -n "${DIGEMID_SOURCE_URL:-}" ]]; then
  ARGS+=(--source-url "${DIGEMID_SOURCE_URL}")
fi

if [[ -n "${DIGEMID_MIN_ROWS:-}" ]]; then
  ARGS+=(--min-rows "${DIGEMID_MIN_ROWS}")
fi

if [[ -n "${DIGEMID_TIMEOUT_SECONDS:-}" ]]; then
  ARGS+=(--timeout "${DIGEMID_TIMEOUT_SECONDS}")
fi

if [[ "${DIGEMID_FAIL_ON_NO_SOURCE:-0}" == "1" ]]; then
  ARGS+=(--fail-on-no-source)
fi

if [[ "${DIGEMID_FAIL_ON_FETCH_ERROR:-0}" == "1" ]]; then
  ARGS+=(--fail-on-fetch-error)
fi

echo "digemid_worker=starting report=${REPORT_OUT}"
"${PYTHON_BIN}" "${ARGS[@]}"
echo "digemid_worker=finished report=${REPORT_OUT}"
