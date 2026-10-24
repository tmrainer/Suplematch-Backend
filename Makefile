# Atajos de desarrollo. Requiere podman o docker (variable CONTAINER_RUNTIME) y Python 3.12 en contenedor.
CONTAINER_RUNTIME ?= podman
PY_IMAGE ?= docker.io/library/python:3.12-slim
PG_IMAGE ?= docker.io/library/postgres:16
POD ?= suple-dev

.PHONY: help test-unit db-up db-down migrate seed import-catalog test-integration rebuild-catalog maintenance-dry-run

help:
	@grep -E '^[a-z-]+:' Makefile | cut -d: -f1 | tr '\n' ' '; echo

# Tests unitarios en un contenedor limpio (sin Postgres). Sin torch se omiten los tests del Modelo 2.
test-unit:
	$(CONTAINER_RUNTIME) run --rm --security-opt label=disable -v "$(PWD)":/app -w /app $(PY_IMAGE) \
	  sh -c "pip install -q -r requirements-ci.txt && python -m pytest tests/unit -q -p no:cacheprovider"

# Postgres + contenedor de app compartiendo red (localhost) para migraciones e integracion.
db-up:
	$(CONTAINER_RUNTIME) pod create --name $(POD) >/dev/null || true
	$(CONTAINER_RUNTIME) run -d --pod $(POD) --name $(POD)-pg -e POSTGRES_DB=suplematch -e POSTGRES_USER=suplematch -e POSTGRES_PASSWORD=suplematch $(PG_IMAGE) >/dev/null || true
	$(CONTAINER_RUNTIME) run -d --pod $(POD) --name $(POD)-app --security-opt label=disable -v "$(PWD)":/app -w /app \
	  -e DATABASE_URL=postgresql+psycopg://suplematch:suplematch@localhost:5432/suplematch -e ENVIRONMENT=development $(PY_IMAGE) sleep infinity >/dev/null || true
	$(CONTAINER_RUNTIME) exec $(POD)-app pip install -q -r requirements-ci.txt
	@for i in $$(seq 1 30); do $(CONTAINER_RUNTIME) exec $(POD)-pg pg_isready -U suplematch -d suplematch >/dev/null 2>&1 && break; sleep 2; done

db-down:
	$(CONTAINER_RUNTIME) pod rm -f $(POD) >/dev/null 2>&1 || true

migrate:
	$(CONTAINER_RUNTIME) exec $(POD)-app alembic upgrade head

seed:
	$(CONTAINER_RUNTIME) exec $(POD)-app python scripts/ops/sembrar_base.py

import-catalog:
	$(CONTAINER_RUNTIME) exec $(POD)-app python scripts/catalog/importar_catalogo_postgres.py --catalog data/catalog/approved_catalog.csv

test-integration: migrate seed import-catalog
	$(CONTAINER_RUNTIME) exec $(POD)-app python -m pytest tests/integration -q -p no:cacheprovider

rebuild-catalog:
	bash scripts/catalog/reconstruir_catalogo.sh

maintenance-dry-run:
	bash scripts/ops/mantenimiento_diario.sh --dry-run
