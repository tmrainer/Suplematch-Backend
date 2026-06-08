# PostgreSQL relational phase plan

Este backend debe usar PostgreSQL para la base relacional: usuarios, catálogo comercial, recomendaciones, feedback, reviews, auditoría y administración.

## Fase 1: esquema relacional y catálogo

Variables:

```bash
export DATABASE_URL="postgresql+psycopg://suplematch:suplematch@localhost:5432/suplematch"
```

Instalar dependencias:

```bash
python3 -m pip install -r requirements.txt
```

Crear tablas y roles base:

```bash
alembic upgrade head
python3 scripts/init_postgres_schema.py
```

Importar catálogo aprobado actual:

```bash
python3 scripts/import_catalog_to_postgres.py \
  --catalog data/catalog/approved_catalog.csv
```

Validar persistencia y efecto en re-ranking:

```bash
python3 scripts/validate_postgres_persistence.py
```

Si se usa Docker local:

```bash
docker compose up -d postgres
```

En esta máquina la validación con Docker requiere que el usuario tenga permisos sobre `/var/run/docker.sock`.

Tablas creadas en esta fase:

```txt
users
roles
user_roles
user_profiles
pharmacies
components
commercial_products
commercial_product_components
staging_scraped_products
catalog_import_runs
catalog_import_errors
recommendation_sessions
recommendation_items
recommended_packs
recommended_pack_items
recommendation_feedback
supplement_reviews
pack_reviews
catalog_overrides
admin_actions
```

## Fase 2: persistir recomendaciones

Implementado: al responder `/api/v1/recommend`, se guarda en PostgreSQL:

```txt
recommendation_sessions
recommendation_items
recommended_packs
recommended_pack_items
```

La respuesta de la API puede seguir igual, pero la trazabilidad quedará en PostgreSQL.

## Fase 3: feedback y reviews

Implementado para feedback de recomendaciones: `/api/v1/feedback` guarda en PostgreSQL:

```txt
recommendation_feedback
```

Pendiente para reseñas públicas/moderables:

```txt
pack_reviews
supplement_reviews
```

SQLite debe quedar solo como mecanismo legacy/migración, no como fuente relacional principal.

## Fase 4: usuarios y roles

Implementado base:

```txt
registro/login
JWT Bearer
roles user/moderator/admin
historial de recomendaciones por usuario
```

Endpoints:

```txt
POST /api/v1/auth/register
POST /api/v1/auth/login
GET /api/v1/auth/me
GET /api/v1/users/me
PATCH /api/v1/users/me
PUT /api/v1/users/me/profile
GET /api/v1/history/me
```

## Fase 5: admin comercial

Implementado base de endpoints admin para:

```txt
activar/bloquear productos
marcar preferred
moderar reviews
ver métricas
auditar acciones
```

Endpoints:

```txt
GET /api/v1/admin/products
PATCH /api/v1/admin/products/{product_id}
GET /api/v1/admin/import-runs
GET /api/v1/admin/reviews/supplements
PATCH /api/v1/admin/reviews/supplements/{review_id}
GET /api/v1/admin/metrics/feedback
```

## Fase 6: métricas del modelo

Implementado en primera version para recomendaciones:

```txt
score_feedback
score_reviews
score_exposure
repetition_penalty
pharmacy_diversity_score
```

El modelo no necesita reentrenarse al inicio; primero usa estos datos para re-ranking. `repetition_penalty` se expresa como `score_exposure`, y `pharmacy_diversity_score` se aplica en seleccion de productos por pack.
