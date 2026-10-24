# Enriquecimiento de calidad del catálogo

El scraping captura productos, precios, disponibilidad, URL y registro sanitario. Después, el pipeline ejecuta `scripts/catalog/enriquecer_catalogo_verificable.py` para mejorar la calidad comercial antes de importar a PostgreSQL.

## Qué agrega

- Dosis normalizada cuando falta en el parser base: `amount`, `unit`, `amount_mg`, `amount_source`.
- Tamaño de presentación cuando puede inferirse: `serving_size`, `units_per_pack`.
- Marca inferida con trazabilidad: `brand`, `brand_confidence`, `brand_source`.
- Flags de restricciones separados entre verificados e inferidos:
  - verificados: `contains_fish`, `contains_gelatin`, `contains_dairy`, etc.
  - inferidos: `contains_fish_inferred`, `contains_gelatin_inferred`, `contains_dairy_inferred`, etc.
- Estado de etiqueta:
  - `label_status=verified`: sale de composición/forma DIGEMID o campo explícito.
  - `label_status=inferred`: sale del nombre, URL o texto comercial.
  - `label_status=unknown`: no hay evidencia suficiente.
- Nivel de trazabilidad de restricciones: `restriction_traceability_level`.

### Conversión UI → mg (`amount_to_mg`)

- Vitamina D: 1 UI = 0.025 mcg. Vitamina A: 1 UI = 0.3 mcg.
- Vitamina E depende de la forma (fuente: NIH ODS, *Vitamin E Health Professional Fact Sheet*):
  - d-alfa-tocoferol natural (RRR): 1 UI = 0.67 mg. Se detecta por `D-ALFA`/`D-ALPHA`/`RRR`/`NATURAL`.
  - dl-alfa-tocoferol sintético (all-rac): 1 UI = 0.45 mg. Se detecta por `DL-ALFA`/`DL-ALPHA`/`ALL-RAC`/`SINTETIC`.
  - Si la forma no se distingue se usa **0.67 mg/UI**. Decisión: para evaluar límites superiores de
    seguridad es conservador asumir el factor que produce más mg; el factor sintético solo se aplica con
    evidencia textual (ingrediente, `digemid_composicion`, `digemid_producto` o nombre comercial).

## Parser de composición DIGEMID (`scripts/catalog/parser_composicion.py`)

`parse_composition` devuelve una lista de `{ingredient, amount, unit, amount_mg, salt_form}`:

- Unidades de masa (`mg`, `g`, `mcg`/`µg`/`ug`) se convierten a `amount_mg`. `kg` se reconoce como
  unidad pero no se convierte (`amount_mg=None`): una cantidad en kilogramos es un peso de presentación,
  no una dosis de componente.
- `UI`/`IU`, `mL` y `%` quedan sin `amount_mg`. Probióticos: `UFC`/`CFU` se normalizan a `unit="UFC"`,
  `amount_mg=None`; se acepta notación científica ("1 x 10^9 UFC").
