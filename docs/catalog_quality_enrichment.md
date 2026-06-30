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

