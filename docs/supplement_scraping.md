# SupleMatch supplement scraping

Este flujo genera el CSV bruto de productos comerciales y luego reconstruye el catálogo aprobado que usa el backend.

## Archivo bruto esperado

El scraper escribe:

```txt
data/raw/csv/supplements_exhaustive_clean.csv
```

Columnas compatibles con `scripts/build_approved_catalog.py`:

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
```

Por defecto deja productos con alguna trazabilidad de componente:

- `true_rs_component`: registro sanitario validado contra `digemid_limpio.csv` y componente confiable en `product_components.csv`.
- `true_component_name_with_rs_unmapped`: tiene RS local, pero no está mapeado en `product_components.csv`; el componente se detectó por nombre usando los CSV del proyecto.
- `true_component_name_no_rs`: no tiene RS publicado/inferido, pero el componente se detectó por nombre usando `product_components.csv` y `data/training/modelo2/Component_Master_Clean.csv`.

El catálogo que usa el backend sigue siendo más estricto: `scripts/build_approved_catalog.py` solo incluye productos con RS validado y componente mapeado en `product_components.csv`.

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
python3 scripts/scraping/supplements_exhaustive_scraper.py \
  --limit-per-pharmacy 2000 \
  --infer-registro \
  --out data/raw/csv/supplements_exhaustive_clean.csv \
  --rejects-out data/reports/scraping/supplements_rejected.csv
```

Para probar una farmacia con pocos registros:

```bash
python3 scripts/scraping/supplements_exhaustive_scraper.py \
  --pharmacy hogarysalud \
  --limit-per-pharmacy 20 \
  --allow-unverified
```

## Reconstruir catálogo aprobado

Después de generar el CSV bruto:

```bash
python3 scripts/build_approved_catalog.py \
  --scraped data/raw/csv/supplements_exhaustive_clean.csv \
  --digemid digemid_limpio.csv \
  --components product_components.csv \
  --out data/catalog/approved_catalog.csv
```

## Automatización semanal

Ejecución manual del flujo completo:

```bash
bash scripts/scraping/run_weekly_supplement_update.sh
```

Cron sugerido para domingos 03:30:

```cron
30 3 * * 0 cd /home/leo/DPD/Proyecto/Suplematch-Backend && /usr/bin/env bash scripts/scraping/run_weekly_supplement_update.sh
```

Variables opcionales:

```bash
LIMIT_PER_PHARMACY=1000
SCRAPER_DELAY=0.25
```

Ejemplo:

```bash
LIMIT_PER_PHARMACY=1500 SCRAPER_DELAY=0.5 bash scripts/scraping/run_weekly_supplement_update.sh
```

## Notas

Algunas tiendas no publican el registro sanitario en el listado. En esos casos `--infer-registro` intenta encontrarlo por similitud contra `digemid_limpio.csv`; los matches se mantienen exigentes para evitar falsos positivos.

Si la lista DIGEMID real se reemplaza, debe mantenerse la columna `item` con el registro sanitario y la columna `Producto` con el nombre comercial/formal.
