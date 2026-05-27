# SupleMatch Backend

Backend FastAPI para generar recomendaciones de suplementos, registrar feedback y reordenar packs usando señales de uso.

## Requisitos

- Python 3.12
- scikit-learn 1.5.0
- Linux/macOS o WSL recomendado para la ejecución local

`scikit-learn==1.5.0` está fijado en `requirements.txt` porque los artefactos `.pkl` del modelo deben cargarse con una versión compatible.

## Setup Local

Crear y activar el entorno virtual:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Actualizar herramientas base e instalar dependencias:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Verificar versiones clave:

```bash
python --version
python -c "import sklearn; print(sklearn.__version__)"
```

La versión esperada de `sklearn` es `1.5.0`.

Opcionalmente, copiar variables locales:

```bash
cp .env.example .env
```

Variables útiles:

```txt
MODEL_DIR=app/ml/runtime
FEEDBACK_DB_PATH=app/ml/runtime/feedback.sqlite3
```

## Ejecutar API

Desde la raíz del proyecto:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/api/v1/health
```

Estado de modelos:

```bash
curl http://localhost:8000/api/v1/debug/model-status
```

## Probar `/recommend`

```bash
curl -X POST http://localhost:8000/api/v1/recommend \
  -H "Content-Type: application/json" \
  -d '{
    "edad_rango": "31_50",
    "horas_sueno": "5_7h",
    "frecuencia_ejercicio": "1_2_semana",
    "dieta": "regular",
    "fatiga": "a_menudo",
    "exposicion_solar": "menos_15min",
    "frecuencia_enfermedad": "1_2_anio",
    "estres": "moderado",
    "alcohol": "ocasional"
  }'
```

La respuesta incluye `recommendation_id`, `conditions`, `recommendations`, `packs_ranked`, `sinergias`, `alertas` y `disclaimer`.
También incluye campos listos para frontend, como `conditions_display`, `display_name`, `reason`, `dosage_hint`, `priority` e `icon_key`.

Si los modelos o artefactos no están disponibles, la API responde de forma controlada:

```json
{
  "detail": "No se pudo generar la recomendación. Revisa los artefactos del modelo."
}
```

## Probar `/feedback`

Usa un `recommendation_id` y un `pack_id` devueltos por `/recommend`:

```bash
curl -X POST http://localhost:8000/api/v1/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "recommendation_id": "rec_demo",
    "pack_id": "pack_demo",
    "component_ids": ["cmp_vit_d", "cmp_calcium"],
    "rating": 5,
    "conditions": ["DEFICIT_VIT_D"],
    "comment": "Me sirvió la recomendación"
  }'
```

`rating` debe estar entre `1` y `5`.

Resumen de feedback:

```bash
curl http://localhost:8000/api/v1/feedback/summary
```

## Modelos

El runtime carga los modelos desde:

```txt
app/ml/runtime/modelo1_pipeline.pkl
app/ml/runtime/modelo2_artifacts_cpu.pkl
```

La carpeta se puede cambiar con:

```env
MODEL_DIR=/ruta/a/modelos
```

También existen artefactos en:

```txt
artifacts/models/modelo1_pipeline.pkl
artifacts/models/modelo2_artifacts.pkl
```

Para el MVP actual, el pipeline usado por la API vive en:

```txt
app/ml/runtime/pipeline_completo.py
```

## Persistencia de Feedback

La persistencia principal local usa SQLite:

```txt
app/ml/runtime/feedback.sqlite3
```

La ruta se puede cambiar con:

```env
FEEDBACK_DB_PATH=/ruta/local/feedback.sqlite3
```

Tablas mínimas:

```txt
recommendation_events
feedback_events
```

Los JSON legacy se mantienen como fuente de migración para demos locales:

```txt
app/ml/runtime/recommendation_events.json
app/ml/runtime/user_feedback_events.json
```

En el primer acceso al store, los eventos existentes en esos JSON se migran a SQLite con `INSERT OR IGNORE`.

## Tests Mínimos

Si `pytest` está instalado:

```bash
pytest tests/integration -q
```

Los tests de integración cubren:

```txt
GET /api/v1/health
GET /api/v1/debug/model-status
POST /api/v1/recommend
POST /api/v1/feedback
```

## Validación de Calidad de Recomendaciones

Para validar el comportamiento del modelo con datos reales y medir el impacto del feedback:

```bash
python scripts/validate_recommendation_quality.py
```

La validación ejecuta 15 perfiles ideales no saludables y revisa:

```txt
condiciones accionables detectadas
mínimo 3 suplementos recomendados por perfil
packs_ranked generado
top pack con al menos 2 suplementos
combo sin alertas riesgosas
feedback_count sube después del feedback
ratings positivos elevan score_feedback
ratings negativos reducen score_feedback
score_final cambia en recomendaciones posteriores
```

Por defecto usa una base SQLite temporal para no contaminar la demo local. Para guardar un reporte JSON:

```bash
python scripts/validate_recommendation_quality.py --output reports/recommendation_quality.json
```

Para validar usando el store real configurado por `FEEDBACK_DB_PATH`:

```bash
python scripts/validate_recommendation_quality.py --use-runtime-store
```
