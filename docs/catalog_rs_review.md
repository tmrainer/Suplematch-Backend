# Cola de revisión humana de registros sanitarios (RS)

Plan de fiabilidad, Fase 1: *"Cola de revisión humana en Postgres para el 100% de RS
inferidos + 5% de muestra aleatoria"*.

## Por qué existe

El catálogo aprobado (`data/catalog/approved_catalog.csv`) trae la columna
`registro_sanitario_source`. Cuando vale `digemid_name_match` o `digemid_name_inference`
el RS **no se leyó de la página de la farmacia**: se dedujo comparando el nombre
comercial con el padrón DIGEMID. Un match de nombre puede equivocarse de producto
(otra dosis, otra forma farmacéutica, otro titular), y de ese RS cuelgan la composición,
los flags de seguridad y la trazabilidad que ve el usuario. Por eso todo RS inferido
pasa por una persona antes de considerarse confiable, y además se revisa una muestra
aleatoria del resto como control de calidad del RS leído.

Hasta ahora el único estado de revisión vivía en un JSON en disco
(`servicio_candidatos_catalogo.py`); esta cola vive en Postgres y queda auditada en
`admin_actions`.

## Modelo

Tabla `catalog_rs_reviews` (`CatalogRsReview` en `app/db/models.py`, migración
`alembic/versions/20261022_0014_catalog_rs_review.py`, idempotente).

| Campo | Significado |
|---|---|
| `pharmacy`, `sku`, `url`, `commercial_name` | Producto comercial tal como lo vende la farmacia. `sku` cae a la URL cuando la farmacia no expone SKU (misma regla que el importador). |
| `registro_sanitario_key` | RS normalizado (`DE-1230` → `DE1230`), misma regla que `construir_catalogo_aprobado.normalize_rs`. |
| `digemid_producto`, `digemid_composicion` | Lo que DIGEMID registra bajo ese RS: el revisor compara esto contra `commercial_name`. |
| `registro_sanitario_source` | Fuente original del RS. |
| `match_reason` | Texto libre con el contexto del match: fuente, forma farmacéutica DIGEMID, marca, fabricante, nivel y motivos de confianza comercial. |
| `sample_reason` | `inferred` (100% de los RS inferidos) o `random_sample` (muestra aleatoria). |
| `status` | `pending` → `approved` / `rejected` / `needs_info`. Se puede volver a `pending`. |
| `reviewer_user_id`, `reviewer_note`, `decided_at` | Quién decidió, por qué y cuándo. |

Única por `(pharmacy, sku, registro_sanitario_key)`: una decisión aplica a **ese RS en ese
producto**. Si el catálogo corrige el RS del producto aparece una fila nueva y la antigua
deja de afectarlo.

## Selección (`select_review_items`)

`app/domains/admin/servicio_revision_rs.py::select_review_items(rows, sample_ratio=0.05, seed=...)`
es una función pura sobre las filas del CSV:

1. Agrupa filas por producto (`pharmacy` + `sku`/`url`); una entrada por producto aunque
   tenga varias filas (una por componente).
2. Si **alguna** fila del producto tiene `registro_sanitario_source` ∈
   {`digemid_name_match`, `digemid_name_inference`} → `sample_reason="inferred"`.
3. Del resto de productos con RS, entra en `random_sample` el que cumple
   `sha256(seed|pharmacy|sku) / 2^64 < sample_ratio`. Se usa hash en vez de
   `random.sample` para que la muestra sea **estable**: añadir o quitar productos del
   catálogo no saca de la muestra a uno ya muestreado (la cola persiste decisiones).
   Cambiar `seed` cambia la muestra.
4. Productos sin RS se omiten (no hay RS que revisar; los trata el flujo de candidatos).

## Poblar la cola

- Al importar: `python scripts/catalog/importar_catalogo_postgres.py` pobla la cola al
  final de la importación. Flags: `--no-rs-review`, `--rs-review-sample-ratio 0.05`.
  La salida añade `rs_review_inserted`, `rs_review_updated`, `rs_review_skipped_decided`.
- Sin reimportar: `python scripts/ops/poblar_cola_revision_rs.py [--dry-run] [--json]
  [--sample-ratio 0.05] [--seed ...]`.

Reglas del upsert (`CatalogRsReviewRepository.upsert_items`):

- No existe la clave → se inserta en `pending`.
- Existe en `pending` → se refrescan los campos descriptivos (nombre, URL, DIGEMID, fuente,
  `match_reason`, `sample_reason`).
- Existe con `status != pending` → **no se toca**. Una decisión humana nunca se pisa por
  una recarga.

## Revisar (endpoints admin, `require_admin`)

