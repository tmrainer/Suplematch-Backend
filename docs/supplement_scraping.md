# SupleMatch supplement scraping

Este flujo genera el CSV bruto de productos comerciales y luego reconstruye el catálogo aprobado que usa el backend.

## Archivo bruto esperado

El scraper escribe:

```txt
data/raw/pharmacies/supplements_exhaustive_clean.csv
```

Columnas compatibles con `scripts/catalog/construir_catalogo_aprobado.py`:

```txt
pharmacy
commercial_name
formal_name
registro_sanitario
price
currency
availability
url
sku
brand
source_strategy
```

También agrega columnas operativas:

```txt
scraped_at
stock
component_text
registro_sanitario_source
component_traceable
component_ids_detected
component_names_detected
image_url
image_source
image_local_path
image_downloaded_at
rejection_reason
```

Por defecto deja productos con alguna trazabilidad de componente:

- `true_rs_component`: registro sanitario validado contra `digemid_limpio.csv` y componente confiable en `product_components.csv`.
- `true_component_name_with_rs_unmapped`: tiene RS local, pero no está mapeado en `product_components.csv`; el componente se detectó por nombre usando los CSV del proyecto.
- `true_component_name_no_rs`: no tiene RS publicado/inferido, pero el componente se detectó por nombre usando `product_components.csv` y `data/training/supplement_model/Component_Master_Clean.csv`.

El catálogo que usa el backend sigue siendo más estricto: `scripts/catalog/construir_catalogo_aprobado.py` solo incluye productos con RS validado y componente mapeado en `product_components.csv`.

### Corrección creatina

Creatina tiene un componente curado propio:

```txt
COMP_7B47CDB437E8 -> Creatina
```

Reglas aplicadas:

- `CREATINA`, `CREATINA MONOHIDRATO`, `CREATINE MONOHYDRATE`,
  `CLORHIDRATO DE CREATINA`, sales y variantes comerciales de creatina se
  agrupan bajo ese componente.
- No deben mapearse a `COMP_67B16EEFC42F`, que corresponde a vitamina C.
- El scraper tiene alias manuales de alta confianza para evitar que el fuzzy
  matching confunda creatina con ácido ascórbico.
- El parser de composicion reconoce números con miles y decimales mixtos, por
  ejemplo `3,250.000000 mg`, para no dejar nombres como
  `CREATINA MONOHIDRATO 3`.

Los descartes se guardan en:

```txt
data/reports/scraping/supplements_rejected.csv
```

## Fuentes

El script incluye adaptadores para:

```txt
inkafarma
mifarma
boticasperu
farmaciauniversal
hogarysalud
boticasysalud
```

Uso principal:

```bash
pip install -r requirements.txt
python3 scripts/scraping/scraper_suplementos.py \
  --limit-per-pharmacy 2000 \
  --infer-registro \
  --fetch-detail-pages \
  --out data/raw/pharmacies/supplements_exhaustive_clean.csv \
  --rejects-out data/reports/scraping/supplements_rejected.csv
```

Recuperación de registro sanitario:

- `registro_sanitario_source=card`: el RS apareció en la tarjeta/listado o en la respuesta principal.
- `registro_sanitario_source=detail`: el RS apareció en la página/API de detalle.
- `registro_sanitario_source=image_ocr`: el RS se recuperó desde imagen de etiqueta usando Tesseract.
- `registro_sanitario_source=digemid_name_match`: no había RS visible, pero se encontró un match alto por nombre contra DIGEMID.

Flags útiles:

```bash
--fetch-detail-pages     # recomendado para staging/semanal
--ocr-product-images     # más lento; usar para corrida dirigida o revisión
--infer-registro         # fallback por nombre contra DIGEMID con umbral alto
--download-product-images # descarga la imagen principal detectada
```

Imágenes de producto:

- `image_url`: URL pública de la primera imagen válida detectada en card o detalle.
- `image_source`: origen de la imagen, normalmente `card` o `detail`.
- `image_local_path`: ruta relativa dentro del backend cuando se usa descarga local.
- `image_downloaded_at`: fecha UTC de descarga.

La descarga local guarda archivos en:

```txt
data/raw/pharmacies/product_images/
```

