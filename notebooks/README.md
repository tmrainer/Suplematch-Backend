# Notebooks

Los notebooks son demostraciones ejecutables de los pipelines. La ejecucion
oficial repetible sigue viviendo en `scripts/`.

Orden sugerido:

- `00_overview`: mapa del pipeline completo.
- `01_data_sources`: fuentes oficiales y trazabilidad.
- `02_scraping`: exploracion de scraping de farmacias.
- `03_cleaning`: limpieza y normalizacion.
- `04_synthetic_data`: generacion de datos sinteticos.
- `05_training`: entrenamiento de modelos.
- `06_evaluation`: benchmarks, golden cases y holdouts.
- `07_model_export`: generacion y validacion de `.pkl`.

Notas:

- Las celdas de scraping, limpieza, evaluacion y exportacion usan `RUN = False`
  por defecto para evitar red o sobrescritura accidental.
- El notebook de entrenamiento ejecuta un smoke temporal y no sobrescribe
  `models/runtime`.
- Las celdas de codigo no tienen comentarios para mantener la demo limpia.
