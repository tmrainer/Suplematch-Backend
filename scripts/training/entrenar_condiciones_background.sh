#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ROWS="${ROWS:-10000}"
SEED="${SEED:-42}"
PYTHON_BIN="${PYTHON_BIN:-/home/leo/DPD/Proyecto/.venv/bin/python}"
LOG_DIR="$ROOT_DIR/data/reports/condition_model"
LOG_FILE="$LOG_DIR/condition_mvp_${ROWS}_train.log"
PID_FILE="$LOG_DIR/condition_mvp_${ROWS}_train.pid"

mkdir -p "$LOG_DIR"

if [[ "$ROWS" -lt 10000 ]]; then
  echo "ROWS debe ser al menos 10000 para este entrenamiento largo." >&2
  exit 2
fi

cd "$ROOT_DIR"
nohup "$PYTHON_BIN" scripts/training/entrenar_modelo_condiciones.py \
  --rows "$ROWS" \
  --seed "$SEED" \
  >"$LOG_FILE" 2>&1 &

PID="$!"
echo "$PID" > "$PID_FILE"
echo "condition_mvp large training started"
echo "pid=$PID"
echo "rows=$ROWS"
echo "seed=$SEED"
echo "log=$LOG_FILE"
echo "pid_file=$PID_FILE"