Ejemplo con imágenes:

```bash
python3 scripts/scraping/scraper_suplementos.py \
  --pharmacy mifarma \
  --limit-per-pharmacy 50 \
  --fetch-detail-pages \
  --download-product-images \
  --allow-unverified
```

Para probar una farmacia con pocos registros:

```bash
python3 scripts/scraping/scraper_suplementos.py \
  --pharmacy hogarysalud \
  --limit-per-pharmacy 20 \
  --allow-unverified
```

## Reconstruir catálogo aprobado

Después de generar el CSV bruto:

```bash
python3 scripts/catalog/construir_catalogo_aprobado.py \
  --scraped data/raw/pharmacies/supplements_exhaustive_clean.csv \
  --digemid digemid_limpio.csv \
  --components product_components.csv \
  --out data/catalog/approved_catalog.csv
```

## Automatización semanal

Ejecución manual del flujo completo:

```bash
bash scripts/scraping/actualizar_suplementos_semanal.sh
```

El flujo semanal ahora ejecuta:

1. Scraping de farmacias.
2. Reconstrucción de `data/catalog/approved_catalog.csv`.
3. Validación de calidad con `scripts/validation/validar_pipeline_catalogo.py`.
4. Snapshots fechados en `data/reports/scraping/`.
5. Importación opcional a PostgreSQL si `IMPORT_TO_POSTGRES=1`.

Además usa un lock por tipo de corrida en `data/reports/scraping/<RUN_LABEL>.lock`, para evitar dos ejecuciones simultáneas del mismo flujo.

Cron sugerido para domingos 03:30:

```cron
30 3 * * 0 cd /home/leo/DPD/Proyecto/Suplematch-Backend && /usr/bin/env bash scripts/scraping/actualizar_suplementos_semanal.sh
```

Variables opcionales:

```bash
LIMIT_PER_PHARMACY=1000
SCRAPER_DELAY=0.25
SCRAPER_PHARMACIES=
SCRAPED_CSV=data/raw/pharmacies/supplements_exhaustive_clean.csv
APPROVED_CSV=data/catalog/approved_catalog.csv
REJECTED_CSV=data/reports/scraping/supplements_rejected.csv
MIN_RAW_ROWS=500
MIN_APPROVED_ROWS=250
MIN_PHARMACIES=3
MAX_INVALID_PRICE_RATIO=0.01
MAX_RAW_AGE_HOURS=48
IMPORT_TO_POSTGRES=0
VALIDATE_ONLY=0
SCRAPER_FETCH_DETAIL_PAGES=1
SCRAPER_OCR_PRODUCT_IMAGES=0
SCRAPER_DOWNLOAD_PRODUCT_IMAGES=0
SCRAPER_IMAGE_DIR=data/raw/pharmacies/product_images
```

Ejemplo:

```bash
LIMIT_PER_PHARMACY=1500 SCRAPER_DELAY=0.5 bash scripts/scraping/actualizar_suplementos_semanal.sh
```

Para ejecutar solo algunas fuentes, usar los slugs aceptados por el scraper:

```bash
SCRAPER_PHARMACIES="inkafarma,mifarma,hogarysalud" \
  bash scripts/scraping/actualizar_suplementos_semanal.sh
```

Para exigir farmacias específicas en la corrida:

```bash
REQUIRE_PHARMACIES="Inkafarma,Mifarma,Farmacia Universal" \
  bash scripts/scraping/actualizar_suplementos_semanal.sh
```

Para auditar el snapshot actual sin ejecutar scraping de red:

```bash
VALIDATE_ONLY=1 bash scripts/scraping/actualizar_suplementos_semanal.sh
```

Esto usa los mismos umbrales de validación que la corrida semanal. Para una
auditoría histórica o local con datos antiguos puede ampliarse el umbral de
frescura:

```bash
VALIDATE_ONLY=1 MAX_RAW_AGE_HOURS=999999 \
  bash scripts/scraping/actualizar_suplementos_semanal.sh
```

Para probar una farmacia real sin pisar el catálogo principal, enviar la salida
a `data/reports/scraping/`:

