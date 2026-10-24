"""Validacion peruana del target de anemia con ENDES (INEI): hemoglobina medida en mujeres 15-49.

Responde: ¿el modelo real entrenado con NHANES (EE. UU.) predice anemia en mujeres peruanas?
Tres evaluaciones, todas con split temporal (ENDES 2022 -> ENDES 2024):
  (a) modelo NHANES tal cual (`condition_lab_model.pkl`, target_anemia) sobre ENDES 2022 y 2024;
  (b) el mismo modelo recalibrado (isotonica) con ENDES 2022, evaluado en 2024;
  (c) modelo nativo ENDES (regresion logistica con altitud, region, urbano, riqueza, educacion, IMC, embarazo,
      tabaco, diabetes) entrenado en 2022 y evaluado en 2024: techo alcanzable con datos peruanos.

Target oficial: `V457` in {1,2,3} (anemia severa/moderada/leve segun INEI, hemoglobina ajustada por altitud).
Se contrasta con el corte OMS sobre `V456` (<12.0 g/dL no embarazada, <11.0 embarazada).

Modulos: REC42 (peso, talla, Hb), REC0111 (edad, region, urbano, educacion, riqueza, factor), RE223132 (embarazo),
RECH0 (altitud), CSALUD01 (tabaco, diabetes, hipertension; una persona 15+ por hogar).

Uso:
  python scripts/training/validar_anemia_endes.py            # requiere data/raw/endes/{2022,2024}/csv/*.csv
  python scripts/training/validar_anemia_endes.py --quick    # submuestra
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

pd.set_option("future.no_silent_downcasting", True)

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from scripts.training.entrenar_condiciones_nhanes import (  # noqa: E402
    CAT_FEATURES,
    NUM_FEATURES,
    MODEL_PATH as NHANES_MODEL_PATH,
    choose_threshold,
    evaluate,
)

ENDES_ROOT = ROOT_DIR / "data" / "raw" / "endes"
REPORT_DIR = ROOT_DIR / "data" / "reports" / "condition_model"
MODEL_DIR = ROOT_DIR / "models" / "runtime"
ENDES_MODEL_PATH = MODEL_DIR / "anemia_endes_model.pkl"
ENDES_MODEL_CARD = MODEL_DIR / "anemia_endes_model_card.json"
TRAIN_YEAR, TEST_YEAR = "2022", "2024"

ENDES_CAT = ["embarazo", "urbano", "educacion_endes", "fuma", "diabetes_dx", "hipertension_dx"]
ENDES_NUM = ["edad", "bmi", "altitud_m", "riqueza_quintil", "region_codigo"]


def read_module(year: str, name: str, columns: set[str]) -> pd.DataFrame:
    path = ENDES_ROOT / year / "csv" / f"{name}.csv"
    frame = pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig", usecols=lambda c: c in columns, dtype=str)
    return frame


def norm_key(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip()


def caseid_parts(caseid: pd.Series) -> tuple[pd.Series, pd.Series]:
    """CASEID = HHID (con espacios a la izquierda) + 2 espacios + numero de linea."""
    text = caseid.astype(str)
    hhid = text.str[:-3].str.strip()
    line = pd.to_numeric(text.str[-3:].str.strip(), errors="coerce")
    return hhid, line


def anemia_target_from_v457(v457: pd.Series) -> pd.Series:
    code = pd.to_numeric(v457, errors="coerce")
    target = pd.Series(np.nan, index=v457.index, dtype="float64")
    target[code.isin([1, 2, 3])] = 1.0
    target[code == 4] = 0.0
    return target


def anemia_target_who(v456_adjusted: pd.Series, pregnant: pd.Series) -> pd.Series:
    hb = pd.to_numeric(v456_adjusted, errors="coerce") / 10.0
    cut = np.where(pregnant == 1, 11.0, 12.0)
    return (hb < cut).astype("float64").where(hb.notna())


def load_women(year: str, quick: bool = False, seed: int = 42) -> pd.DataFrame:
    r42 = read_module(year, "REC42", {"CASEID", "V437", "V438", "V445", "V453", "V455", "V456", "V457"})
    r01 = read_module(year, "REC0111", {"CASEID", "HHID", "V012", "V024", "V025", "V106", "V190", "V005"})
    re2 = read_module(year, "RE223132", {"CASEID", "V213"})
    h0 = read_module(year, "RECH0", {"HHID", "HV040"})
    cs = read_module(year, "CSALUD01", {"HHID", "QSNUMERO", "QS102", "QS109", "QS200", "QS201", "QS202", "QS208", "QS210"})

    for frame in (r42, r01, re2):
        frame["CASEID"] = norm_key(frame["CASEID"])
    women = r42.merge(r01, on="CASEID", how="inner").merge(re2, on="CASEID", how="left")
    women["HHID_key"], women["line"] = caseid_parts(women["CASEID"])
    h0["HHID_key"] = norm_key(h0["HHID"])
    women = women.merge(h0[["HHID_key", "HV040"]], on="HHID_key", how="left")
    cs["HHID_key"] = norm_key(cs["HHID"])
    cs["line"] = pd.to_numeric(cs["QSNUMERO"], errors="coerce")
    women = women.merge(cs.drop(columns=["HHID", "QSNUMERO"]), on=["HHID_key", "line"], how="left")

    # medicion valida de hemoglobina
    women = women[pd.to_numeric(women["V455"], errors="coerce") == 0].copy()
    women["year"] = year
    if quick:
        women = women.sample(min(3000, len(women)), random_state=seed)
    return women.reset_index(drop=True)


def features_from_endes(women: pd.DataFrame) -> pd.DataFrame:
    """Features del contrato NHANES (lo que la encuesta SupleMatch puede dar) + columnas propias de ENDES."""
    f = pd.DataFrame(index=women.index)
    num = lambda col: pd.to_numeric(women.get(col), errors="coerce")  # noqa: E731
    f["sexo"] = "femenino"
    f["edad"] = num("V012")
    f["etnia"] = "missing"
    v106 = num("V106")
    f["educacion"] = v106.map({0: "menos_9", 1: "menos_9", 2: "secundaria", 3: "universitaria"}).fillna("missing").astype(str)
    pregnant = num("V213").fillna(0)
    f["embarazo"] = np.where(pregnant == 1, "si", "no")
    f["ingreso_ratio"] = np.nan  # V190 es quintil de riqueza, no ratio de pobreza: no se traduce
    bmi = num("V445")
    f["bmi"] = (bmi / 100.0).where(bmi < 9000)
    f["peso_kg"] = num("V437") / 10.0
    f["talla_cm"] = num("V438") / 10.0
    for col in NUM_FEATURES:
        if col.startswith(("sup_", "dieta_")):
            f[col] = np.nan
    f["sup_count"] = np.nan
    qs200, qs201 = num("QS200"), num("QS201")
    f["fuma"] = np.select([qs201 == 1, (qs200 == 1) & (qs201 == 2), qs200 == 2], ["actual", "ex", "nunca"], default="missing")
    f["actividad_vigorosa"] = "missing"
    f["actividad_moderada"] = "missing"
    qs208 = num("QS208")
    f["alcohol_tragos_dia"] = np.where(qs208 == 2, 0.0, np.nan)
    f["diabetes_dx"] = num("QS109").map({1: "si", 2: "no"}).fillna("missing").astype(str)
    f["sueno_horas"] = np.nan
    f["sueno_problemas"] = "missing"
    f["salud_autopercibida"] = "missing"
    # columnas propias de ENDES (para el modelo nativo)
    f["altitud_m"] = num("HV040")
    f["urbano"] = num("V025").map({1: "urbano", 2: "rural"}).fillna("missing").astype(str)
    f["educacion_endes"] = v106.map({0: "sin_nivel", 1: "primaria", 2: "secundaria", 3: "superior"}).fillna("missing").astype(str)
    f["riqueza_quintil"] = num("V190")
    f["region_codigo"] = num("V024")
    f["hipertension_dx"] = num("QS102").map({1: "si", 2: "no"}).fillna("missing").astype(str)
    f["peso_muestral"] = num("V005") / 1_000_000.0
    for col in NUM_FEATURES + ENDES_NUM:
        f[col] = pd.to_numeric(f[col], errors="coerce")
    return f


def ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    from scripts.training.entrenar_condiciones_nhanes import expected_calibration_error

    return expected_calibration_error(y, p, bins)


def build_endes_pipeline(seed: int):
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    pre = ColumnTransformer(
        [
            ("cat", OneHotEncoder(handle_unknown="ignore"), ENDES_CAT),
            ("num", Pipeline([("imp", SimpleImputer(strategy="median", add_indicator=True)), ("sc", StandardScaler())]), ENDES_NUM),
        ]
    )
    clf = CalibratedClassifierCV(LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5, random_state=seed), method="sigmoid", cv=3)
    return Pipeline([("pre", pre), ("clf", clf)])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-age", type=int, default=18)
    parser.add_argument("--max-age", type=int, default=49)
    args = parser.parse_args()

    import joblib
    from sklearn.isotonic import IsotonicRegression

    rng = np.random.RandomState(args.seed)
    data: dict[str, dict[str, Any]] = {}
    for year in (TRAIN_YEAR, TEST_YEAR):
        women = load_women(year, quick=args.quick, seed=args.seed)
        feats = features_from_endes(women)
        mask = (feats["edad"] >= args.min_age) & (feats["edad"] <= args.max_age)
        feats = feats[mask].reset_index(drop=True)
        women = women[mask].reset_index(drop=True)
        y_official = anemia_target_from_v457(women["V457"])
        y_who = anemia_target_who(women["V456"], pd.to_numeric(women["V213"], errors="coerce").fillna(0))
        keep = y_official.notna()
        data[year] = {"x": feats[keep].reset_index(drop=True), "y": y_official[keep].to_numpy().astype(int), "y_who": y_who[keep].to_numpy(), "n_raw": int(len(women))}
        w = data[year]["x"]["peso_muestral"].to_numpy()
        prev_w = float(np.average(data[year]["y"], weights=np.nan_to_num(w, nan=0.0))) if np.nansum(w) > 0 else float("nan")
        agree = float(np.nanmean(data[year]["y"] == data[year]["y_who"]))
        print(f"ENDES {year}: mujeres {args.min_age}-{args.max_age} con Hb valida = {len(data[year]['y'])}  prevalencia anemia (V457) = {data[year]['y'].mean():.3f}  ponderada = {prev_w:.3f}  acuerdo V457 vs corte OMS sobre V456 = {agree:.3f}")
        data[year]["prevalence_weighted"] = prev_w
        data[year]["agreement_v457_vs_who"] = agree

    results: dict[str, Any] = {"population": f"mujeres {args.min_age}-{args.max_age}, hemoglobina medida (V455=0)", "quick": args.quick}

    # (a) NHANES model as-is
    nhanes = joblib.load(NHANES_MODEL_PATH)
    pipe = nhanes["models"]["target_anemia"]
    thr = float(nhanes["thresholds"]["target_anemia"])
    cols = list(nhanes["cat_features"]) + list(nhanes["num_features"])
    probs = {}
    for year in (TRAIN_YEAR, TEST_YEAR):
        x = data[year]["x"].reindex(columns=cols)
        probs[year] = pipe.predict_proba(x)[:, 1]
        results[f"nhanes_as_is_{year}"] = evaluate(data[year]["y"], probs[year], thr)
        r = results[f"nhanes_as_is_{year}"]
        print(f"(a) NHANES tal cual en ENDES {year}: AUC={r['roc_auc']:.3f} AP={r['average_precision']:.3f} Brier={r['brier']:.3f} (base {r['brier_baseline_prevalence']:.3f}) ECE={r['ece']:.3f} F1={r['f1']:.2f} recall={r['recall']:.2f}")

    # (b) recalibrated on 2022, evaluated on 2024
    iso = IsotonicRegression(out_of_bounds="clip").fit(probs[TRAIN_YEAR], data[TRAIN_YEAR]["y"])
    p_cal_train = iso.predict(probs[TRAIN_YEAR])
    idx = rng.permutation(len(p_cal_train)); n_val = max(200, len(idx) // 5)
    thr_cal = choose_threshold(data[TRAIN_YEAR]["y"][idx[:n_val]], p_cal_train[idx[:n_val]])
    p_cal_test = iso.predict(probs[TEST_YEAR])
    results["nhanes_recalibrated_2024"] = evaluate(data[TEST_YEAR]["y"], p_cal_test, thr_cal)
    r = results["nhanes_recalibrated_2024"]
    print(f"(b) NHANES recalibrado (isotonica 2022) en ENDES 2024: AUC={r['roc_auc']:.3f} Brier={r['brier']:.3f} ECE={r['ece']:.3f} thr={thr_cal:.2f} F1={r['f1']:.2f}")

    # (c) ENDES-native model
    x_tr, y_tr = data[TRAIN_YEAR]["x"], data[TRAIN_YEAR]["y"]
    x_te, y_te = data[TEST_YEAR]["x"], data[TEST_YEAR]["y"]
    idx = rng.permutation(len(y_tr)); n_val = max(200, len(idx) // 5)
    fit_idx, val_idx = idx[n_val:], idx[:n_val]
    native = build_endes_pipeline(args.seed).fit(x_tr.iloc[fit_idx], y_tr[fit_idx])
    thr_native = choose_threshold(y_tr[val_idx], native.predict_proba(x_tr.iloc[val_idx])[:, 1])
    native = build_endes_pipeline(args.seed).fit(x_tr, y_tr)
    p_native = native.predict_proba(x_te)[:, 1]
    results["endes_native_2024"] = evaluate(y_te, p_native, thr_native)
    r = results["endes_native_2024"]
    print(f"(c) Modelo nativo ENDES (2022 -> 2024): AUC={r['roc_auc']:.3f} AP={r['average_precision']:.3f} Brier={r['brier']:.3f} ECE={r['ece']:.3f} thr={thr_native:.2f} F1={r['f1']:.2f}")

    # importancia aproximada: coeficientes medios de la regresion calibrada
    try:
        names = native.named_steps["pre"].get_feature_names_out()
        coefs = np.mean([est.estimator.coef_[0] for est in native.named_steps["clf"].calibrated_classifiers_], axis=0)
        top = sorted(zip(names, coefs), key=lambda t: -abs(t[1]))[:12]
        results["endes_native_top_coefficients"] = [{"feature": str(n), "coef": float(c)} for n, c in top]
        print("    coeficientes (|mayor| primero):", ", ".join(f"{n}={c:+.2f}" for n, c in top[:8]))
    except Exception as exc:  # estructura interna de sklearn puede cambiar
        results["endes_native_top_coefficients"] = f"no disponible: {exc}"

    results["data"] = {y: {"n": int(len(data[y]["y"])), "n_raw_women": data[y]["n_raw"], "prevalence": float(data[y]["y"].mean()), "prevalence_weighted": data[y]["prevalence_weighted"], "agreement_v457_vs_who_cutoff": data[y]["agreement_v457_vs_who"]} for y in (TRAIN_YEAR, TEST_YEAR)}
    results["nhanes_model_sha256_16"] = hashlib.sha256(NHANES_MODEL_PATH.read_bytes()).hexdigest()[:16]
    results["generated_at"] = datetime.now(timezone.utc).isoformat()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "endes_anemia_validation.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    rows = [{"evaluation": k, **v} for k, v in results.items() if isinstance(v, dict) and "roc_auc" in v]
    pd.DataFrame(rows).to_csv(REPORT_DIR / "endes_anemia_validation.csv", index=False)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": native, "threshold": thr_native, "cat_features": ENDES_CAT, "num_features": ENDES_NUM, "train_year": TRAIN_YEAR, "test_year": TEST_YEAR,
                 "recalibrator_for_nhanes_model": iso, "recalibrated_threshold": thr_cal, "trained_at": results["generated_at"]}, ENDES_MODEL_PATH)
    card = {
        "model": "anemia_endes_model",
        "sha256_16": hashlib.sha256(ENDES_MODEL_PATH.read_bytes()).hexdigest()[:16],
        "task": "Probabilidad de anemia (V457 INEI) en mujeres 18-49 peruanas desde variables de encuesta; incluye altitud y region.",
        "data": {"source": "ENDES (INEI) via datosabiertos.gob.pe", "train": TRAIN_YEAR, "test": TEST_YEAR, **results["data"]},
        "features": {"categorical": ENDES_CAT, "numeric": ENDES_NUM},
        "metrics_test": results["endes_native_2024"],
        "nhanes_model_on_endes": {k: v for k, v in results.items() if k.startswith("nhanes_")},
        "limitations": ["Solo mujeres 15-49 (ENDES no mide hemoglobina en hombres adultos).", "Sin pesos muestrales en el ajuste; prevalencia ponderada solo informativa.", "La encuesta SupleMatch no pregunta altitud/region: para usar este modelo habria que anadir ciudad o region.", "No es diagnostico."],
        "generated_at": results["generated_at"],
    }
    ENDES_MODEL_CARD.write_text(json.dumps(card, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"reporte: {REPORT_DIR / 'endes_anemia_validation.json'}\nmodelo nativo: {ENDES_MODEL_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
