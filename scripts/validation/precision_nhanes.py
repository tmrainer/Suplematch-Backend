"""Precision del sistema con encuestas y examenes reales de NHANES 2013-2014 (CDC).

Cada adulto de 20 a 59 años con el modulo de sol (DEQ_H) pasa a una encuesta de SupleMatch; la prediccion se hace
con la encuesta, por el mismo camino que /recommend, y se compara con sus examenes. Mismo reporte que
`precision_real.py` (sistema / reglas / nhanes), mas:

- **diagnostico por regla**: entre quienes cumplen cada regla, que proporcion confirma el examen (precision de la
  regla) y cuanto sube frente a la prevalencia (lift);
- **pesos aprendidos**: regresion logistica sobre las mismas reglas como variables, evaluada con validacion cruzada
  (AUC fuera de muestra) contra el puntaje de reglas actual y el Modelo 1. Sirve de propuesta para el nutricionista,
  no se aplica sola: es poblacion de EE. UU.

Mapeo (`survey_from_nhanes`): sol = minutos al aire libre 9-17 h (DED120 laboral, DED125 libre, promedio semanal);
fatiga = PHQ-9 item 4 (DPQ040); estres = suma de los otros items del PHQ-9 sin sueño ni fatiga (aproximado);
sueño SLD010H; ejercicio = dias de actividad recreativa (PAQ655/PAQ670); alcohol ALQ101/110/120Q/120U/130;
tabaco SMQ020/040; salud HSD010; suplementos DSQTOT; metformina y antiacidos RXQ_RX; diabetes medicada DIQ050/070;
embarazo RIDEXPRG. Sin equivalente: frecuencia de enfermedad (queda en "1_2_anio", lo tipico en adultos) y la dieta
detallada (queda sin responder, como si la persona la saltara). Sin pesos muestrales.

Examenes (verdad, cortes de biomarkers.csv): vitamina D, HbA1c, glucosa en ayunas, colesterol total y HDL, ALT,
AST, creatinina, B12 y hemoglobina. Sin ferritina (no se midio en 2013-2014) ni folato serico (solo eritrocitario).
El modelo NHANES de vitamina D, HbA1c, HDL y ALT se entreno con 2015-2016: 2013-2014 queda fuera de muestra.

    python scripts/validation/precision_nhanes.py            # completo (~3 900 adultos, unos minutos)
    python scripts/validation/precision_nhanes.py --limit 300
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.domains.labs.esquemas import LabBiomarkerInput  # noqa: E402
from app.domains.labs.servicio_analisis_examenes import LabAnalysisService  # noqa: E402
from app.domains.recommendations.servicio_recomendaciones import _lab_patient_context  # noqa: E402
from app.domains.survey.esquemas_encuesta import EncuestaInput  # noqa: E402
from app.ml.evaluation.pares_reales import _statuses, survey_only_details  # noqa: E402
from app.ml.evaluation.precision_real import PrecisionReport, lab_truth, predicted_conditions  # noqa: E402
from app.ml.feature_builder import FeatureBuilder  # noqa: E402
from scripts.training.entrenar_condiciones_nhanes import download, medication_flags  # noqa: E402

YEAR, SUFFIX, SOURCE = "2013", "H", "nhanes_2013_2014"
REPORT_DIR = ROOT_DIR / "data" / "reports" / "precision_real"
FILES: dict[str, list[str]] = {
    "DEMO": ["SEQN", "RIAGENDR", "RIDAGEYR", "RIDEXPRG"],
    "BMX": ["SEQN", "BMXWT", "BMXHT"],
    "DEQ": ["SEQN", "DEQ034D", "DED120", "DED125"],
    "DPQ": ["SEQN", "DPQ010", "DPQ020", "DPQ030", "DPQ040", "DPQ050", "DPQ060", "DPQ070", "DPQ080", "DPQ090"],
    "SLQ": ["SEQN", "SLD010H"],
    "PAQ": ["SEQN", "PAQ650", "PAQ655", "PAQ665", "PAQ670"],
    "ALQ": ["SEQN", "ALQ101", "ALQ110", "ALQ120Q", "ALQ120U", "ALQ130"],
    "SMQ": ["SEQN", "SMQ020", "SMQ040"],
    "HSQ": ["SEQN", "HSD010"],
    "DIQ": ["SEQN", "DIQ050", "DIQ070"],
    "DSQTOT": ["SEQN", "DSDCOUNT", "DSQTVD", "DSQTIRON", "DSQTVB12", "DSQTCALC", "DSQTMAGN", "DSQTZINC", "DSQTVC"],
    "VID": ["SEQN", "LBXVIDMS"],
    "GHB": ["SEQN", "LBXGH"],
    "GLU": ["SEQN", "LBXGLU"],
    "TCHOL": ["SEQN", "LBXTC"],
    "HDL": ["SEQN", "LBDHDD"],
    "BIOPRO": ["SEQN", "LBXSATSI", "LBXSASSI", "LBXSCR"],
    "VITB12": ["SEQN", "LBDB12"],
    "CBC": ["SEQN", "LBXHGB"],
}
# Codigo de biomarkers.csv -> (columna NHANES, factor a la unidad de biomarkers.csv, unidad)
LABS: dict[str, tuple[str, float, str]] = {
    "vitamin_d": ("LBXVIDMS", 0.4, "ng/mL"),  # nmol/L -> ng/mL
    "hba1c": ("LBXGH", 1.0, "%"),
    "glucose": ("LBXGLU", 1.0, "mg/dL"),
    "total_cholesterol": ("LBXTC", 1.0, "mg/dL"),
    "hdl": ("LBDHDD", 1.0, "mg/dL"),
    "alt": ("LBXSATSI", 1.0, "U/L"),
    "ast": ("LBXSASSI", 1.0, "U/L"),
    "creatinine": ("LBXSCR", 1.0, "mg/dL"),
    "b12": ("LBDB12", 1.0, "pg/mL"),
    "hemoglobin": ("LBXHGB", 1.0, "g/dL"),
}
SUPPLEMENTS: dict[str, tuple[str, str]] = {
    "vitamina_d": ("DSQTVD", "mcg"),
    "hierro": ("DSQTIRON", "mg"),
    "vitamina_b12": ("DSQTVB12", "mcg"),
    "calcio": ("DSQTCALC", "mg"),
    "magnesio": ("DSQTMAGN", "mg"),
    "zinc": ("DSQTZINC", "mg"),
    "vitamina_c": ("DSQTVC", "mg"),
}
STRESS_ITEMS = ("DPQ010", "DPQ020", "DPQ050", "DPQ060", "DPQ070", "DPQ080", "DPQ090")  # PHQ-9 sin sueño ni fatiga
ALCOHOL_UNIT_PER_WEEK = {1: 1.0, 2: 12 / 52, 3: 1 / 52}  # ALQ120U: semana, mes, año
CV_FOLDS = 5


def _num(row: dict[str, Any], name: str, missing: tuple[float, ...] = ()) -> float | None:
    value = row.get(name)
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    value = float(value)
    return None if value in missing else value


def sleep_range(hours: float | None) -> str | None:
    if hours is None or hours > 24:
        return None
    if hours < 5:
        return "menos_5h"
    if hours < 7:
        return "5_7h"
    if hours < 9:
        return "7_9h"
    return "mas_9h"


def sun_range(workday: float | None, freeday: float | None) -> str | None:
    """Minutos al aire libre entre 9 y 17 h, promedio semanal (5 dias laborales + 2 libres)."""
    if workday is None and freeday is None:
        return None
    minutes = (5 * (workday if workday is not None else freeday) + 2 * (freeday if freeday is not None else workday)) / 7
    if minutes < 15:
        return "menos_15min"
    if minutes < 30:
        return "15_30min"
    if minutes <= 60:
        return "30_60min"
    return "mas_1h"


def stress_level(items: list[float | None]) -> str | None:
    """Suma de 7 items del PHQ-9 (0-21). Aproximado: el PHQ-9 mide animo, no estres."""
    if any(item is None for item in items):
        return None
    total = sum(items)
    if total <= 3:
        return "bajo"
    if total <= 7:
        return "moderado"
    if total <= 11:
        return "alto"
    return "muy_alto"


def alcohol_per_week(row: dict[str, Any]) -> float | None:
    if _num(row, "ALQ101") == 2 and _num(row, "ALQ110") in (2, None):
        return 0.0
    times = _num(row, "ALQ120Q", (777, 999))
    if times == 0:
        return 0.0
    unit = _num(row, "ALQ120U", (7, 9))
    if times is None or unit not in ALCOHOL_UNIT_PER_WEEK:
        return None
    drinks = _num(row, "ALQ130", (777, 999)) or 1.0
    return times * ALCOHOL_UNIT_PER_WEEK[int(unit)] * drinks


def alcohol_range(per_week: float | None) -> str | None:
    if per_week is None:
        return None
    if per_week <= 0:
        return "nunca"
    if per_week < 1:
        return "raro"
    if per_week <= 7:
        return "ocasional"
    return "frecuente"


def exercise_days(row: dict[str, Any]) -> int | None:
    vigorous, moderate = _num(row, "PAQ650", (7, 9)), _num(row, "PAQ665", (7, 9))
    if vigorous is None or moderate is None:
        return None
    days_v = _num(row, "PAQ655", (77, 99)) if vigorous == 1 else 0.0
    days_m = _num(row, "PAQ670", (77, 99)) if moderate == 1 else 0.0
    if days_v is None or days_m is None:
        return None
    return int(min(7, max(days_v, days_m)))


def exercise_range(days: int | None) -> str | None:
    if days is None:
        return None
    if days == 0:
        return "casi_nunca"
    if days <= 2:
        return "1_2_semana"
    if days <= 4:
        return "3_4_semana"
    return "diario"


def survey_from_nhanes(row: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Encuesta de SupleMatch para una fila de NHANES, o (None, motivo) si falta una pregunta obligatoria."""
    fatigue = _num(row, "DPQ040", (7, 9))
    days = exercise_days(row)
    per_week = alcohol_per_week(row)
    required = {
        "horas_sueno": sleep_range(_num(row, "SLD010H", (77, 99))),
        "frecuencia_ejercicio": exercise_range(days),
        "fatiga": {0: "casi_nunca", 1: "a_veces", 2: "a_menudo", 3: "siempre"}.get(int(fatigue)) if fatigue is not None else None,
        "exposicion_solar": sun_range(_num(row, "DED120", (7777, 9999)), _num(row, "DED125", (7777, 9999))),
        "estres": stress_level([_num(row, item, (7, 9)) for item in STRESS_ITEMS]),
        "alcohol": alcohol_range(per_week),
    }
    missing = [key for key, value in required.items() if value is None]
    if missing:
        return None, f"falta_{missing[0]}"

    survey: dict[str, Any] = {
        **required,
        "frecuencia_enfermedad": "1_2_anio",  # sin equivalente en NHANES
        "sexo": "masculino" if _num(row, "RIAGENDR") == 1 else "femenino",
        "age_years": int(_num(row, "RIDAGEYR")),
        "exercise_days_week": days,
        "alcohol_drinks_week": int(min(80, round(per_week))),
    }
    if (weight := _num(row, "BMXWT")) is not None:
        survey["weight_kg"] = weight
    if (height := _num(row, "BMXHT")) is not None:
        survey["height_cm"] = height
    sunscreen = _num(row, "DEQ034D", (7, 9))
    if sunscreen is not None:
        survey["protector_solar"] = "siempre" if sunscreen <= 2 else ("a_veces" if sunscreen == 3 else "nunca")
    smoked, now = _num(row, "SMQ020", (7, 9)), _num(row, "SMQ040", (7, 9))
    if smoked == 2:
        survey["tabaco"] = "nunca"
    elif smoked == 1 and now is not None:
        survey["tabaco"] = "actual" if now in (1, 2) else "ex"
    health = _num(row, "HSD010", (7, 9))
    if health is not None:
        survey["salud_autopercibida"] = {1: "excelente", 2: "muy_buena", 3: "buena", 4: "regular", 5: "mala"}[int(health)]

    safety = []
    if _num(row, "DIQ050") == 1 or _num(row, "DIQ070") == 1:
        safety.append("diabetes_medicada")
    if _num(row, "RIDEXPRG") == 1:
        safety.append("embarazo_lactancia")
    survey["condiciones_seguridad"] = safety
    survey["medicamentos_b12"] = [
        name for name, column in (("metformina", "metformina"), ("antiacidos_ibp", "antiacidos")) if row.get(column) == "si"
    ]

    if (_num(row, "DSDCOUNT", (77, 99)) or 0) > 0:
        survey["toma_suplementos"] = "si"
        taken = {name: (_num(row, column), unit) for name, (column, unit) in SUPPLEMENTS.items()}
        # Toma algo, pero ninguno de los que pregunta la encuesta: "otro".
        survey["suplementos_actuales"] = [name for name, (amount, _unit) in taken.items() if amount and amount > 0] or ["otro"]
        doses = {name: {"amount": min(amount, 100000), "unit": unit} for name, (amount, unit) in taken.items() if amount and amount > 0}
        if doses:  # sin esta marca la encuesta descarta las dosis
            survey["suplementos_dosis_conocida"] = True
            survey["suplementos_dosis_actual"] = doses
    return survey, None


