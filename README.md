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
- PyTorch y PyTorch Geometric para el modelo de grafo (GraphSAGE).
- Tesseract OCR, pytesseract, pypdf, pdf2image y Pillow para extraccion de datos desde examenes de laboratorio.
- Docker y Docker Compose para ejecucion reproducible en desarrollo y staging local.

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
