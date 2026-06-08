#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
LOG_DIR="${ROOT_DIR}/data/reports/scraping"
SCRAPED_CSV="${ROOT_DIR}/data/raw/csv/supplements_exhaustive_clean.csv"
REJECTED_CSV="${LOG_DIR}/supplements_rejected.csv"
APPROVED_CSV="${ROOT_DIR}/data/catalog/approved_catalog.csv"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "${LOG_DIR}" "${ROOT_DIR}/data/raw/csv" "${ROOT_DIR}/data/catalog"

"${PYTHON_BIN}" "${ROOT_DIR}/scripts/scraping/supplements_exhaustive_scraper.py" \
  --limit-per-pharmacy "${LIMIT_PER_PHARMACY:-1000}" \
  --delay "${SCRAPER_DELAY:-0.25}" \
  --infer-registro \
  --out "${SCRAPED_CSV}" \
  --rejects-out "${REJECTED_CSV}" \
  2>&1 | tee "${LOG_DIR}/weekly_scrape_${STAMP}.log"

"${PYTHON_BIN}" "${ROOT_DIR}/scripts/build_approved_catalog.py" \
  --scraped "${SCRAPED_CSV}" \
  --digemid "${ROOT_DIR}/digemid_limpio.csv" \
  --components "${ROOT_DIR}/product_components.csv" \
  --out "${APPROVED_CSV}" \
  2>&1 | tee "${LOG_DIR}/weekly_catalog_${STAMP}.log"

cp "${SCRAPED_CSV}" "${LOG_DIR}/supplements_exhaustive_clean_${STAMP}.csv"
cp "${APPROVED_CSV}" "${LOG_DIR}/approved_catalog_${STAMP}.csv"