```bash
RUN_LABEL=real_smoke \
SCRAPER_PHARMACIES=inkafarma \
LIMIT_PER_PHARMACY=20 \
SCRAPER_DELAY=0.05 \
MIN_RAW_ROWS=1 \
MIN_APPROVED_ROWS=1 \
MIN_PHARMACIES=1 \
MAX_RAW_AGE_HOURS=48 \
SCRAPED_CSV=data/reports/scraping/real_smoke_scraped.csv \
APPROVED_CSV=data/reports/scraping/real_smoke_approved.csv \
REJECTED_CSV=data/reports/scraping/real_smoke_rejected.csv \
bash scripts/scraping/run_weekly_supplement_update.sh
```

Ese smoke valida extracción real, reconstrucción de catálogo, componentes
detectados y frescura, pero no reemplaza el CSV aprobado de producción.

## Cobertura comercial por componente

Para revisar si los componentes que recomienda el Modelo 2 tienen suficientes
productos comerciales distintos para rotación:

```bash
python3 scripts/catalog/auditar_cobertura_componentes.py
```

El reporte se escribe en:

```txt
data/reports/catalog/component_commercial_coverage.csv
data/reports/catalog/component_commercial_coverage_summary.json
```

Estados:

- `ready`: 4 o más productos disponibles y de formato compatible.
- `minimum`: cerca del objetivo, pero con poca holgura.
- `weak`: 1 o 2 productos.
- `missing`: sin productos comerciales aprobados.

El auditor cruza `condition_component_links.csv`, el master de componentes y
`data/catalog/approved_catalog.csv`. También agrupa equivalencias técnicas
cuando aplica, por ejemplo `Cromo` con formas detectadas como `Chromium`.

## Scraping dirigido para rotación

Cuando un componente aparece como `missing` o `weak`, se puede ejecutar una
búsqueda dirigida con los alias del componente:

```bash
python3 scripts/scraping/buscar_productos_rotacion_componentes.py \
  --max-components 8 \
  --limit-per-pharmacy 50 \
  --pharmacy inkafarma \
  --pharmacy mifarma \
  --pharmacy farmaciauniversal
```

El script usa el reporte de cobertura, genera términos como `Ashwagandha`,
`L-Theanine` o `Valerian`, llama al scraper principal y resume candidatos por
componente. También acepta términos repetidos en el scraper base mediante
`--term`.

Para recuperar más RS durante la búsqueda dirigida:

```bash
python3 scripts/scraping/buscar_productos_rotacion_componentes.py \
  --fetch-detail-pages \
  --ocr-product-images \
  --max-components 5 \
  --limit-per-pharmacy 30
```

Salidas:

```txt
data/reports/scraping/rotation_candidates_raw.csv
data/reports/scraping/rotation_candidates_rejected.csv
data/reports/scraping/rotation_candidates_by_component.csv
data/reports/scraping/rotation_candidate_relations.csv
data/reports/scraping/rotation_candidates_summary.json
```

Estos archivos son candidatos para revisión humana/importación posterior. No
actualizan `approved_catalog.csv` ni PostgreSQL automáticamente.
`rotation_candidate_relations.csv` es el archivo más útil para revisión: deja
una fila por relación `component_id -> producto comercial`, con farmacia,
precio, URL, trazabilidad detectada y base del match.

Si un producto dirigido aparece sin RS, queda como candidato para revisión y no
se fuerza al catálogo aprobado. Para entrada automática debe tener RS DIGEMID y
componente trazable. El catálogo enriquecido agrega:

```txt
commercial_confidence_score
commercial_confidence_level
commercial_confidence_reasons
```

## Revisión admin de candidatos

Los candidatos de rotación se revisan desde el panel admin de catálogo y desde
la API:

```txt
GET   /api/v1/admin/catalog/candidates
PATCH /api/v1/admin/catalog/candidates/{candidate_id}
POST  /api/v1/admin/catalog/candidates/{candidate_id}/promote
```

Estados usados por el flujo:

