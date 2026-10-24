"""Precision real: lo que la encuesta estima contra lo que el examen de la misma persona confirma.

Lee pares (encuesta, examen) de Postgres, recalcula la prediccion sin los examenes y compara tres variantes
(sistema servido, solo reglas + NHANES, solo NHANES). Ver app/ml/evaluation/precision_real.py.

    python scripts/validation/precision_real.py                 # resumen por consola + JSON/CSV agregados
    python scripts/validation/precision_real.py --window-days 120

Salida: data/reports/precision_real/precision_real_<fecha>.{json,csv} (solo conteos y metricas; ningun dato
individual). Con menos de MIN_CASES_FOR_METRIC casos marcados o positivos, la fila se marca como insuficiente.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db.session import SessionLocal  # noqa: E402
from app.ml.evaluation.pares_reales import DEFAULT_WINDOW_DAYS, measure  # noqa: E402
from app.ml.evaluation.precision_real import PREDICTORS  # noqa: E402

REPORT_DIR = ROOT_DIR / "data" / "reports" / "precision_real"


def _pct(value: float | None) -> str:
    return "  -  " if value is None else f"{value * 100:4.0f}%"


def rows(result: dict) -> list[dict]:
    out = []
    for condition, data in result["conditions"].items():
        for predictor, metrics in data["predictors"].items():
            out.append({"condition": condition, "predictor": predictor, "prevalence": data["prevalence"], **{
                key: (json.dumps(value) if isinstance(value, (list, tuple)) else value) for key, value in metrics.items()
            }})
    return out


def print_summary(result: dict) -> None:
    print(f"pares: {result['pairs']}  fuentes: {result['sources']}  descartados: {result['skipped']}")
    if not result["conditions"]:
        print("Sin pares evaluables todavia: hace falta que usuarios con examenes completen la encuesta.")
        return
    print(f"\n{'condicion':28} {'n':>5} {'prev':>5}  " + "  ".join(f"{p + ' prec/sens':>18}" for p in PREDICTORS))
    for condition, data in result["conditions"].items():
        cells = []
        for predictor in PREDICTORS:
            metrics = data["predictors"].get(predictor)
            if metrics is None:
                cells.append(f"{'':>18}")
                continue
            mark = "" if metrics["sufficient"] else "*"
            cells.append(f"{_pct(metrics['precision'])} / {_pct(metrics['recall'])}{mark:1}".rjust(18))
        print(f"{condition:28} {data['n']:>5} {_pct(data['prevalence'])}  " + "  ".join(cells))
    print(f"\n* menos de {result['min_cases_for_metric']} casos marcados o positivos: no concluir nada de esa celda.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    parser.add_argument("--out-dir", type=Path, default=REPORT_DIR)
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        result = measure(db, window_days=args.window_days).to_dict()
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    result["window_days"] = args.window_days

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    json_path = args.out_dir / f"precision_real_{stamp}.json"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    table = rows(result)
    csv_path = args.out_dir / f"precision_real_{stamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(table[0]) if table else ["condition", "predictor"])
        writer.writeheader()
        writer.writerows(table)

    print_summary(result)
    print(f"\nreporte: {json_path}\ncsv: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
