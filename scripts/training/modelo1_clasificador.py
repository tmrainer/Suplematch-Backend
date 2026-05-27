"""
Modelo 1 — Clasificador multi-label de condiciones vitamínicas
Input  : encuesta_sintetica.csv (encuesta sintomatológica)
Output : condicion_predicha (ej: DEFICIT_VIT_D|BAJA_INMUNIDAD)
Guarda : modelo1_pipeline.pkl  (pipeline completo listo para inferencia)
"""

import pandas as pd
import numpy as np
import joblib
import warnings
warnings.filterwarnings("ignore")

from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.multioutput import MultiOutputClassifier
from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (classification_report, hamming_loss,
                              f1_score, accuracy_score)
from sklearn.utils import resample

# ─── 1. Cargar datos ───────────────────────────────────────────────────────────
df = pd.read_csv("encuesta_sintetica.csv")
print(f"Dataset: {df.shape[0]} filas, {df.shape[1]} columnas")

# ─── 2. Binarizar etiquetas (multi-label) ─────────────────────────────────────
LABELS = [
    "DEFICIT_VIT_D",
    "DEFICIT_B12",
    "DEFICIT_HIERRO",
    "DEFICIT_MAGNESIO",
    "BAJA_INMUNIDAD",
    "RENDIMIENTO_DEPORTIVO",
    "SALUD_CAPILAR_PIEL",
    "FATIGA_CRONICA",
]
# SALUDABLE = todas las etiquetas en 0 (no requiere columna propia)

for label in LABELS:
    df[label] = df["condicion"].str.contains(label).astype(int)

Y = df[LABELS].values
print(f"\nEtiquetas ({len(LABELS)}):", LABELS)
print("Distribución por etiqueta:")
for i, label in enumerate(LABELS):
    pos = Y[:, i].sum()
    print(f"  {label:<30} {pos:>5} ({pos/len(Y)*100:.1f}%)")

saludable_count = (Y.sum(axis=1) == 0).sum()
print(f"  {'SALUDABLE (sin deficit)':<30} {saludable_count:>5} ({saludable_count/len(Y)*100:.1f}%)")

# ─── 3. Features ──────────────────────────────────────────────────────────────
CAT_COLS = ["sexo", "tipo_dieta", "exposicion_solar", "nivel_actividad"]
NUM_COLS = [
    "edad", "peso_kg", "altura_cm",
    "fatiga_general", "dolor_muscular", "dolor_articular", "niebla_mental",
    "problemas_sueno", "caida_cabello", "piel_seca", "unas_quebradizas",
    "enfermedad_frecuente", "calambres", "irritabilidad",
    "meta_energia", "meta_inmunidad", "meta_belleza", "meta_rendimiento",
    "meta_salud_osea", "meta_cognitivo",
]

X = df[CAT_COLS + NUM_COLS]

# ─── 4. Train/test split ──────────────────────────────────────────────────────
X_train, X_test, y_train, y_test = train_test_split(
    X, Y, test_size=0.2, random_state=42
)
print(f"\nTrain: {len(X_train)} | Test: {len(X_test)}")

# ─── 4b. Oversample clases minoritarias en train ──────────────────────────────
# FATIGA_CRONICA tiene ~4% → duplicar hasta ~15% para que el modelo la aprenda
FATIGA_IDX = LABELS.index("FATIGA_CRONICA")
fatiga_mask = y_train[:, FATIGA_IDX] == 1
X_train_np = X_train.values
X_fat  = X_train_np[fatiga_mask]
y_fat  = y_train[fatiga_mask]
target_count = max(int(len(X_train) * 0.15), fatiga_mask.sum() * 3)
n_to_add = target_count - fatiga_mask.sum()

if n_to_add > 0:
    X_over, y_over = resample(X_fat, y_fat, n_samples=n_to_add,
                               random_state=42, replace=True)
    X_train_np = np.vstack([X_train_np, X_over])
    y_train    = np.vstack([y_train, y_over])
    X_train = pd.DataFrame(X_train_np, columns=X_train.columns)
    pct = y_train[:, FATIGA_IDX].mean() * 100
    print(f"Oversampling FATIGA_CRONICA: {fatiga_mask.sum()} → {y_train[:,FATIGA_IDX].sum()} casos ({pct:.1f}%)")

# ─── 5. Preprocesador ─────────────────────────────────────────────────────────
preprocessor = ColumnTransformer([
    ("num", StandardScaler(), NUM_COLS),
    ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CAT_COLS),
])

