# Estructura del Backend

Convencion actual:

- Carpetas en ingles: representan capas tecnicas o etapas del pipeline.
- Archivos `.py` nuevos en espanol: describen acciones o conceptos de negocio.
- `app/` contiene codigo runtime de FastAPI organizado por dominios.
- `data/` contiene datos y reportes, no codigo de aplicacion.
- `models/` contiene artefactos `.pkl` usados por runtime.
- `notebooks/` contiene trabajo exploratorio o explicativo.
- `scripts/` contiene ejecuciones repetibles desde CLI.

## Carpetas Principales

```txt
app/          FastAPI runtime, dominios de negocio, DB, core y ML.
data/         CSVs, knowledge base, catalogos, training, evaluacion y reportes.
models/       Modelos entrenados y backups.
notebooks/    Exploracion reproducible y explicacion de pipelines.
scripts/      Operaciones, catalogo, scraping, training y validacion.
tests/        Pruebas unitarias, integracion y externas.
docs/         Documentacion tecnica y operativa.
alembic/      Migraciones de base de datos.
docker/       Imagen y entrypoint backend.
var/          Archivos runtime/legacy locales que no son codigo.
```

## App

```txt
app/
├── api/
│   └── v1/
│       ├── router.py              # Ensambla rutas publicas.
│       ├── dependencies.py        # Dependencias compartidas de FastAPI.
│       └── endpoints/
│           ├── health.py          # Endpoint tecnico.
│           └── debug.py           # Endpoint tecnico/local.
├── core/                          # Configuracion, seguridad, errores, rate limit y observabilidad base.
├── db/                            # SQLAlchemy models, session y conexion.
├── domains/
│   ├── admin/
│   ├── auth/
│   ├── catalog/
│   ├── feedback/
│   ├── history/
│   ├── labs/
│   ├── recommendations/
│   ├── reviews/
│   ├── survey/
│   └── users/
├── ml/                            # Carga e inferencia ML.
└── data/                          # Validadores de datos usados por runtime.
```

Cada dominio agrupa sus piezas internas con archivos en espanol:

```txt
app/domains/recommendations/
├── rutas.py
├── esquemas.py
├── servicio_recomendaciones.py
├── repositorio_recomendaciones.py
└── repositorio_metricas_recomendacion.py
```

Regla de lectura:

- `rutas.py`: endpoints FastAPI del dominio.
- `esquemas.py`: modelos Pydantic del dominio.
- `servicio_*.py`: logica de negocio.
- `repositorio_*.py`: acceso a PostgreSQL.
- archivos especificos: helpers del dominio, por ejemplo `seguridad_productos.py`.

Dominios con modulos auxiliares:

- `catalog/catalogo_csv.py`: parseo y agrupacion del catalogo aprobado en CSV.
- `catalog/seguridad_productos.py`: deteccion de restricciones y riesgos por producto.
- `labs/biomarcadores.py`: biomarcadores, aliases, rangos y criticidad OCR.
- `recommendations/reglas_presentacion.py`: etiquetas, warnings y reglas de explicacion.

## Data

```txt
data/
├── knowledge/                 # Fuentes oficiales, reglas, biomarcadores y links condicion-componente.
├── catalog/                   # Catalogo comercial aprobado para importar/servir.
├── raw/
│   ├── digemid/               # Fuente DIGEMID normalizada.
│   ├── nhanes/                # Fuentes NHANES por ciclo.
│   └── pharmacies/            # Scraping bruto de farmacias.
├── processed/                 # Datos intermedios normalizados.
├── training/
│   ├── condition_model/       # Dataset y contrato de features del modelo de condiciones.
│   └── supplement_model/      # Componentes y relaciones para modelo recomendador.
├── evaluation/
│   └── condition_model/       # Golden cases, holdout, benchmark labels y casos reales anonimizados.
├── reports/
│   ├── condition_model/       # Metricas, predicciones y reportes del modelo de condiciones.
│   └── scraping/              # Logs y validaciones de scraping/catalogo.
└── samples/                   # Ejemplos pequenos para demos/manual testing.
```

## Models

```txt
models/
├── runtime/   # `.pkl` y metadata cargados por FastAPI.
└── backups/   # Backups fechados de modelos.
```

El runtime usa `MODEL_DIR`, por defecto `models/runtime`.

Documentacion relacionada:

- `docs/model2_component_ranker.md`: explica como Modelo 2 convierte condiciones
  probables en componentes rankeados antes de buscar productos comerciales.

## Notebooks

```txt
notebooks/
├── 00_overview/
├── 01_data_sources/
├── 02_scraping/
├── 03_cleaning/
├── 04_synthetic_data/
├── 05_training/
├── 06_evaluation/
└── 07_model_export/
```

Un notebook puede explicar, explorar y justificar. Un script debe ser el camino
oficial para ejecutar procesos repetibles.

Cada carpeta contiene un notebook base con objetivo, entradas, comando oficial y
salida esperada. Estos notebooks sirven para presentacion y trazabilidad; los
scripts siguen siendo la fuente ejecutable principal.

## Scripts

```txt
scripts/
├── ops/          # Inicializacion, seed, DB de test, export de contrato.
├── catalog/      # Construccion/importacion de catalogo.
├── scraping/     # Scrapers y jobs periodicos.
├── training/     # Entrenamiento, benchmarks y calibracion.
└── validation/   # Smoke/quality checks.
```

Ejemplos:

```bash
python3 scripts/ops/sembrar_base.py
python3 scripts/catalog/importar_catalogo_postgres.py --catalog data/catalog/approved_catalog.csv
bash scripts/scraping/actualizar_suplementos_semanal.sh
python3 scripts/training/ejecutar_suite_benchmark_condiciones.py --skip-train
```

Se mantienen wrappers legacy en `scripts/` y `scripts/scraping/` para comandos
antiguos. Los wrappers delegan a la ruta nueva y evitan romper documentacion o
automatizaciones existentes mientras se migra al esquema ordenado.
