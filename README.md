# SupleMatch Backend

API FastAPI para recomendar suplementos personalizados según el perfil del usuario. Combina un clasificador de condiciones (Random Forest) con un recomendador basado en grafo GNN, enriquecido con productos reales validados por DIGEMID.

## Stack

- Python 3.12 · FastAPI · SQLAlchemy · Alembic · PostgreSQL
- Scikit-learn 1.5.0 (Modelo 1 — clasificador multilabel)
- GNN sobre embeddings de grafo (Modelo 2 — recomendador)
- SHAP para explicabilidad del Modelo 1

## Setup local

### 1. Crear entorno virtual

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### 2. Instalar dependencias

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> **Importante:** `scikit-learn==1.5.0` está fijado porque los archivos `.pkl` deben cargarse con la misma versión con que fueron entrenados. No actualizar sklearn sin reentrenar los modelos.

Verificar versiones clave:

```bash
python -c "import sklearn; print(sklearn.__version__)"   # debe ser 1.5.0
python -c "import shap; print(shap.__version__)"         # >= 0.45.0
```

### 3. Variables de entorno

```bash
cp .env.example .env
```

Variables relevantes:

```env
MODEL_DIR=app/ml/runtime
FEEDBACK_DB_PATH=app/ml/runtime/feedback.sqlite3
DIGEMID_CSV_PATH=data/raw/csv/digemid_limpio.csv
PRODUCT_COMPONENTS_CSV_PATH=data/training/modelo2/product_components.csv
APPROVED_CATALOG_PATH=data/catalog/approved_catalog.csv
DATABASE_URL=postgresql+psycopg://suplematch:suplematch@localhost:5432/suplematch
```

### 4. Modelos

Los modelos entrenados están versionados en el repositorio:

```
app/ml/runtime/
├── modelo1_pipeline.pkl       # Random Forest multilabel (clasificador de condiciones)
└── modelo2_artifacts.pkl      # Embeddings GNN + grafo de relaciones
```

No se requiere reentrenamiento para correr la API.

### 5. Levantar la API

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/api/v1/health
```

Estado de modelos cargados:

```bash
curl http://localhost:8000/api/v1/debug/model-status
```

---

## Pipeline de recomendación

```
Encuesta del usuario
      │
      ▼
Modelo 1 (Random Forest multilabel)
  → predict_proba → probabilidades reales por condición
  → SHAP TreeExplainer → drivers personalizados por usuario
      │
      ▼
Condiciones detectadas (ej: FATIGA, DEFICIT_VIT_D)
      │
      ▼
Modelo 2 (GNN — embeddings de grafo)
  → semillas directas por condición
  → candidatos por similitud coseno en el espacio de embeddings
  → filtro de sinergias y alertas de interacción
      │
      ▼
Re-ranking por feedback histórico
      │
      ▼
Enriquecimiento con productos DIGEMID
  → catálogo aprobado con RS validado y precios scrapeados
```

---

## Explicabilidad (Explainability)

El endpoint `/recommend` retorna el campo `explainability` con el detalle de **por qué** el modelo detectó cada condición para ese usuario específico.

**Cómo funciona:**

1. Se usa `predict_proba` del pipeline sklearn para obtener probabilidades reales (no hardcodeadas) por condición.
2. Para cada condición con probabilidad ≥ 45%, se corre `shap.TreeExplainer` sobre el sub-estimador Random Forest correspondiente del `MultiOutputClassifier`.
3. Se extraen los top-3 features por valor absoluto de SHAP, mapeando nombres transformados (post-`ColumnTransformer`) de vuelta a las variables originales de la encuesta.
4. Si `shap` no está instalado, el sistema cae automáticamente a un mapeo basado en reglas de dominio (mismo resultado visual, menor precisión).

**Ejemplo de respuesta:**

```json
"explainability": [
  {
    "condition": "FATIGA",
    "probability": 0.83,
    "drivers": [
      { "label": "Fatiga frecuente",   "value": 4, "value_label": "A menudo",  "impact": "alto",  "shap_value": 0.31 },
      { "label": "Problemas de sueño", "value": 5, "value_label": "Severo",    "impact": "alto",  "shap_value": 0.22 },
      { "label": "Nivel de estrés",    "value": 3, "value_label": "Moderado",  "impact": "medio", "shap_value": 0.09 }
    ]
  }
]
```

El campo `shap_value` indica la contribución real de esa variable al score del modelo para ese usuario. Es distinto para cada persona.

---

## Endpoints principales

### POST `/api/v1/recommend`

```bash
curl -X POST http://localhost:8000/api/v1/recommend \
  -H "Content-Type: application/json" \
  -d '{
    "edad_rango": "31_50",
    "horas_sueno": "5_7h",
    "frecuencia_ejercicio": "1_2_semana",
    "dieta": "regular",
    "fatiga": "a_menudo",
    "exposicion_solar": "menos_15min",
    "frecuencia_enfermedad": "1_2_anio",
    "estres": "moderado",
    "alcohol": "ocasional"
  }'
```

Campos de la respuesta:

| Campo | Descripción |
|---|---|
| `conditions` | Condiciones detectadas (códigos) |
| `conditions_display` | Condiciones con nombre, nivel y probabilidad real |
| `explainability` | Drivers SHAP por condición — qué variables influyeron y cuánto |
| `recommendations` | Suplementos con razón, dosis y productos reales |
| `packs_ranked` | Packs ordenados por score GNN + feedback histórico |
| `sinergias` | Pares de componentes con sinergia funcional (del grafo) |
| `alertas` | Interacciones riesgosas detectadas |
| `disclaimer` | Aviso médico |

### POST `/api/v1/feedback`

```bash
curl -X POST http://localhost:8000/api/v1/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "recommendation_id": "rec_abc123",
    "pack_id": "pack_1",
    "component_ids": ["COMP_ABC", "COMP_XYZ"],
    "rating": 5,
    "conditions": ["FATIGA"],
    "comment": "Me sirvió"
  }'
```

El feedback alimenta el re-ranking de packs en recomendaciones futuras.

---

## Datos

### Estructura

```
data/
├── raw/
│   └── csv/
│       ├── digemid_limpio.csv              # Registro DIGEMID (productos regulados)
│       ├── supplements_exhaustive_clean.csv # Scraping de farmacias peruanas
│       └── scrape_parts/                   # CSVs por farmacia
├── training/
│   └── modelo2/
│       ├── Component_Master_Clean.csv      # Catálogo de componentes con señales
│       ├── Component_Relationship_Edges_Clean.csv  # Relaciones del grafo
│       └── product_components.csv          # Mapeo ítem DIGEMID → componente
└── catalog/
    └── approved_catalog.csv               # Catálogo aprobado (generado)
```

### Reconstruir catálogo aprobado

```bash
python scripts/build_approved_catalog.py \
  --scraped data/raw/csv/supplements_exhaustive_clean.csv \
  --digemid data/raw/csv/digemid_limpio.csv \
  --components data/training/modelo2/product_components.csv \
  --out data/catalog/approved_catalog.csv
```

---

## Tests

```bash
pytest tests/integration -q
```

Validación de calidad del modelo:

```bash
python scripts/validate_recommendation_quality.py
```

---

## Docker

```bash
docker compose up --build
```

---

## Notas de versión

- `scikit-learn==1.5.0` — no cambiar sin reentrenar los `.pkl`
- `shap>=0.45.0` — requerido para explicabilidad SHAP; si no está instalado el sistema usa fallback automático
- `torch` — requerido por el Modelo 2 (GNN embeddings)
