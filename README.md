# SupleMatch Backend

## 1. Tecnologias utilizadas

Tecnologias principales:

- Python 3.12 como lenguaje principal.
- FastAPI para exponer endpoints HTTP.
- Uvicorn para ejecucion local y despliegue en contenedor.
- PostgreSQL como base de datos principal.
- SQLAlchemy 2 para modelos, consultas y persistencia.
- Pydantic y pydantic-settings para validacion de datos y configuracion por entorno.
- passlib, bcrypt y python-jose para autenticacion, hash de contrasenas y manejo de JWT.
- scikit-learn 1.5, numpy, scipy, pandas, joblib y pyarrow para procesamiento de datos, features, entrenamiento e inferencia del modelo tabular.
  El Modelo 1 (`condition_mvp`) se entrena hoy con datos sintéticos derivados de `condition_rules.csv`;
  sus salidas deben leerse como índice de riesgo basado en reglas, no como probabilidad clínica.
  Ver `docs/plan_fiabilidad.md`.
- PyTorch (runtime, solo para deserializar embeddings) y PyTorch Geometric (solo entrenamiento) para el
  grafo de componentes del Modelo 2. El GNN aporta candidatos complementarios; el ranking principal es
  un motor de reglas ponderadas sobre `data/knowledge/`.
- Tesseract OCR, pytesseract, pypdf, pdf2image y Pillow para extraccion de datos desde examenes de laboratorio.
- Docker y Docker Compose para ejecucion reproducible en desarrollo y staging local.

## 1.1 Artefactos de modelo

Los `.pkl` de `models/runtime/` no se versionan en git. Sin ellos el endpoint `/recommend`
responde error y `/health/ready` reporta `models=false`. Para generarlos:

```bash
python3 scripts/training/entrenar_modelo_condiciones.py --rows 10000 --seed 42   # condition_mvp_model.pkl
python3 scripts/training/modelo2_train.py                                          # modelo2_artifacts.pkl (requiere torch-geometric y CSVs en SUPPLEMENT_MODEL_DATA_DIR)
python3 scripts/training/entrenar_condiciones_nhanes.py                            # condition_lab_model.pkl (descarga NHANES)
```

El sha256 que corresponde a cada commit está en `data/insumos_manifest.json`. Al arrancar, la API compara los
`.pkl` con ese hash y el contrato de features de `condition_lab_model.pkl` con el del código: en `staging`/`production`
un modelo distinto deja `/health/ready` en `degraded` (`checks.model_artifacts.versions.problems`); en desarrollo solo
avisa en el log. Para desplegar los modelos de un commit sin reentrenar:

```bash
python3 scripts/ops/modelos_release.py descargar --tag models-AAAA-MM-DD   # baja del release, verifica sha256 y reemplaza
python3 scripts/ops/modelos_release.py verificar                          # compara lo que hay en disco
```

Tras reentrenar a propósito: `python3 scripts/ops/verificar_insumos.py --update`, comitear el manifiesto y publicar
(`modelos_release.py publicar --tag ...`; el repositorio es público, el release también).

## 2. Despliegue

### Opcion A: ejecucion local con Python

Desde la raiz del repositorio backend:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Levantar PostgreSQL local desde la raiz del proyecto general:

```bash
docker compose -f infra/docker-compose.staging.yml up -d postgres
```

Aplicar migraciones:

```bash
source .venv/bin/activate
alembic upgrade head
```

Levantar la API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Validar estado:

```bash
curl http://localhost:8000/api/v1/health
```

### Opcion B: ejecucion con Docker Compose

Desde la raiz del proyecto general:

```bash
cp -n .env.staging.example .env.staging
docker compose -p proyecto --env-file .env.staging -f infra/docker-compose.staging.yml up -d --build backend
```

Validar contenedor y healthcheck:

```bash
docker compose -p proyecto --env-file .env.staging -f infra/docker-compose.staging.yml ps
docker compose -p proyecto --env-file .env.staging -f infra/docker-compose.staging.yml exec -T backend curl -fsS http://localhost:8000/api/v1/health
```