def lab_values(row: dict[str, Any]) -> list[LabBiomarkerInput]:
    values = []
    for code, (column, factor, unit) in LABS.items():
        value = _num(row, column)
        if value is not None and value > 0:
            values.append(LabBiomarkerInput(code=code, value=round(value * factor, 3), unit=unit))
    return values


def load_frame() -> pd.DataFrame:
    merged: pd.DataFrame | None = None
    for stem, columns in FILES.items():
        path = download(f"{stem}_{SUFFIX}", YEAR)
        if path is None:
            raise RuntimeError(f"no se pudo descargar {stem}_{SUFFIX}")
        frame = pd.read_sas(path, format="xport", encoding="latin-1")
        frame = frame[[c for c in columns if c in frame.columns]]
        merged = frame if merged is None else merged.merge(frame, on="SEQN", how="left")
    rx_path = download(f"RXQ_RX_{SUFFIX}", YEAR)
    if rx_path is not None:
        merged = merged.merge(medication_flags(pd.read_sas(rx_path, format="xport", encoding="latin-1")), on="SEQN", how="left")
    # El modulo de sol (DEQ) se pregunto a adultos de 20 a 59.
    return merged[(merged["RIDAGEYR"] >= 20) & (merged["RIDAGEYR"] <= 59) & merged["DED120"].notna()]


