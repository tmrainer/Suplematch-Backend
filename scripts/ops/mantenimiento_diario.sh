#!/usr/bin/env bash
# Tareas de mantenimiento diarias. Pensado para cron (host o contenedor) o para un job programado.
#   - Purga (redacta) reportes de laboratorio vencidos segun LAB_REPORT_RETENTION_DAYS (Ley 29733: datos sensibles).
#   - Verifica integridad de insumos (hashes) y avisa si alguno falta o cambio.
# Uso:  bash scripts/ops/mantenimiento_diario.sh [--dry-run]
# Cron sugerido (03:15 hora Lima):  15 3 * * *  cd /app && bash scripts/ops/mantenimiento_diario.sh >> /var/log/suplematch/mantenimiento.log 2>&1
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DRY_RUN="${1:-}"

echo "[$(date -u +%FT%TZ)] mantenimiento inicio dry_run=${DRY_RUN:-no}"
if [[ "$DRY_RUN" == "--dry-run" ]]; then
  "$PYTHON_BIN" scripts/ops/purgar_lab_reports.py --dry-run
else
  "$PYTHON_BIN" scripts/ops/purgar_lab_reports.py
fi
"$PYTHON_BIN" scripts/ops/verificar_insumos.py --strict-versioned || echo "[WARN] insumos versionados con cambios o ausentes"
echo "[$(date -u +%FT%TZ)] mantenimiento fin"