- `GET /api/v1/admin/catalog/rs-review?status=pending&sample_reason=inferred&pharmacy=&limit=50&offset=0`
  Lista paginada (`items`, `total`). `status=all` lista todos los estados. Orden:
  `inferred` antes que `random_sample`, luego farmacia y nombre. Cada ítem trae
  `commercial_name` vs `digemid_producto` + `digemid_composicion` + `match_reason`.
- `PATCH /api/v1/admin/catalog/rs-review/{id}` con `{"status": "approved" | "rejected" |
  "needs_info" | "pending", "reviewer_note": "..."}`. Registra `AdminAction`
  (`action_type="catalog_rs_review_decision"`, `entity_type="catalog_rs_review"`) con
  before/after.
- `GET /api/v1/admin/catalog/rs-review/summary`: `total`, `pending`, `decided`, `progress`,
  `by_status`, `by_sample_reason`, `by_sample_reason_and_status`.

### Criterios de aprobación

Aprobar (`approved`) solo si **todo** se cumple:

1. **Nombre coherente.** El nombre comercial describe el mismo producto que
   `digemid_producto`: mismo principio activo y misma dosis (por ejemplo "Vitamina E 400
   UI Cápsula Blanda" ↔ "VITAMINA E 400 UI"). Una dosis distinta (400 vs 1000 UI) o un
   principio distinto (D3 vs D2, citrato vs carbonato de calcio) es rechazo.
2. **Composición coherente.** `digemid_composicion` cuadra con lo que el envase/la ficha
   de la farmacia declara (ingredientes y cantidades). Si la farmacia declara varios
   componentes y DIGEMID registra uno solo (o al revés), no es el mismo producto.
3. **Misma forma farmacéutica.** Cápsula blanda vs tableta vs jarabe vs gomitas no son el
   mismo RS, aunque el nombre coincida. Usar `forma_digemid=` en `match_reason`.
4. **Marca / titular.** La marca de la farmacia (`marca=` en `match_reason`) debe ser
   compatible con el fabricante o titular DIGEMID (`fabricante_digemid=`). Una marca
   distinta con el mismo nombre genérico ("Vitamina C 1000 mg") es el caso típico de
   falso positivo: rechazar o pedir información.

Usar `needs_info` cuando falte evidencia (p. ej. la ficha de la farmacia no muestra
composición ni marca) y anotar qué falta en `reviewer_note`. Usar `rejected` cuando
alguno de los cuatro criterios falla con claridad y escribir el motivo.

### Qué pasa con cada estado al servir productos (modo Postgres)

`CatalogRepository.products_for_component` y `search_products` consultan la cola por
`(pharmacy, sku, RS actual del producto)`:

- `rejected` → el producto **no se sirve** (ni en recomendaciones ni en `/prices`). Es el
  mismo efecto que un `CatalogOverride.blocked`, pero reversible desde la cola: volver a
  `pending`/`approved` lo reactiva. El producto sigue existiendo en `commercial_products`.
- `pending`, `needs_info`, `approved` → se sirve. El dict del producto expone
  `rs_review_status` con ese valor para que el cliente pueda mostrar la trazabilidad.
- Sin fila para el RS actual → `rs_review_status="not_required"`.

En modo CSV (sin BD) no hay decisiones que aplicar: todos los productos salen con
`rs_review_status="not_required"`. Decisión: no se replica el estado en el CSV porque la
cola es la fuente de verdad y el modo CSV es solo para desarrollo/validación offline.

> Pendiente fuera del alcance de esta tarea: `RecommendedProduct`
> (`app/domains/recommendations/esquemas.py`) ignora campos extra, así que
> `rs_review_status` llega al servicio pero no al JSON de `/recommend` hasta añadir
> `rs_review_status: str = "not_required"` a ese esquema.

### Después de rechazar

Un rechazo significa "este RS no corresponde a este producto". Siguiente paso operativo:
corregir la inferencia aguas arriba (`scripts/catalog/reinferir_rs.py` / matcher de
nombres) o conseguir el RS real (etiqueta, OCR de imagen, consulta DIGEMID). Cuando el
catálogo traiga otro RS para el producto, el importador crea una fila nueva en `pending`
y el producto vuelve a servirse (con `rs_review_status="pending"`) hasta la nueva decisión.

## Tests

- `tests/unit/test_catalog_rs_review.py`: selección pura, determinismo y estabilidad de la
  muestra, contexto de `match_reason`, cobertura del 100% de inferidos sobre el CSV real.
- `tests/integration/test_catalog_rs_review.py` (requiere Postgres): upsert sin pisar
  decisiones, ocultamiento de rechazados en `products_for_component`/`search_products`,
  independencia entre RS antiguo y nuevo, resumen.
