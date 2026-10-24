"""Modelo 1 con datos reales: predecir estado de laboratorio a partir del cuestionario (NHANES).

Tarea legitima (plan de fiabilidad, Fase 3): dado lo que un usuario puede responder en la encuesta
(demografia, antropometria, dieta, suplementos que toma, tabaco, actividad, sueno, salud autopercibida),
estimar la probabilidad de que un laboratorio este fuera de rango. El target proviene de laboratorios
REALES de NHANES con los cortes de `data/knowledge/biomarkers.csv`; ningun laboratorio entra como feature.

Diseno anti-fuga:
- Split TEMPORAL: entrena en el ciclo 2015-2016 (sufijo I), evalua en 2017-2018 (sufijo J).
- Umbrales de decision elegidos en una particion de validacion DENTRO del train, nunca en test.
- Calibracion (sigmoid, cv=3) ajustada en train; se reporta Brier y ECE en test.
- Se reporta el baseline de prevalencia para cada target.

Salidas:
- models/runtime/condition_lab_model.pkl  (pipelines por target + umbrales + contrato de features)
- data/reports/condition_model/nhanes_real_metrics.json / .csv
- models/runtime/condition_lab_model_card.json

Limitaciones (ver model card): poblacion de EE. UU., sin pesos muestrales, cuestionario NHANES != encuesta
SupleMatch (se documenta el mapeo), no es diagnostico.

Uso:
  python scripts/training/entrenar_condiciones_nhanes.py            # descarga (cache en data/raw/nhanes) y entrena
  python scripts/training/entrenar_condiciones_nhanes.py --quick    # submuestra para humo
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

# pandas 2.2: evitar el downcasting silencioso en fillna/where (comportamiento futuro por defecto).
pd.set_option("future.no_silent_downcasting", True)

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

# El runtime rechaza artefactos con otro contrato: la version vive alli para que no se desincronicen.
from app.ml.runtime.condition_lab_inference import FEATURE_CONTRACT_VERSION  # noqa: E402

RAW_ROOT = ROOT_DIR / "data" / "raw" / "nhanes"
REPORT_DIR = ROOT_DIR / "data" / "reports" / "condition_model"
MODEL_DIR = ROOT_DIR / "models" / "runtime"
MODEL_PATH = MODEL_DIR / "condition_lab_model.pkl"
MODEL_CARD_PATH = MODEL_DIR / "condition_lab_model_card.json"

CYCLES = {
    # B12 y acido metilmalonico solo se midieron en 2011-2012 (G) y 2013-2014 (H): split propio para B12.
    "2011_2012": {"year": "2011", "suffix": "G"},
    "2013_2014": {"year": "2013", "suffix": "H"},
    "2015_2016": {"year": "2015", "suffix": "I"},
    "2017_2018": {"year": "2017", "suffix": "J"},
    # Solo validacion externa (scripts/training/validar_condiciones_nhanes_externo.py); no entra al entrenamiento.
    "2021_2023": {"year": "2021", "suffix": "L"},
}
TRAIN_CYCLE = "2015_2016"
TEST_CYCLE = "2017_2018"
# Targets cuyo laboratorio no existe en I/J: (train, test) temporal propio.
TARGET_SPLITS: dict[str, tuple[str, str]] = {
    "target_b12_low": ("2011_2012", "2013_2014"),
}

# Archivos NHANES y columnas. Solo las de FEATURE_FILES pueden entrar como features.
FEATURE_FILES: dict[str, list[str]] = {
    "DEMO": ["SEQN", "RIAGENDR", "RIDAGEYR", "RIDRETH3", "RIDEXPRG", "INDFMPIR", "DMDEDUC2"],
    "BMX": ["SEQN", "BMXBMI", "BMXWT", "BMXHT"],
    "DSQTOT": ["SEQN", "DSDCOUNT", "DSQTVD", "DSQTIRON", "DSQTVB12", "DSQTFA", "DSQTCALC", "DSQTMAGN", "DSQTZINC", "DSQTVC"],
    "DR1TOT": ["SEQN", "DR1TKCAL", "DR1TPROT", "DR1TVD", "DR1TIRON", "DR1TVB12", "DR1TFA", "DR1TCALC", "DR1TMAGN", "DR1TZINC", "DR1TVC", "DR1TFIBE"],
    "SMQ": ["SEQN", "SMQ020", "SMQ040"],
    "PAQ": ["SEQN", "PAQ605", "PAQ620", "PAQ650", "PAQ665"],
    "ALQ": ["SEQN", "ALQ130"],
    "DIQ": ["SEQN", "DIQ010"],
    "SLQ": ["SEQN", "SLD012", "SLD010H", "SLQ050"],  # SLD010H: horas de sueno en G/H
    "HSQ": ["SEQN", "HSD010"],
}
LAB_FILES: dict[str, list[str]] = {
    "VID": ["SEQN", "LBXVIDMS"],      # nmol/L
    "FERTIN": ["SEQN", "LBXFER"],     # ng/mL
    "CBC": ["SEQN", "LBXHGB"],        # g/dL
    "GLU": ["SEQN", "LBXGLU"],        # mg/dL (ayunas)
    "TCHOL": ["SEQN", "LBXTC"],       # mg/dL
    "HDL": ["SEQN", "LBDHDD"],        # mg/dL
    "BIOPRO": ["SEQN", "LBXSATSI"],   # ALT U/L
    "GHB": ["SEQN", "LBXGH"],         # HbA1c %
    "VITB12": ["SEQN", "LBXB12", "LBDB12"],  # B12 serica pg/mL (solo G/H; LBXB12 en G, LBDB12 en H)
}
# Medicamentos que bajan la absorcion de B12 (NIH ODS): metformina e inhibidores de acido (IBP y anti-H2).
# RXQ_RX tiene una fila por medicamento; se agregan a si/no por persona (ver medication_flags).
METFORMIN_NAMES = ("METFORMIN",)
ACID_SUPPRESSOR_NAMES = (
    "OMEPRAZOLE", "ESOMEPRAZOLE", "LANSOPRAZOLE", "DEXLANSOPRAZOLE", "PANTOPRAZOLE", "RABEPRAZOLE",
    "RANITIDINE", "FAMOTIDINE", "CIMETIDINE", "NIZATIDINE",
)

CAT_FEATURES = ["sexo", "etnia", "educacion", "fuma", "actividad_vigorosa", "actividad_moderada", "diabetes_dx", "sueno_problemas", "salud_autopercibida", "embarazo", "metformina", "antiacidos"]
NUM_FEATURES = [
    "edad", "bmi", "peso_kg", "talla_cm", "ingreso_ratio",
    "sup_count", "sup_vit_d_mcg", "sup_hierro_mg", "sup_b12_mcg", "sup_folico_mcg", "sup_calcio_mg", "sup_magnesio_mg", "sup_zinc_mg", "sup_vit_c_mg",
    "dieta_kcal", "dieta_proteina_g", "dieta_vit_d_mcg", "dieta_hierro_mg", "dieta_b12_mcg", "dieta_folato_mcg", "dieta_calcio_mg", "dieta_magnesio_mg", "dieta_zinc_mg", "dieta_vit_c_mg", "dieta_fibra_g",
    "alcohol_tragos_dia", "sueno_horas",
]

# Restricciones de poblacion por target para que train y test sean comparables.
# Ferritina: en 2015-2016 NHANES solo la midio en mujeres de 12-49 anos; se restringe a mujeres 18-49 en ambos ciclos.
TARGET_POPULATION: dict[str, dict[str, Any]] = {
    "target_ferritin_low": {"sexo": "femenino", "edad_max": 49},
}


def population_mask(features: pd.DataFrame, target: str) -> pd.Series:
    rule = TARGET_POPULATION.get(target)
    mask = pd.Series(True, index=features.index)
    if not rule:
        return mask
    if "sexo" in rule:
        mask &= features["sexo"] == rule["sexo"]
    if "edad_max" in rule:
        mask &= features["edad"] <= rule["edad_max"]
    return mask


def biomarker_cutoffs() -> dict[str, dict[str, float | None]]:
    """Cortes por defecto desde data/knowledge/biomarkers.csv (fila sex=any)."""
    out: dict[str, dict[str, float | None]] = {}
    with (ROOT_DIR / "data/knowledge/biomarkers.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["sex"] != "any" or row["pregnant"] != "any" or row["age_min"] or row["age_max"]:
                continue
            out[row["biomarker_code"]] = {k: (float(row[k]) if row.get(k) else None) for k in ("low", "borderline", "high", "critical_low", "critical_high")}
    return out


def _col(frame: pd.DataFrame, name: str) -> pd.Series:
    """Columna numerica o NaN si el archivo no estaba disponible para ese ciclo."""
    if name in frame.columns:
        return pd.to_numeric(frame[name], errors="coerce")
    return pd.Series(np.nan, index=frame.index, dtype="float64")


def targets_from_labs(frame: pd.DataFrame, cutoffs: dict[str, dict[str, float | None]]) -> pd.DataFrame:
    """Targets binarios con los mismos cortes que usa el runtime de labs. 1 = fuera de rango en la direccion clinica.

    NaN cuando el laboratorio no existe para la persona o el archivo no esta disponible en el ciclo.
    """
    t = pd.DataFrame(index=frame.index)

    def flag(series: pd.Series, condition: pd.Series) -> pd.Series:
        return condition.astype("float64").where(series.notna())

    vitd_ng = _col(frame, "LBXVIDMS") * 0.4  # nmol/L -> ng/mL
    ferritin = _col(frame, "LBXFER")
    hgb = _col(frame, "LBXHGB")
    glu = _col(frame, "LBXGLU")
    tc = _col(frame, "LBXTC")
    hdl = _col(frame, "LBDHDD")
    alt = _col(frame, "LBXSATSI")
    hba1c = _col(frame, "LBXGH")
    b12 = _col(frame, "LBDB12").fillna(_col(frame, "LBXB12"))
    hb_cut = pd.Series(np.where(_col(frame, "RIAGENDR") == 1, 13.0, 12.0), index=frame.index)  # OMS 2024
    t["target_vitamin_d_low"] = flag(vitd_ng, vitd_ng < cutoffs["vitamin_d"]["low"])
    t["target_ferritin_low"] = flag(ferritin, ferritin < cutoffs["ferritin"]["low"])
    t["target_anemia"] = flag(hgb, hgb < hb_cut)
    t["target_glucose_high"] = flag(glu, glu >= cutoffs["glucose"]["high"])
    t["target_cholesterol_high"] = flag(tc, tc >= cutoffs["total_cholesterol"]["high"])
    t["target_hdl_low"] = flag(hdl, hdl < cutoffs["hdl"]["low"])
    t["target_alt_high"] = flag(alt, alt > cutoffs["alt"]["high"])
    t["target_hba1c_high"] = flag(hba1c, hba1c >= cutoffs["hba1c"]["high"])
    # B12 baja o limitrofe (< 300 pg/mL, NIH ODS): con < 200 la prevalencia adulta en NHANES es muy baja para aprender.
    t["target_b12_low"] = flag(b12, b12 < cutoffs["b12"]["borderline"])
    return t


def features_from_questionnaire(frame: pd.DataFrame) -> pd.DataFrame:
    """Mapea variables NHANES a features equivalentes a la encuesta SupleMatch. Ningun laboratorio."""
    f = pd.DataFrame(index=frame.index)
    f["sexo"] = frame["RIAGENDR"].map({1: "masculino", 2: "femenino"}).fillna("missing")
    f["edad"] = frame["RIDAGEYR"]
    f["etnia"] = frame.get("RIDRETH3", pd.Series(index=frame.index)).map({1: "mex", 2: "hisp_otro", 3: "blanco", 4: "negro", 6: "asiatico", 7: "otro"}).fillna("missing")
    f["educacion"] = frame.get("DMDEDUC2", pd.Series(index=frame.index)).map({1: "menos_9", 2: "9_11", 3: "secundaria", 4: "superior_incompleta", 5: "universitaria"}).fillna("missing")
    f["embarazo"] = frame.get("RIDEXPRG", pd.Series(index=frame.index)).map({1: "si", 2: "no", 3: "no_sabe"}).fillna("no_aplica")
    f["ingreso_ratio"] = frame.get("INDFMPIR")
    f["bmi"] = frame.get("BMXBMI")
    f["peso_kg"] = frame.get("BMXWT")
    f["talla_cm"] = frame.get("BMXHT")
    f["sup_count"] = frame.get("DSDCOUNT")
    for col, src in (("sup_vit_d_mcg", "DSQTVD"), ("sup_hierro_mg", "DSQTIRON"), ("sup_b12_mcg", "DSQTVB12"), ("sup_folico_mcg", "DSQTFA"), ("sup_calcio_mg", "DSQTCALC"), ("sup_magnesio_mg", "DSQTMAGN"), ("sup_zinc_mg", "DSQTZINC"), ("sup_vit_c_mg", "DSQTVC")):
        f[col] = frame.get(src)
    for col, src in (("dieta_kcal", "DR1TKCAL"), ("dieta_proteina_g", "DR1TPROT"), ("dieta_vit_d_mcg", "DR1TVD"), ("dieta_hierro_mg", "DR1TIRON"), ("dieta_b12_mcg", "DR1TVB12"), ("dieta_folato_mcg", "DR1TFA"), ("dieta_calcio_mg", "DR1TCALC"), ("dieta_magnesio_mg", "DR1TMAGN"), ("dieta_zinc_mg", "DR1TZINC"), ("dieta_vit_c_mg", "DR1TVC"), ("dieta_fibra_g", "DR1TFIBE")):
        f[col] = frame.get(src)
    smq020 = frame.get("SMQ020", pd.Series(index=frame.index))
    smq040 = frame.get("SMQ040", pd.Series(index=frame.index))
    f["fuma"] = np.select([smq020 == 2, smq040.isin([1, 2]), smq040 == 3], ["nunca", "actual", "ex"], default="missing")
    f["actividad_vigorosa"] = frame.get("PAQ605", pd.Series(index=frame.index)).map({1: "si", 2: "no"}).fillna(frame.get("PAQ650", pd.Series(index=frame.index)).map({1: "si", 2: "no"})).fillna("missing")
    f["actividad_moderada"] = frame.get("PAQ620", pd.Series(index=frame.index)).map({1: "si", 2: "no"}).fillna(frame.get("PAQ665", pd.Series(index=frame.index)).map({1: "si", 2: "no"})).fillna("missing")
    alq = frame.get("ALQ130", pd.Series(index=frame.index))
    f["alcohol_tragos_dia"] = alq.where(alq < 100)  # 777/999 = no sabe/rechaza
    f["diabetes_dx"] = frame.get("DIQ010", pd.Series(index=frame.index)).map({1: "si", 2: "no", 3: "borderline"}).fillna("missing")
    sld = frame.get("SLD012", pd.Series(index=frame.index)).fillna(frame.get("SLD010H", pd.Series(index=frame.index)))
    f["sueno_horas"] = sld.where(sld < 24)
    f["sueno_problemas"] = frame.get("SLQ050", pd.Series(index=frame.index)).map({1: "si", 2: "no"}).fillna("missing")
    f["salud_autopercibida"] = frame.get("HSD010", pd.Series(index=frame.index)).map({1: "excelente", 2: "muy_buena", 3: "buena", 4: "regular", 5: "mala"}).fillna("missing")
    for col in ("metformina", "antiacidos"):
        f[col] = frame.get(col, pd.Series("missing", index=frame.index)).fillna("missing")
    for col in NUM_FEATURES:
        if col not in f:
            f[col] = np.nan
        f[col] = pd.to_numeric(f[col], errors="coerce")
    return f[CAT_FEATURES + NUM_FEATURES]


def download(file_code: str, year: str, force: bool = False) -> Path | None:
    cycle_dir = RAW_ROOT / f"{year}_cycle"
    cycle_dir.mkdir(parents=True, exist_ok=True)
    path = cycle_dir / f"{file_code}.XPT"
    if path.exists() and not force:
        return path
    url = f"https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/{year}/DataFiles/{file_code}.XPT"
    try:
        with urlopen(Request(url, headers={"User-Agent": "SupleMatch-research/1.0"}), timeout=180) as response:
            data = response.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        print(f"  [WARN] no se pudo descargar {file_code}: {exc}")
        return None
    if len(data) < 5_000 or data[:30].lstrip().lower().startswith(b"<!doctype"):
        print(f"  [WARN] respuesta invalida para {file_code}")
        return None
    path.write_bytes(data)
    return path


def load_cycle(cycle: str, force: bool = False) -> pd.DataFrame:
    year, suffix = CYCLES[cycle]["year"], CYCLES[cycle]["suffix"]
    merged: pd.DataFrame | None = None
    for stem, columns in {**FEATURE_FILES, **LAB_FILES}.items():
        path = download(f"{stem}_{suffix}", year, force=force)
        if path is None:
            continue
        frame = pd.read_sas(path, format="xport", encoding="utf-8")
        frame = frame[[c for c in columns if c in frame.columns]]
        merged = frame if merged is None else merged.merge(frame, on="SEQN", how="left")
    if merged is None:
        raise RuntimeError(f"sin datos para {cycle}")
    rx_path = download(f"RXQ_RX_{suffix}", year, force=force)
    if rx_path is not None:
        merged = merged.merge(medication_flags(pd.read_sas(rx_path, format="xport", encoding="latin-1")), on="SEQN", how="left")
    merged["cycle"] = cycle
    return merged


def medication_flags(rx: pd.DataFrame) -> pd.DataFrame:
    """Una fila por persona con metformina/antiacidos "si" o "no" a partir de RXQ_RX (una fila por medicamento).

    RXDUSE=2 (no tomo medicamentos el ultimo mes) cuenta como "no"; sin respuesta queda faltante.
    """
    names = rx.get("RXDDRUG", pd.Series("", index=rx.index)).fillna("").astype(str).str.upper()
    rx = rx.assign(
        _metformina=names.str.contains("|".join(METFORMIN_NAMES)),
        _antiacidos=names.str.contains("|".join(ACID_SUPPRESSOR_NAMES)),
        _answered=rx.get("RXDUSE", pd.Series(index=rx.index)).isin([1, 2]),
    )
    grouped = rx.groupby("SEQN").agg(_metformina=("_metformina", "any"), _antiacidos=("_antiacidos", "any"), _answered=("_answered", "any"))
    out = pd.DataFrame(index=grouped.index)
    for col in ("metformina", "antiacidos"):
        out[col] = np.where(grouped[f"_{col}"], "si", np.where(grouped["_answered"], "no", "missing"))
    return out.reset_index()


def expected_calibration_error(y_true: np.ndarray, y_prob: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    ece = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (y_prob >= lo) & (y_prob < hi) if hi < 1.0 else (y_prob >= lo) & (y_prob <= hi)
        if mask.sum() == 0:
            continue
        ece += mask.mean() * abs(y_true[mask].mean() - y_prob[mask].mean())
    return float(ece)


def build_pipeline(seed: int):
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    pre = ColumnTransformer(
        [
            ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_FEATURES),
            ("num", Pipeline([("imp", SimpleImputer(strategy="median", add_indicator=True)), ("sc", StandardScaler())]), NUM_FEATURES),
        ]
    )
    clf = CalibratedClassifierCV(LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5, random_state=seed), method="sigmoid", cv=3)
    return Pipeline([("pre", pre), ("clf", clf)])


def choose_threshold(y_val: np.ndarray, p_val: np.ndarray) -> float:
    """Umbral que maximiza F1 en VALIDACION (nunca en test). Nunca por debajo de 0.30."""
    from sklearn.metrics import f1_score

    best_t, best_f1 = 0.5, -1.0
    for t in np.arange(0.30, 0.90, 0.02):
        f1 = f1_score(y_val, (p_val >= t).astype(int), zero_division=0)
        if f1 > best_f1:
            best_t, best_f1 = float(t), f1
    return best_t


def evaluate(y: np.ndarray, p: np.ndarray, threshold: float) -> dict[str, float]:
    from sklearn.metrics import average_precision_score, brier_score_loss, f1_score, precision_score, recall_score, roc_auc_score

    prevalence = float(y.mean())
    pred = (p >= threshold).astype(int)
    return {
        "n": int(len(y)),
        "prevalence": prevalence,
        "roc_auc": float(roc_auc_score(y, p)) if 0 < prevalence < 1 else float("nan"),
        "average_precision": float(average_precision_score(y, p)) if 0 < prevalence < 1 else float("nan"),
        "brier": float(brier_score_loss(y, p)),
        "brier_baseline_prevalence": float(np.mean((y - prevalence) ** 2)),
        "ece": expected_calibration_error(y, p),
        "threshold": threshold,
        "f1": float(f1_score(y, pred, zero_division=0)),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-age", type=int, default=18)
    parser.add_argument("--quick", action="store_true", help="submuestra 1500 filas por ciclo (humo)")
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--model-out", type=Path, default=MODEL_PATH)
    parser.add_argument("--drop-features", nargs="*", default=[], help="Ablacion: features que se fuerzan a faltante (p. ej. fuma salud_autopercibida).")
    parser.add_argument("--report-suffix", default="", help="Sufijo para metricas y model card (ablaciones); vacio = artefacto oficial.")
    args = parser.parse_args()
    unknown = set(args.drop_features) - set(CAT_FEATURES + NUM_FEATURES)
    if unknown:
        parser.error(f"--drop-features desconocidas: {sorted(unknown)}")

    import joblib

    rng = np.random.RandomState(args.seed)
    cutoffs = biomarker_cutoffs()
    frames = {}
    needed = [TRAIN_CYCLE, TEST_CYCLE] + [c for split in TARGET_SPLITS.values() for c in split if c not in (TRAIN_CYCLE, TEST_CYCLE)]
    for cycle in dict.fromkeys(needed):
        print(f"Cargando {cycle}...")
        frame = load_cycle(cycle, force=args.force_download)
        frame = frame[frame["RIDAGEYR"] >= args.min_age]
        if args.quick:
            frame = frame.sample(min(1500, len(frame)), random_state=args.seed)
        frames[cycle] = frame.reset_index(drop=True)
        print(f"  filas adultos: {len(frame)}")

    x_by_cycle = {cycle: features_from_questionnaire(frame) for cycle, frame in frames.items()}
    t_by_cycle = {cycle: targets_from_labs(frame, cutoffs) for cycle, frame in frames.items()}
    assert not any(col.startswith(("LBX", "LBD")) for x in x_by_cycle.values() for col in x.columns), "fuga: laboratorio en features"
    for col in args.drop_features:  # ablacion: simula una encuesta que no pregunta esa variable
        for frame_ in x_by_cycle.values():
            frame_[col] = "missing" if col in CAT_FEATURES else np.nan

    models: dict[str, Any] = {}
    thresholds: dict[str, float] = {}
    metrics: dict[str, dict[str, Any]] = {}
    for target in t_by_cycle[TRAIN_CYCLE].columns:
        train_cycle, test_cycle = TARGET_SPLITS.get(target, (TRAIN_CYCLE, TEST_CYCLE))
        x_train_all, t_train_all = x_by_cycle[train_cycle], t_by_cycle[train_cycle]
        x_test_all, t_test_all = x_by_cycle[test_cycle], t_by_cycle[test_cycle]
        mask_tr = t_train_all[target].notna() & population_mask(x_train_all, target)
        mask_te = t_test_all[target].notna() & population_mask(x_test_all, target)
        y_tr = t_train_all.loc[mask_tr, target].astype(int).to_numpy()
        x_tr = x_train_all.loc[mask_tr]
        y_te = t_test_all.loc[mask_te, target].astype(int).to_numpy()
        x_te = x_test_all.loc[mask_te]
        if len(y_tr) < 200 or y_tr.sum() < 20 or len(y_te) < 100:
            metrics[target] = {"skipped": True, "n_train": int(len(y_tr)), "positives_train": int(y_tr.sum()), "n_test": int(len(y_te))}
            print(f"  {target}: omitido (train={len(y_tr)}, positivos={int(y_tr.sum())}, test={len(y_te)})")
            continue
        # particion de validacion dentro del train para el umbral
        idx = rng.permutation(len(y_tr))
        n_val = max(100, int(0.2 * len(y_tr)))
        val_idx, fit_idx = idx[:n_val], idx[n_val:]
        pipe = build_pipeline(args.seed)
        pipe.fit(x_tr.iloc[fit_idx], y_tr[fit_idx])
        threshold = choose_threshold(y_tr[val_idx], pipe.predict_proba(x_tr.iloc[val_idx])[:, 1])
        # reentrenar con todo el train y evaluar en el ciclo de test
        pipe = build_pipeline(args.seed)
        pipe.fit(x_tr, y_tr)
        p_te = pipe.predict_proba(x_te)[:, 1]
        result = evaluate(y_te, p_te, threshold)
        result.update({"n_train": int(len(y_tr)), "positives_train": int(y_tr.sum()), "train_cycle": train_cycle, "test_cycle": test_cycle, "population": TARGET_POPULATION.get(target, {"all_adults": True})})
        metrics[target] = result
        models[target] = pipe
        thresholds[target] = threshold
        print(f"  {target}: AUC={result['roc_auc']:.3f} AP={result['average_precision']:.3f} Brier={result['brier']:.3f} (base {result['brier_baseline_prevalence']:.3f}) ECE={result['ece']:.3f} prev={result['prevalence']:.2f} thr={threshold:.2f} F1={result['f1']:.2f}")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"_{args.report_suffix}" if args.report_suffix else ""
    (REPORT_DIR / f"nhanes_real_metrics{suffix}.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    rows = [{"target": k, **{kk: vv for kk, vv in v.items()}} for k, v in metrics.items()]
    pd.DataFrame(rows).to_csv(REPORT_DIR / f"nhanes_real_metrics{suffix}.csv", index=False)

    args.model_out.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "models": models,
        "thresholds": thresholds,
        "cat_features": CAT_FEATURES,
        "num_features": NUM_FEATURES,
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "train_cycle": TRAIN_CYCLE,
        "test_cycle": TEST_CYCLE,
        "target_splits": TARGET_SPLITS,
        "cutoffs": cutoffs,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    joblib.dump(artifact, args.model_out)
    digest = hashlib.sha256(args.model_out.read_bytes()).hexdigest()[:16]
    card = {
        "model": "condition_lab_model",
        "sha256_16": digest,
        "task": "Probabilidad de laboratorio fuera de rango a partir del cuestionario (sin laboratorios como entrada).",
        "data": {"source": "NHANES (CDC)", "train": TRAIN_CYCLE, "test": TEST_CYCLE, "min_age": args.min_age, "quick": args.quick,
                 "n_train_adults": int(len(frames[TRAIN_CYCLE])), "n_test_adults": int(len(frames[TEST_CYCLE]))},
        "targets_and_cutoffs": {
            "target_vitamin_d_low": f"25-OH-D < {cutoffs['vitamin_d']['low']} ng/mL (NIH ODS; NHANES en nmol/L x0.4)",
            "target_ferritin_low": f"ferritina < {cutoffs['ferritin']['low']} ng/mL",
            "target_anemia": "Hb < 13 g/dL hombres, < 12 g/dL mujeres (OMS 2024)",
            "target_glucose_high": f"glucosa ayunas >= {cutoffs['glucose']['high']} mg/dL",
            "target_cholesterol_high": f"colesterol total >= {cutoffs['total_cholesterol']['high']} mg/dL",
            "target_hdl_low": f"HDL < {cutoffs['hdl']['low']} mg/dL",
            "target_alt_high": f"ALT > {cutoffs['alt']['high']} U/L",
            "target_hba1c_high": f"HbA1c >= {cutoffs['hba1c']['high']} % (prediabetes o diabetes)",
            "target_b12_low": f"B12 serica < {cutoffs['b12']['borderline']} pg/mL (baja o limitrofe, NIH ODS); train 2011-2012, test 2013-2014",
        },
        "features": {"categorical": CAT_FEATURES, "numeric": NUM_FEATURES, "contract_version": FEATURE_CONTRACT_VERSION, "dropped_for_ablation": list(args.drop_features)},
        "algorithm": "LogisticRegression (balanced, C=0.5) + CalibratedClassifierCV(sigmoid, cv=3); umbral por F1 en validacion interna, minimo 0.30",
        "metrics_test": metrics,
        "limitations": [
            "Poblacion de EE. UU.; no validado en Peru. Validar anemia con ENDES antes de usar DEFICIT_HIERRO en produccion.",
            "Sin pesos muestrales de NHANES: metricas no representan prevalencia poblacional.",
            "El cuestionario NHANES no es la encuesta SupleMatch: el mapeo de features es aproximado (ver features_from_questionnaire).",
            "No es diagnostico. Salida = probabilidad calibrada de laboratorio fuera de rango, para priorizar recomendaciones y sugerir un examen.",
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    card_path = MODEL_CARD_PATH if not suffix else REPORT_DIR / f"condition_lab_model_card{suffix}.json"
    card_path.write_text(json.dumps(card, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"modelo: {args.model_out}\nmodel card: {card_path}\nmetricas: {REPORT_DIR / f'nhanes_real_metrics{suffix}.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
