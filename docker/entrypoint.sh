#!/usr/bin/env sh
set -eu

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  alembic upgrade head
fi

if [ "${RUN_SEED:-true}" = "true" ]; then
  python scripts/ops/sembrar_base.py
fi

if [ "${RUN_OPERATIONAL_REPORTS_ON_START:-false}" = "true" ]; then
  python scripts/ops/generar_reportes_operativos.py --skip-condition || true
fi

exec "$@"
