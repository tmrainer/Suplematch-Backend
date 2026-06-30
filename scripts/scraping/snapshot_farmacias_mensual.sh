#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Monthly runs are intended to refresh the broad pharmacy dataset with a slower
# and deeper crawl. The weekly script performs the actual scrape/build/validate
# steps; this wrapper only sets safer monthly defaults.
export RUN_LABEL="${RUN_LABEL:-monthly}"
export LIMIT_PER_PHARMACY="${LIMIT_PER_PHARMACY:-2500}"
export SCRAPER_DELAY="${SCRAPER_DELAY:-0.5}"
export MIN_RAW_ROWS="${MIN_RAW_ROWS:-1000}"
export MIN_APPROVED_ROWS="${MIN_APPROVED_ROWS:-500}"
export MIN_PHARMACIES="${MIN_PHARMACIES:-3}"
export MAX_RAW_AGE_HOURS="${MAX_RAW_AGE_HOURS:-72}"

exec "${ROOT_DIR}/scripts/scraping/actualizar_suplementos_semanal.sh"
