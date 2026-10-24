#!/usr/bin/env bash
# Reconstruye el catalogo aprobado de punta a punta a partir de insumos locales (sin red):
#   DIGEMID + Component_Master  -> product_components.csv   (generar_product_components.py)
#   raw de scraping             -> raw con RS re-inferido   (reinferir_rs.py, matcher actual)
#   raw + DIGEMID + componentes -> catalogo aprobado         (construir_catalogo_aprobado.py)
#   catalogo                    -> enriquecido               (enriquecer_catalogo_verificable.py)
#   validacion + limpieza                                     (validar_pipeline_catalogo.py, limpiar_catalogo_aprobado.py)
# Uso: bash scripts/catalog/reconstruir_catalogo.sh [--apply]
#   sin --apply escribe todo en data/reports/catalog/rebuild_<stamp>/ y no toca data/catalog/approved_catalog.csv
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-python3}"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
WORK="data/reports/catalog/rebuild_${STAMP}"
mkdir -p "$WORK"

RAW="${RAW:-data/raw/pharmacies/supplements_exhaustive_clean.csv}"
DIGEMID="${DIGEMID:-data/raw/digemid/digemid_limpio.csv}"
MASTER="${MASTER:-data/training/supplement_model/Component_Master_Clean.csv}"
COMPONENTS="data/training/supplement_model/product_components.csv"

for f in "$RAW" "$DIGEMID" "$MASTER"; do
  [[ -f "$f" ]] || { echo "falta insumo: $f (ver data/insumos_manifest.json)" >&2; exit 2; }
done

"$PYTHON_BIN" scripts/catalog/generar_product_components.py --digemid "$DIGEMID" --master "$MASTER" --legacy "$COMPONENTS" \
  --out "$WORK/product_components.csv" --report-out "$WORK/product_components_report.json"
"$PYTHON_BIN" scripts/catalog/reinferir_rs.py --raw "$RAW" --out "$WORK/raw_reinferred.csv" \
  --digemid "$DIGEMID" --components "$WORK/product_components.csv" --component-master "$MASTER"
"$PYTHON_BIN" scripts/catalog/construir_catalogo_aprobado.py --scraped "$WORK/raw_reinferred.csv" --digemid "$DIGEMID" \
  --components "$WORK/product_components.csv" --out "$WORK/catalog.csv" --rejects-out "$WORK/rejects.csv"
"$PYTHON_BIN" scripts/catalog/enriquecer_catalogo_verificable.py --input "$WORK/catalog.csv" --output "$WORK/catalog_enriched.csv" --report-dir "$WORK/quality"
"$PYTHON_BIN" scripts/validation/validar_pipeline_catalogo.py --raw "$WORK/raw_reinferred.csv" --approved "$WORK/catalog_enriched.csv" \
  --rejects "$WORK/rejects.csv" --max-raw-age-hours "${MAX_RAW_AGE_HOURS:-100000}" --mode manual --report-out "$WORK/validation.json"
"$PYTHON_BIN" scripts/catalog/limpiar_catalogo_aprobado.py --catalog "$WORK/catalog_enriched.csv" --apply --removed-dir "$WORK"

if [[ "${1:-}" == "--apply" ]]; then
  cp data/catalog/approved_catalog.csv "data/reports/catalog/approved_catalog_pre_rebuild_${STAMP}.csv"
  cp "$WORK/catalog_enriched.csv" data/catalog/approved_catalog.csv
  cp "$WORK/product_components.csv" "$COMPONENTS"
  "$PYTHON_BIN" scripts/ops/verificar_insumos.py --update >/dev/null
  echo "catalogo aplicado: data/catalog/approved_catalog.csv (backup en data/reports/catalog/)"
else
  echo "dry-run: resultados en $WORK (usa --apply para reemplazar el catalogo)"
fi
