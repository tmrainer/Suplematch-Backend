"""Validacion temporal externa de `condition_lab_model` en NHANES agosto 2021-agosto 2023 (sufijo L).

El modelo se entreno en 2015-2016 y se eligio con 2017-2018. Este script lo aplica SIN reentrenar ni recalibrar a un
ciclo posterior a la pandemia, con los mismos cortes y umbrales guardados en el artefacto. Responde si las metricas
del model card se sostienen en otra poblacion y otro momento.

Tambien reporta el porcentaje de faltantes por feature en el ciclo L frente al de test: NHANES cambio algunos
cuestionarios en 2021-2023 y una feature ausente se imputa con la mediana del train (el modelo la ve "promedio").
Los medicamentos (metformina, antiacidos) se evaluan como "no" cuando faltan, igual que en el runtime.

Salida: data/reports/condition_model/nhanes_external_2021_2023.json

Uso:
  python scripts/training/validar_condiciones_nhanes_externo.py           # descarga los XPT del ciclo L (cache en data/raw/nhanes)
  python scripts/training/validar_condiciones_nhanes_externo.py --quick   # submuestra
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from scripts.training.entrenar_condiciones_nhanes import (  # noqa: E402
    CAT_FEATURES,
    MODEL_PATH,
    REPORT_DIR,
    TEST_CYCLE,
    biomarker_cutoffs,
    evaluate,
    features_from_questionnaire,
    load_cycle,
    population_mask,
    targets_from_labs,
)

EXTERNAL_CYCLE = "2021_2023"
MEDICATION_FEATURES = ("metformina", "antiacidos")


def missing_share(features) -> dict[str, float]:
    """Fraccion de filas sin dato por feature (NaN en numericas, "missing" en categoricas)."""
    out = {}
    for col in features.columns:
        series = features[col]
        missing = series.eq("missing") if col in CAT_FEATURES else series.isna()
        out[col] = round(float(missing.mean()), 3)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", type=Path, default=MODEL_PATH)
    parser.add_argument("--min-age", type=int, default=18)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=REPORT_DIR / "nhanes_external_2021_2023.json")
    args = parser.parse_args(argv)

    import joblib

    artifact = joblib.load(args.model)
    cutoffs = artifact.get("cutoffs") or biomarker_cutoffs()

    frames = {}
    for cycle in (TEST_CYCLE, EXTERNAL_CYCLE):
        print(f"Cargando {cycle}...")
        frame = load_cycle(cycle)
        frame = frame[frame["RIDAGEYR"] >= args.min_age]
        if args.quick:
            frame = frame.sample(min(1500, len(frame)), random_state=args.seed)
        frames[cycle] = frame.reset_index(drop=True)
        print(f"  filas adultos: {len(frame)}")

    features = {cycle: features_from_questionnaire(frame) for cycle, frame in frames.items()}
    x_ext, t_ext = features[EXTERNAL_CYCLE], targets_from_labs(frames[EXTERNAL_CYCLE], cutoffs)
    missing = {cycle: missing_share(frame) for cycle, frame in features.items()}
    # RXQ_RX_L ya no publica nombres de medicamentos: metformina/antiacidos quedan faltantes en todo el ciclo. El
    # runtime asume "no" salvo que la persona los marque (condition_lab_inference), asi que se evalua igual.
    for col in MEDICATION_FEATURES:
        x_ext[col] = x_ext[col].replace("missing", "no")

    metrics: dict[str, Any] = {}
    for target, model in artifact["models"].items():
        mask = t_ext[target].notna() & population_mask(x_ext, target)
        y = t_ext.loc[mask, target].astype(int).to_numpy()
        if len(y) < 100 or y.sum() < 10:
            metrics[target] = {"skipped": True, "n": int(len(y)), "positives": int(y.sum())}
            print(f"  {target}: omitido (n={len(y)}, positivos={int(y.sum())})")
            continue
        p = model.predict_proba(x_ext.loc[mask])[:, 1]
        result = evaluate(y, p, float(artifact["thresholds"][target]))
        result["positive_rate_predicted"] = float(np.mean(p >= result["threshold"]))
        result["mean_predicted"] = float(np.mean(p))
        metrics[target] = result
        print(
            f"  {target}: n={result['n']} prev={result['prevalence']:.2f} AUC={result['roc_auc']:.3f} "
            f"Brier={result['brier']:.3f} (base {result['brier_baseline_prevalence']:.3f}) ECE={result['ece']:.3f} "
            f"media_pred={result['mean_predicted']:.2f} F1={result['f1']:.2f}"
        )

    changed = {
        col: {"test": missing[TEST_CYCLE][col], "externo": missing[EXTERNAL_CYCLE][col]}
        for col in x_ext.columns
        if missing[EXTERNAL_CYCLE][col] - missing[TEST_CYCLE][col] >= 0.2
    }
    if changed:
        print("  features con mas faltantes en el ciclo externo (se imputan):", changed)

    report = {
        "model": str(args.model.name),
        "trained_on": artifact.get("train_cycle"),
        "selected_on": artifact.get("test_cycle"),
        "external_cycle": EXTERNAL_CYCLE,
        "n_external_adults": int(len(frames[EXTERNAL_CYCLE])),
        "quick": args.quick,
        "metrics": metrics,
        "missing_share": missing,
        "features_more_missing_external": changed,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Reporte: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