# ─── 6. Modelos ───────────────────────────────────────────────────────────────
# RF nativo multi-output: 1 modelo × 100 árboles (vs MultiOutputClassifier: 8 × 100 = 800)
models = {
    "RandomForest": Pipeline([
        ("prep", preprocessor),
        ("clf", RandomForestClassifier(n_estimators=100, max_depth=8,
                                       min_samples_leaf=3, class_weight="balanced",
                                       random_state=42, n_jobs=-1)),
    ]),
    "ExtraTrees": Pipeline([
        ("prep", preprocessor),
        ("clf", ExtraTreesClassifier(n_estimators=100, max_depth=8,
                                     min_samples_leaf=3, class_weight="balanced",
                                     random_state=42, n_jobs=-1)),
    ]),
}

best_model_name = None
best_f1 = -1
best_pipeline = None

print("\n" + "="*60)
for name, pipe in models.items():
    pipe.fit(X_train, y_train)
    y_pred = pipe.predict(X_test)

    hl   = hamming_loss(y_test, y_pred)
    f1m  = f1_score(y_test, y_pred, average="macro", zero_division=0)
    f1s  = f1_score(y_test, y_pred, average="samples", zero_division=0)
    exact = accuracy_score(y_test, y_pred)

    print(f"\n── {name} ──────────────────────────────")
    print(f"  Hamming Loss  : {hl:.4f}  (menor = mejor)")
    print(f"  F1 Macro      : {f1m:.4f}")
    print(f"  F1 Samples    : {f1s:.4f}")
    print(f"  Exact Match   : {exact:.4f}")

    print(f"\n  Por etiqueta:")
    f1_per = f1_score(y_test, y_pred, average=None, zero_division=0)
    for label, f1 in zip(LABELS, f1_per):
        bar = "█" * int(f1 * 20)
        print(f"    {label:<30} F1={f1:.2f}  {bar}")

    if f1s > best_f1:
        best_f1 = f1s
        best_model_name = name
        best_pipeline = pipe  # ya es Pipeline completo con prep+clf

print(f"\n{'='*60}")
print(f"Mejor modelo: {best_model_name}  (F1-samples={best_f1:.4f})")

# ─── 7. Guardar pipeline ──────────────────────────────────────────────────────
MODEL_PATH = "modelo1_pipeline.pkl"
joblib.dump({
    "pipeline": best_pipeline,
    "labels": LABELS,
    "cat_cols": CAT_COLS,
    "num_cols": NUM_COLS,
}, MODEL_PATH)
print(f"Pipeline guardado: {MODEL_PATH}")

# ─── 8. Función de inferencia (demo) ──────────────────────────────────────────
def predecir_condicion(usuario: dict) -> list[str]:
    """
    usuario: dict con todos los campos de la encuesta
    retorna: lista de condiciones detectadas (vacía = SALUDABLE)
    """
    artifact = joblib.load(MODEL_PATH)
    pipe     = artifact["pipeline"]
    labels   = artifact["labels"]
    cols     = artifact["cat_cols"] + artifact["num_cols"]
    row      = pd.DataFrame([usuario])[cols]
    pred     = pipe.predict(row)[0]
    detected = [labels[i] for i, v in enumerate(pred) if v == 1]
    return detected if detected else ["SALUDABLE"]


# ─── Demo con un usuario de ejemplo ───────────────────────────────────────────
print("\n── Demo inferencia ─────────────────────────────────────────")
usuario_ejemplo = {
    "sexo": "F",
    "tipo_dieta": "vegano",
    "exposicion_solar": "baja",
    "nivel_actividad": "sedentario",
    "edad": 28,
    "peso_kg": 58.0,
    "altura_cm": 163.0,
    "fatiga_general": 4,
    "dolor_muscular": 4,
    "dolor_articular": 3,
    "niebla_mental": 4,
    "problemas_sueno": 3,
    "caida_cabello": 4,
    "piel_seca": 3,
    "unas_quebradizas": 4,
    "enfermedad_frecuente": 2,
    "calambres": 2,
    "irritabilidad": 3,
    "meta_energia": 1,
    "meta_inmunidad": 0,
    "meta_belleza": 1,
    "meta_rendimiento": 0,
    "meta_salud_osea": 0,
    "meta_cognitivo": 1,
}
resultado = predecir_condicion(usuario_ejemplo)
print(f"Usuario (vegana, baja sol, fatiga alta, caída cabello):")
print(f"  → Condiciones detectadas: {resultado}")
print("\nListo. Próximo paso: Modelo 2 (GNN) recibe estas condiciones.")