- Separadores de miles por coma o punto ("2,000.000000", "1.000,5") y por espacio ("2 000 UI"). El espacio
  solo se acepta cuando el texto no usa el formato DIGEMID de seis decimales (en ese formato "VITAMINA D3
  100.000000 UI" nunca es 3 100 UI). Además se excluyen números pegados a letras ("B12 500") y "OMEGA 3 500 mg".
- Las cabeceras de porción ("POR DOSIS 15.00 mL - ", "POR SOBRE 2.00 g - ") se descartan.
- Paréntesis que describen la sal o forma ("ZINC (COMO SULFATO DE ZINC) 10 mg", "(EQUIVALENTE A ...)" o
  cualquier paréntesis con dosis adentro) no generan un ingrediente aparte: van a `salt_form` del
  ingrediente que acompañan. Paréntesis descriptivos ("VITAMINA E (TOCOFEROL)", "(EPA)") se conservan en el nombre.

Pendiente: regenerar `data/training/supplement_model/product_components.csv` con este parser. El catálogo
servido todavía contiene ~128 filas con `amount=0.0` e ingredientes truncados ("VITAMINA D3 2") producidas
por una versión anterior; el parser actual ya las resuelve (test `tests/unit/test_catalog_parser_composicion.py`).

## Reportes generados

Por defecto quedan en `data/reports/catalog_quality/`:

- `catalog_quality_summary.json`
- `productos_sin_dosis.csv`
- `productos_sin_amount_mg.csv`
- `productos_sin_marca.csv`
- `productos_restricciones_incompletas.csv`
- `componentes_con_menos_de_3_productos.csv`
- `componentes_recomendables_sin_producto.csv`

Estos archivos indican qué corregir manualmente o qué buscar en siguientes scrapeos.

## Comandos

```bash
cd /home/leo/DPD/Proyecto/Suplematch-Backend
python3 scripts/catalog/enriquecer_catalogo_verificable.py \
  --input data/catalog/approved_catalog.csv \
  --report-dir data/reports/catalog_quality
```

El importador (`scripts/catalog/importar_catalogo_postgres.py`) marca `commercial_status="inactive"` los
productos ya existentes en PostgreSQL que no aparecen en el CSV importado (solo para farmacias presentes en
el CSV; `blocked` no se toca; guarda `previous_commercial_status`, `deactivated_reason` y `deactivated_at`
en `raw_payload_json`). Un producto inactivo que reaparece vuelve a `active`. Para desactivar este
comportamiento: `--no-deactivate-missing`. `CatalogRepository` solo sirve `active`/`preferred`.

`scripts/catalog/guardar_snapshots_precios.py` guarda **un snapshot por producto** (farmacia + sku/url), no
por fila componente. `scripts/catalog/generar_diff_catalogo.py` lee el motivo de rechazo de la columna
correcta (`catalog_rejection_reason` → `rejection_reason` → `scraper_rejection_reason` → `reason`),
separando motivos múltiples unidos por `;`, y reporta `reason_column` en el JSON.

Para importar el catálogo enriquecido en staging usando Docker y manteniendo los archivos del host:

```bash
cd /home/leo/DPD/Proyecto
docker compose --env-file .env.staging -f docker-compose.staging.yml run --rm \
  -v /home/leo/DPD/Proyecto/Suplematch-Backend/data:/app/data \
  backend python scripts/catalog/importar_catalogo_postgres.py \
  --catalog data/catalog/approved_catalog.csv
```

## Uso en recomendación

El motor comercial ya usa estos campos para:

- premiar productos con dosis declarada;
- premiar etiquetas verificadas;
- penalizar productos con restricciones inferidas;
- bloquear o advertir según restricciones del usuario;
- mejorar comparación de productos por trazabilidad.

### Seguridad sobre la composición completa

`app/domains/catalog/seguridad_productos.product_text` incluye `digemid_composicion` y `product_ingredients`
(todas las filas del mismo producto), de modo que las reglas de seguridad evalúan el producto completo y no
solo la fila por la que fue elegido: un multivitamínico seleccionado por su zinc se bloquea en
`embarazo_lactancia` si su composición DIGEMID declara vitamina A en dosis alta, y se bloquea en
`problema_tiroideo` si declara yodo/yoduro.

En modo CSV, `ProductCatalogService` construye cada producto con la composición completa
(`catalogo_csv._catalog_compositions`, agrupando por farmacia + sku/url) y con los flags verificados del
enriquecimiento (`contains_*`, `*_verified`, `label_status`, `label_verification_source`) en
`restriction_flags_verified`, en lugar de una lista vacía.

Regla con límite de dosis: `retinol_pregnancy_block` usa `dose_limit_mcg=3000` (UL de vitamina A
preformada en embarazo, NIH ODS; 1 UI = 0.3 mcg). Si la composición declara una dosis **por debajo** del
límite, la regla advierte y penaliza en vez de bloquear; sin dosis declarada o con dosis ≥ límite, bloquea.

