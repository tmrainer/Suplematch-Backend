# Actualización semanal DIGEMID

SupleMatch usa `data/raw/digemid/digemid_limpio.csv` como fuente regulatoria para validar registros sanitarios, composición y forma farmacéutica.

## Enfoque

El sitio público de consulta DIGEMID puede responder con protección Cloudflare a peticiones servidor-servidor. Por eso el worker no intenta saltarse protecciones ni hacer scraping agresivo. El diseño es conservador:

1. Si se configura `DIGEMID_SOURCE_URL`, intenta descargar una fuente oficial exportable.
2. Si se configura `DIGEMID_SOURCE_FILE`, usa ese archivo como fuente oficial/manual.
3. Opcionalmente, si `DIGEMID_VISUAL_SCRAPER_ENABLED=1`, consulta la página visual pública con Playwright.
4. Valida columnas mínimas: `item`, `Producto`, `Composición`.
5. Normaliza el CSV a `data/raw/digemid/digemid_limpio.csv`.
6. Guarda backup y snapshot en `data/reports/digemid/`.
7. Si falla o no hay fuente configurada, conserva el último CSV válido y deja reporte.

Esto evita que el scraping semanal de farmacias falle por una caída temporal o bloqueo del portal DIGEMID.

## Variables

```env
DIGEMID_WEEKLY_ENABLED=1
DIGEMID_SOURCE_URL=
DIGEMID_SOURCE_FILE=
DIGEMID_MIN_ROWS=1000
DIGEMID_FAIL_ON_FETCH_ERROR=0
DIGEMID_VISUAL_SCRAPER_ENABLED=0
DIGEMID_VISUAL_URL=https://www.digemid.minsa.gob.pe/rsProductosFarmaceuticos/
DIGEMID_VISUAL_QUERIES=
DIGEMID_VISUAL_QUERY_FILE=
DIGEMID_VISUAL_MAX_QUERIES=20
DIGEMID_VISUAL_MAX_PAGES_PER_QUERY=3
DIGEMID_VISUAL_PROMOTE_TO_SOURCE=0
DIGEMID_VISUAL_MIN_PROMOTE_ROWS=1
DIGEMID_VISUAL_STORAGE_STATE=
DIGEMID_VISUAL_SAVE_STORAGE_STATE=
```

Para staging, estas variables se leen desde `.env.staging`.

## Comandos

Validar y conservar el CSV actual si no hay fuente configurada:

```bash
cd /home/leo/DPD/Proyecto/Suplematch-Backend
bash scripts/scraping/actualizar_digemid_semanal.sh
```

Actualizar desde un archivo oficial descargado manualmente:

```bash
cd /home/leo/DPD/Proyecto/Suplematch-Backend
DIGEMID_SOURCE_FILE=/ruta/al/export_digemid.csv \
bash scripts/scraping/actualizar_digemid_semanal.sh
```

Actualizar desde URL oficial si existe un export accesible:

```bash
cd /home/leo/DPD/Proyecto/Suplematch-Backend
DIGEMID_SOURCE_URL="https://fuente-oficial/export.csv" \
bash scripts/scraping/actualizar_digemid_semanal.sh
```

Ejecutar scraper visual incremental sin reemplazar el CSV maestro:

```bash
cd /home/leo/DPD/Proyecto/Suplematch-Backend
DIGEMID_VISUAL_SCRAPER_ENABLED=1 \
DIGEMID_VISUAL_QUERIES="Ashwagandha,L-teanina,Valeriana,Probióticos" \
bash scripts/scraping/actualizar_digemid_semanal.sh
```

El scraper visual genera:

```txt
data/reports/digemid/digemid_visual_candidates.csv
data/reports/digemid/digemid_visual_scrape_report.json
data/reports/digemid/visual_html/
```

Para promover candidatos visuales al CSV maestro, debe activarse explícitamente:

```bash
DIGEMID_VISUAL_PROMOTE_TO_SOURCE=1
```

Usarlo solo si el reporte muestra filas completas con `item`, `Producto` y `Composición`.

Si se ejecuta en un entorno donde la página permita sesión/cookies, se puede reutilizar estado de navegador:

```bash
DIGEMID_VISUAL_STORAGE_STATE=/app/data/reports/digemid/storage_state.json
```

Para guardar el estado después de una corrida:

```bash
DIGEMID_VISUAL_SAVE_STORAGE_STATE=/app/data/reports/digemid/storage_state.json
```

## Reporte

El reporte principal queda en:

```txt
data/reports/digemid/digemid_update_report.json
```

Campos clave:

- `status=updated`: se actualizó el CSV.
- `status=retained_previous`: se conservó el CSV anterior.
- `reason=source_url_blocked_by_cloudflare`: el portal bloqueó la petición automática.
- `reason=source_url_is_search_html_not_export`: se pasó una página visual, no un export CSV/XLSX/JSON.
- `missing_component_map_rs`: registros DIGEMID que no tienen mapeo en `product_components.csv`.

## Scraper visual

El scraper visual usa Playwright/Chromium. Es útil para búsquedas incrementales por términos específicos cuando no existe un export oficial disponible.

Limitaciones:

- No debe usarse para scraping masivo agresivo.
- Puede fallar si DIGEMID cambia el HTML, requiere sesión o presenta protección.
- No sustituye una descarga oficial solicitada por Acceso a Información Pública.
- Por defecto no reemplaza el CSV maestro; solo deja candidatos y evidencia HTML.
- En la prueba de staging del 2026-06-25, la página visual respondió bloqueada incluso con Chromium headless; el scraper guardó evidencia y no modificó el CSV maestro.

## Relación con el catálogo comercial

Actualizar DIGEMID no basta para que un producto sea recomendable. El producto debe cumplir:

1. estar en el scraping comercial;
2. tener registro sanitario detectable o inferible;
3. existir en DIGEMID;
4. tener composición;
5. tener mapeo de composición a `component_id` en `product_components.csv`.

Por eso algunos productos con texto comercial como Ashwagandha o Valeriana no pasan a compra directa si el registro sanitario no aparece o si la composición oficial no respalda ese componente.
