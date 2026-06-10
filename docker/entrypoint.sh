#!/usr/bin/env sh
set -eu

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  alembic upgrade head
fi

if [ "${RUN_SEED:-true}" = "true" ]; then
  python scripts/seed_database.py
fi

exec "$@"