- `approved_verified`: tiene RS y componente trazable; se puede promover.
- `approved_inferred`: tiene RS, pero la trazabilidad no es fuerte.
- `candidate_needs_rs`: falta RS; no se puede promover.
- `candidate_name_match`: requiere revisar el match por nombre contra DIGEMID.
- `rejected_no_rs`: descartado por falta de RS verificable.
- `rejected_non_oral`: descartado por formato no apto para suplemento oral.
- `manual_rejected`: descartado manualmente por admin.
- `promoted`: ya fue insertado/actualizado en PostgreSQL.

La promoción no edita `approved_catalog.csv` directamente. Inserta o actualiza
el producto en PostgreSQL con `source_strategy=admin_candidate_promotion`,
crea el enlace producto-componente y registra auditoría en `admin_actions`.
También deja evidencia en:

```txt
data/reports/scraping/catalog_candidate_actions.json
data/reports/scraping/catalog_candidate_promotions.csv
```

Regla mínima de promoción: el candidato debe tener `registro_sanitario` y
`component_traceable=true_rs_component`. Si no cumple, la API responde error y
el admin debe marcarlo como pendiente de RS o rechazado.

Para recalcular el resumen sin volver a llamar a las farmacias:

```bash
python3 scripts/scraping/buscar_productos_rotacion_componentes.py --skip-scrape
```

Para atacar componentes concretos:

```bash
python3 scripts/scraping/buscar_productos_rotacion_componentes.py \
  --component COMP_D691B9C2718F \
  --component COMP_9C5C72058DB1
```

Si la validación falla, el script termina con código distinto de cero y deja un JSON como:

```txt
data/reports/scraping/weekly_catalog_validation_YYYYMMDDTHHMMSSZ.json
```

Además mantiene dos archivos de estado para staging/admin:

```txt
data/reports/scraping/catalog_pipeline_current_report.json
data/reports/scraping/catalog_pipeline_alert.json
```

`catalog_pipeline_alert.json` queda en `passed` si la corrida o validación
terminó correctamente, y en `failed` si el script abortó. `/health/ops` expone
esa señal como `scraping_alert`.

Worker Docker semanal:

```bash
cd /home/leo/DPD/Proyecto
docker compose --env-file .env.staging -f docker-compose.staging.yml --profile jobs up -d catalog-weekly
```

Para forzar ejecución inmediata al levantar el worker:

```env
CATALOG_WEEKLY_RUN_ON_START=true
```

## Snapshot mensual de farmacias

Para una corrida mensual más profunda:

```bash
bash scripts/scraping/snapshot_farmacias_mensual.sh
```

Defaults mensuales:

```bash
RUN_LABEL=monthly
LIMIT_PER_PHARMACY=2500
SCRAPER_DELAY=0.5
MIN_RAW_ROWS=1000
MIN_APPROVED_ROWS=500
MIN_PHARMACIES=3
MAX_RAW_AGE_HOURS=72
```

También puede importar a PostgreSQL:

```bash
IMPORT_TO_POSTGRES=1 bash scripts/scraping/snapshot_farmacias_mensual.sh
```

Cron sugerido para el día 1 de cada mes a las 04:30:

```cron
30 4 1 * * cd /home/leo/DPD/Proyecto/Suplematch-Backend && /usr/bin/env bash scripts/scraping/snapshot_farmacias_mensual.sh
```

## Validación manual de una corrida

```bash
python3 scripts/validation/validar_pipeline_catalogo.py \
  --mode manual \
  --raw data/raw/pharmacies/supplements_exhaustive_clean.csv \
  --approved data/catalog/approved_catalog.csv \
  --rejects data/reports/scraping/supplements_rejected.csv \
  --min-raw-rows 500 \
  --min-approved-rows 250 \
  --min-pharmacies 3
```

## Notas

Algunas tiendas no publican el registro sanitario en el listado. En esos casos `--infer-registro` intenta encontrarlo por similitud contra `digemid_limpio.csv`; los matches se mantienen exigentes para evitar falsos positivos.

En staging Docker se montan `data/catalog`, `data/raw` y `data/reports` como
volúmenes del host. Así el panel admin puede leer rechazos, componentes
faltantes y reportes generados por el worker semanal aunque `data/reports` esté
excluido del build de la imagen.

Si la lista DIGEMID real se reemplaza, debe mantenerse la columna `item` con el registro sanitario y la columna `Producto` con el nombre comercial/formal.