def _rule_key(rule: dict[str, Any]) -> str:
    return f"{rule['field']} {rule['operator']} {rule.get('value')}"


def _auc(y: np.ndarray, score: np.ndarray) -> float | None:
    from sklearn.metrics import roc_auc_score

    return round(float(roc_auc_score(y, score)), 4) if 0 < y.sum() < len(y) else None


def rule_analysis(records: list[dict[str, Any]], seed: int = 42) -> dict[str, Any]:
    """Por condicion evaluable: precision/lift de cada regla, AUC del puntaje actual, del Modelo 1, del modelo NHANES
    y de una regresion logistica con las reglas como variables (validacion cruzada)."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict

    by_condition: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        for condition, actual in record["truth"].items():
            detail = record["details"].get(condition)
            if detail is None:
                continue
            by_condition.setdefault(condition, []).append({
                "actual": actual,
                "rules": {_rule_key(rule) for rule in detail.get("driver_details") or [] if not str(rule["field"]).startswith("lab_")},
                "rule_score": float(detail.get("rule_score") or 0.0),
                "model": float(detail.get("model_probability") or 0.0),
                "nhanes": record["nhanes"].get(condition),
            })

    out: dict[str, Any] = {}
    for condition, rows in sorted(by_condition.items()):
        y = np.array([row["actual"] for row in rows], dtype=int)
        prevalence = float(y.mean())
        rule_keys = sorted({key for row in rows for key in row["rules"]})
        per_rule = []
        for key in rule_keys:
            hits = np.array([key in row["rules"] for row in rows])
            if hits.sum() == 0:
                continue
            ppv = float(y[hits].mean())
            per_rule.append({"rule": key, "n_matched": int(hits.sum()), "precision": round(ppv, 4),
                             "lift": round(ppv / prevalence, 3) if prevalence else None})
        result: dict[str, Any] = {
            "n": len(rows),
            "prevalence": round(prevalence, 4),
            "auc_rule_score": _auc(y, np.array([row["rule_score"] for row in rows])),
            "auc_model1": _auc(y, np.array([row["model"] for row in rows])),
            "rules": per_rule,
        }
        nhanes = [(row["actual"], row["nhanes"]) for row in rows if row["nhanes"] is not None]
        if nhanes:
            result["auc_nhanes_model"] = _auc(np.array([a for a, _ in nhanes]), np.array([p for _, p in nhanes]))
        if rule_keys and y.sum() >= CV_FOLDS and (len(y) - y.sum()) >= CV_FOLDS:
            X = np.array([[key in row["rules"] for key in rule_keys] for row in rows], dtype=float)
            model = LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000)
            folds = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=seed)
            oof = cross_val_predict(model, X, y, cv=folds, method="predict_proba")[:, 1]
            result["auc_learned_rule_weights_cv"] = _auc(y, oof)
            model.fit(X, y)
            odds = {key: round(float(math.exp(coef)), 3) for key, coef in zip(rule_keys, model.coef_[0])}
            for item in per_rule:
                item["odds_ratio_multivariable"] = odds.get(item["rule"])
        out[condition] = result
    return out


def run(limit: int | None = None) -> dict[str, Any]:
    frame = load_frame()
    if limit:
        frame = frame.head(limit)
    report = PrecisionReport()
    analyzer = LabAnalysisService()
    feature_builder = FeatureBuilder()
    records = []
    for row in frame.to_dict(orient="records"):
        survey, reason = survey_from_nhanes(row)
        if survey is None:
            report.skip(reason)
            continue
        encuesta = EncuestaInput(**survey)
        values = lab_values(row)
        if not values:
            report.skip("sin_examenes")
            continue
        analysis = analyzer.analyze_manual(values, persist=False, source_note=SOURCE, context=_lab_patient_context(encuesta))
        truth = lab_truth(_statuses(analysis.get("biomarkers") or []))
        if not truth:
            report.skip("examen_sin_condicion_evaluable")
            continue
        details, lab_risks = survey_only_details(encuesta, feature_builder)
        report.add_pair(SOURCE, truth, predicted_conditions(details, lab_risks))
        nhanes_probability: dict[str, float] = {}
        for item in lab_risks:
            if item.get("condition"):
                nhanes_probability[item["condition"]] = max(nhanes_probability.get(item["condition"], 0.0), float(item["probability"]))
        records.append({"truth": truth, "details": {item["condition"]: item for item in details}, "nhanes": nhanes_probability})
    result = report.to_dict()
    result["rule_analysis"] = rule_analysis(records)
    result["population"] = "NHANES 2013-2014, adultos 20-59 con modulo de sol (DEQ_H); sin pesos muestrales"
    return result


def main(argv: list[str] | None = None) -> int:
    from scripts.validation.precision_real import print_summary, rows

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out-dir", type=Path, default=REPORT_DIR)
    args = parser.parse_args(argv)

    result = run(args.limit)
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    json_path = args.out_dir / f"precision_{SOURCE}_{stamp}.json"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    table = rows(result)
    with (args.out_dir / f"precision_{SOURCE}_{stamp}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(table[0]) if table else ["condition", "predictor"])
        writer.writeheader()
        writer.writerows(table)

    print_summary(result)
    print("\nAUC por condicion (puntaje de reglas | Modelo 1 | modelo NHANES | reglas con pesos aprendidos, CV):")
    for condition, data in result["rule_analysis"].items():
        print(f"  {condition:28} n={data['n']:5} prev={data['prevalence']:.2f}  "
              f"{data['auc_rule_score']} | {data['auc_model1']} | {data.get('auc_nhanes_model', '-')} | {data.get('auc_learned_rule_weights_cv', '-')}")
    print(f"\nreporte: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
