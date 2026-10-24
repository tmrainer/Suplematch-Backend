# Actualización semanal DIGEMID

SupleMatch usa `data/raw/digemid/digemid_limpio.csv` como fuente regulatoria para validar registros sanitarios, composición y forma farmacéutica.

## Estado de la fuente (verificado 2026-10-22)

- El portal https://www.digemid.minsa.gob.pe/rsProductosFarmaceuticos/ es **solo consulta web paginada**. No ofrece descarga CSV/XLSX ni API documentada.
- En https://www.datosabiertos.gob.pe **no existe dataset de registro sanitario DIGEMID** (búsquedas "digemid" y "registro sanitario": 0 resultados relevantes; lo único cercano es un registro de farmacias de SUSALUD, que no sirve para este fin).
- El portal responde con protección Cloudflare a clientes automatizados. **No se evade**: el worker no reutiliza cookies, no espera "challenges" ni suplanta un navegador; si detecta bloqueo, aborta con mensaje claro y deja evidencia HTML.

### `digemid_limpio.csv` es una extracción manual fechada

El maestro actual no se regenera automáticamente desde una fuente oficial. Debe tratarse como una **extracción manual con fecha**: cada vez que se reemplace o fusione, dejar constancia de la fecha y el origen (export oficial, consulta manual, candidatos visuales) en `data/reports/digemid/digemid_update_report.json` (campos `source`, `updated_at`, `merge`). El archivo no está versionado en git; conservar los snapshots de `data/reports/digemid/`.

### Vía recomendada: solicitud formal de acceso a la información pública

Para obtener el padrón completo y actualizable, la vía correcta es una **solicitud de acceso a la información pública** a DIGEMID/MINSA (Ley N.º 27806, Texto Único Ordenado aprobado por D.S. 021-2019-JUS), pidiendo el registro de productos farmacéuticos, dietéticos y edulcorantes en formato reutilizable (CSV/XLSX) y, de ser posible, su actualización periódica. El archivo recibido se carga con `DIGEMID_SOURCE_FILE` (ver comandos abajo). Mientras no exista esa fuente, el scraper visual solo sirve para consultas incrementales acotadas.

## Enfoque

El worker es conservador:

1. Si se configura `DIGEMID_SOURCE_URL`, intenta descargar una fuente oficial exportable (hoy no existe ninguna; se deja para cuando la haya).
2. Si se configura `DIGEMID_SOURCE_FILE`, usa ese archivo como fuente oficial/manual.
3. Opcionalmente, si `DIGEMID_VISUAL_SCRAPER_ENABLED=1`, consulta la página visual pública con Playwright, con User-Agent honesto (`SupleMatch DIGEMID reader/1.0 (...; contacto: ...)`) y sesión limpia.
4. Valida columnas mínimas: `item`, `Producto`, `Composición`, y el mínimo de filas (`DIGEMID_MIN_ROWS`, default 1000) sobre la fuente entrante.
5. **Fusiona** la fuente con el maestro `data/raw/digemid/digemid_limpio.csv` por RS normalizado: filas nuevas se agregan, existentes se actualizan con los valores no vacíos de la fuente, **nada se borra**. `--replace` fuerza reemplazo total (solo para re-cargar un export oficial completo).
6. Guarda backup (`digemid_limpio_previous_<stamp>.csv`) y snapshot en `data/reports/digemid/`.
7. Si falla, bloquea o no hay fuente configurada, conserva el último CSV válido y deja reporte.

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
DIGEMID_VISUAL_CONTACT=
```

`DIGEMID_VISUAL_CONTACT` se incluye en el User-Agent de los lectores DIGEMID. Ya no existen `DIGEMID_VISUAL_STORAGE_STATE`, `DIGEMID_VISUAL_SAVE_STORAGE_STATE`, `DIGEMID_VISUAL_CHALLENGE_WAIT_MS` ni `DIGEMID_VISUAL_MIN_PROMOTE_ROWS`: no se reutilizan cookies, no se espera al challenge de Cloudflare y la promoción de candidatos usa el mínimo normal de filas.

Para staging, estas variables se leen desde `.env.staging`.

## Comandos

Validar y conservar el CSV actual si no hay fuente configurada:

```bash
cd /home/leo/DPD/Proyecto/Suplematch-Backend
bash scripts/scraping/actualizar_digemid_semanal.sh
```

Actualizar (fusionar) desde un archivo oficial obtenido por solicitud de acceso a la información o descargado manualmente:

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

La promoción fusiona (no reemplaza) y exige el mínimo normal de filas (`DIGEMID_MIN_ROWS`, default 1000) sobre los candidatos; una extracción visual de pocas filas queda como candidatos en `data/reports/digemid/` y no toca el maestro. Si el scraper visual terminó bloqueado (código de salida 3), no se promueve nada.

## Reporte

El reporte principal queda en:

```txt
data/reports/digemid/digemid_update_report.json
```

Campos clave:

- `status=updated`: se actualizó el CSV.
- `status=retained_previous`: se conservó el CSV anterior.
- `mode=merge|replace` y `merge={existing_rows, incoming_rows, added, updated, unchanged, total_rows}`: resultado de la fusión con el maestro.
- `reason=source_url_blocked_by_cloudflare`: el portal bloqueó la petición automática.
- `reason=source_url_is_search_html_not_export`: se pasó una página visual, no un export CSV/XLSX/JSON.
- `reason=too_few_rows:N<min_rows:M`: la fuente entrante no alcanzó el mínimo; el maestro no se tocó.
- `missing_component_map_rs`: registros DIGEMID que no tienen mapeo en `product_components.csv`.

El reporte del scraper visual (`digemid_visual_scrape_report.json`) usa `status=blocked`, `reason=portal_blocked` y `blocked_evidence` cuando el portal respondió bloqueado; el proceso sale con código 3.

## Scraper visual

El scraper visual usa Playwright/Chromium. Es útil para búsquedas incrementales por términos específicos cuando no existe un export oficial disponible.

Limitaciones:

- No debe usarse para scraping masivo agresivo.
- Se identifica con User-Agent honesto y sesión limpia; no reutiliza cookies ni espera al challenge de Cloudflare. Si el portal responde bloqueado, aborta (código 3) con mensaje claro y evidencia en `visual_html/`.
- Puede fallar si DIGEMID cambia el HTML, requiere sesión o presenta protección.
- No sustituye una descarga oficial solicitada por Acceso a Información Pública (ver arriba).
- Por defecto no toca el CSV maestro; solo deja candidatos y evidencia HTML. Con `DIGEMID_VISUAL_PROMOTE_TO_SOURCE=1` fusiona, nunca reemplaza.
- En la prueba de staging del 2026-06-25, la página visual respondió bloqueada incluso con Chromium headless; el scraper guardó evidencia y no modificó el CSV maestro. Verificación 2026-10-22: sigue sin existir CSV/API pública.

## Relación con el catálogo comercial

Actualizar DIGEMID no basta para que un producto sea recomendable. El producto debe cumplir:

1. estar en el scraping comercial;
2. tener registro sanitario detectable o inferible;
3. existir en DIGEMID;
4. tener composición;
5. tener mapeo de composición a `component_id` en `product_components.csv`.

Por eso algunos productos con texto comercial como Ashwagandha o Valeriana no pasan a compra directa si el registro sanitario no aparece o si la composición oficial no respalda ese componente.
