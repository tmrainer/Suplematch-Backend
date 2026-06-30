# MVP Final Operativo

Este documento resume el cierre de producto para demo/staging.

## Flujo demo usuario

1. Usuario completa encuesta.
2. Modelo 1 devuelve probabilidades de condiciones/riesgos.
3. Modelo 2 convierte condiciones en componentes.
4. Safety decide si se puede convertir a producto comercial.
5. Motor comercial rankea productos reales por:
   - match de componente;
   - producto unitario vs multicomponente;
   - precio/stock;
   - registro sanitario y trazabilidad;
   - etiqueta verificada o inferida;
   - reviews;
   - exposición repetida;
   - diversidad de farmacia;
   - restricciones y safety.
6. Frontend muestra componente sugerido, producto comercial, razones, badges y
   bloqueos.
7. Feedback guarda pack, componentes y productos mostrados/elegidos.

## Flujo crítico

Si el perfil marca renal/hepático/tiroideo, anticoagulantes, embarazo/lactancia,
menor de edad o laboratorio crítico:

```txt
commercial_recommendations_blocked=true
products=[]
CTA compra oculto
```

El frontend puede mostrar componente educativo o alerta, pero no producto
comprable.

## Admin

Vistas esperadas:

- Catálogo:
  - activar/bloquear/preferir producto;
  - ver RS, trazabilidad, unitario/multicomponente;
  - ver flags de restricción verificados/inferidos;
  - ver advertencias de catálogo.
- Moderación:
  - publicar/rechazar reviews;
  - ver spam flags.
- Safety:
  - crear/desactivar reglas por ingrediente, restricción o condición.
- Operación:
  - health;
  - métricas Prometheus;
  - OCR;
  - scraping;
  - Modelo 2;
  - motor comercial.

## Validaciones

Backend:

```bash
cd /home/leo/DPD/Proyecto/Suplematch-Backend
python3 -m pytest tests/unit -q
python3 -m pytest tests/integration -q
python3 scripts/validate_model2_quality.py
python3 scripts/validate_commercial_engine_quality.py
python3 scripts/validate_condition_model_quality.py
python3 scripts/validate_lab_ocr_quality.py
```

Full stack:

```bash
cd /home/leo/DPD/Proyecto
bash scripts/validate_full_stack.sh
```

Staging no destructivo:

```bash
cd /home/leo/DPD/Proyecto/Suplematch-Backend
API_BASE_URL=https://tu-dominio \
ADMIN_TOKEN=token_admin \
bash scripts/ops/validar_staging_controlado.sh
```

Bootstrap admin para staging/demo:

```bash
cd /home/leo/DPD/Proyecto/Suplematch-Backend
DATABASE_URL=postgresql+psycopg://suplematch:suplematch@localhost:5432/suplematch \
ADMIN_EMAIL=admin@suplematch.test \
ADMIN_PASSWORD='cambiar-en-staging' \
python3 scripts/seed_database.py
```

`scripts/ops/sembrar_base.py` es idempotente y tolera carreras de creacion de
usuario: si dos procesos intentan crear el mismo admin, recupera el usuario
existente y asigna el rol.

Validacion local ejecutada:

```txt
alembic current: 20260622_0010 (head)
catalog import: 5868 productos, 191 componentes, 5868 enlaces, 0 errores
tests unit backend: 123 passed
tests integration focalizados: 13 passed
modelo 2 quality: passed
commercial engine quality: passed, 6/6 casos
frontend lint: OK
frontend build: OK
frontend e2e: 6 passed
staging smoke con token admin: staging_validation=ok
```

Validacion operativa agregada:

```txt
smoke_db_limpia: OK
OCR por analito: recall 1.0 en 21 analitos sintéticos representativos
reporte señales reales: generado en data/reports/real_feedback/
compose staging: config OK
compose staging + monitoring: config OK
reportes operativos en contenedor: Modelo 2 OK, motor comercial OK, OCR OK
catálogo enriquecido: 271 productos activos con flags/fuente verificable en PostgreSQL
```

Nota de catálogo semanal:

```txt
VALIDATE_ONLY=1 bash scripts/scraping/run_weekly_supplement_update.sh
```

detectó correctamente que el snapshot local estaba viejo
(`raw_stale_scraped_at_hours`). Eso no es fallo de código: indica que debe
ejecutarse una corrida real de scraping o ampliar el umbral solo para auditoría
histórica.

Comando de suite operativa:

```bash
python scripts/ops/generar_reportes_operativos.py --skip-condition
```

Smoke público contra Cloudflare:

```bash
API_BASE_URL=https://suplematch.lmdemo.com bash scripts/validate_public_staging.sh
```

## Métricas objetivo para demo

- Modelo 2:
  - `top3_accuracy >= 0.80`
  - `block_accuracy == 1.00`
  - `risk_avoidance_accuracy == 1.00`
- Motor comercial:
  - `pass_rate == 1.00`
- Catálogo:
  - productos activos > 0;
  - cobertura RS alta;
  - flags inferidos presentes;
  - flags verificados creciendo progresivamente.
- Feedback:
  - cada evento guarda `recommendation_id`, `pack_id`, componentes y productos
    mostrados/elegidos cuando existan.

## Limitaciones declarables

- No diagnostica.
- No prescribe dosis personalizada.
- No reemplaza evaluación médica.
- Señales blandas de bienestar no disparan compra directa.
- Productos con perfil crítico quedan ocultos hasta revisión profesional.
