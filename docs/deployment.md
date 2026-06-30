# Despliegue staging SupleMatch

Esta guía asume despliegue con Docker Compose y exposición web mediante Cloudflare Tunnel (`cloudflared`).

## 1. Preparar variables

Desde la raíz del workspace:

```bash
cp .env.staging.example .env.staging
```

Editar obligatoriamente:

- `POSTGRES_PASSWORD`
- `JWT_SECRET_KEY` con 32+ caracteres
- `REFRESH_TOKEN_EXPIRE_DAYS`, por defecto 14
- `CORS_ORIGINS` con el dominio real
- `ADMIN_EMAIL` y `ADMIN_PASSWORD`
- `CLOUDFLARE_TUNNEL_TOKEN`
- `GRAFANA_ADMIN_PASSWORD` si se levanta monitoreo externo

En staging/prod la API falla al iniciar si:

- `JWT_SECRET_KEY` queda con el default local.
- `CORS_ORIGINS` contiene `"*"`.
- `PASSWORD_RESET_RETURN_TOKEN=true`.

## 2. Cloudflare Tunnel

Crear un tunnel remoto en Cloudflare Zero Trust y copiar el token del conector Docker.

El servicio `cloudflared` se levanta desde Docker Compose con el perfil `tunnel` y recibe `TUNNEL_TOKEN` desde `.env.staging`. El token no debe aparecer como argumento del proceso.

Flujo recomendado desde la raíz del workspace:

```bash
bash scripts/start_staging_tunnel.sh
```

El comando Docker entregado por Cloudflare suele tener esta forma:

```bash
docker run cloudflare/cloudflared:latest tunnel --no-autoupdate run --token TOKEN
```

En este proyecto no se usa directamente porque deja el token visible en `ps` y en historiales de shell. Su equivalente seguro es guardar el token en `CLOUDFLARE_TUNNEL_TOKEN` y levantar el servicio `cloudflared` de Compose.

En el dashboard de Cloudflare, configurar dos rutas para el mismo hostname público. La ruta de API debe quedar antes que la ruta raíz:

```txt
hostname: suplematch-stage.tu-dominio.com
path: /api/*
service: http://backend:8000

hostname: suplematch-stage.tu-dominio.com
path: /
service: http://frontend:80
```

El frontend mantiene proxy interno `/api/ -> backend:8000` como fallback/local, pero en staging controlado se prefiere enrutar `/api/*` directo al backend desde Cloudflare. El puerto `FRONTEND_PORT` solo es para acceso directo local al host. El tráfico público entra por Cloudflare Tunnel.

No levantar `ngrok` o `cloudflared` manualmente con tokens en la línea de comandos. Si un token apareció en `ps`, logs o capturas, rotarlo en el proveedor y actualizar `.env.staging`.

Auditar procesos manuales:

```bash
bash scripts/audit_tunnels.sh
```

Cuando el runner Docker ya esté saludable, desactivar el servicio legacy de Debian:

```bash
CONFIRM_DISABLE_LEGACY_CLOUDFLARED=1 bash scripts/disable_legacy_cloudflared_service.sh
```

Si también existen procesos manuales `ngrok` o `cloudflared`, revisarlos con `scripts/audit_tunnels.sh`. Para detener procesos host-level de forma global existe `scripts/stop_manual_tunnels.sh`, pero requiere confirmación explícita porque puede cortar una demo activa. Si un token apareció en `ps`, logs o capturas, rotarlo en el proveedor y actualizar `.env.staging`.

## 3. Levantar staging

```bash
bash scripts/start_staging_tunnel.sh
```

Sin tunnel, para probar localmente:

```bash
docker compose --env-file .env.staging -f docker-compose.staging.yml up -d --build
```

Frontend local:

```txt
http://localhost:${FRONTEND_PORT}
```

En el `.env.staging` local usado para demo, `FRONTEND_PORT=18080`. Si no se define, Compose usa `8080`.

## 4. Startup operativo

El backend ejecuta en su entrypoint:

```bash
alembic upgrade head
python scripts/ops/sembrar_base.py
gunicorn app.main:app -k uvicorn.workers.UvicornWorker
```

El catálogo no se importa automáticamente. Importarlo explícitamente:

```bash
docker compose --env-file .env.staging -f docker-compose.staging.yml exec backend \
  python scripts/catalog/importar_catalogo_postgres.py --catalog data/catalog/approved_catalog.csv
```

## 5. Healthchecks

Health básico:

```bash
curl http://localhost:${FRONTEND_PORT}/api/v1/health
```

Readiness completo:

```bash
curl http://localhost:${FRONTEND_PORT}/api/v1/health/ready
```

Valida:

- conexión DB
- Alembic en `head`
- modelos cargados
- catálogo con productos activos
- módulo de exámenes en DB después de migraciones

## 6. Smoke test

El smoke usa una base aislada `suplematch_test`, la recrea y limpia datos de validación:

```bash
bash scripts/validate_full_stack.sh
```

## 7. CI

El workflow `.github/workflows/validate.yml` ejecuta:

- PostgreSQL 16
- Python 3.12
- Node 20.19
- Alembic
- importación de catálogo
- tests backend
- lint/build frontend
- smoke de persistencia

El workflow `.github/workflows/deploy-staging.yml` permite despliegue manual a staging por SSH, usando secrets del environment `staging`.

## 8. Seguridad mínima aplicada

- CORS restringido por entorno.
- JWT secret obligatorio en staging/prod.
- Auth con refresh tokens rotativos persistidos hasheados.
- `POST /api/v1/auth/refresh` rota refresh tokens y revoca el anterior.
- `POST /api/v1/auth/logout` revoca una sesión.
- `POST /api/v1/auth/logout-all` revoca todas las sesiones del usuario.
- Reset/cambio de contraseña revoca refresh tokens activos.
- Rate limiting in-memory para auth, feedback y reviews.
- Seed admin por variables de entorno.
- Logs estructurados JSON para recomendación, importación y acciones admin.

## 9. Backups y restore

Crear backup desde el host usando el contenedor PostgreSQL:

```bash
bash scripts/backup_postgres.sh
```

Instalar backup diario en cron:

```bash
bash scripts/install_backup_cron.sh
```

Por defecto guarda en:

```txt
.backups/postgres/
```

También actualiza un symlink:

```txt
.backups/postgres/suplematch_latest.dump
```

Restaurar requiere confirmación explícita porque elimina y recrea el schema `public`:

```bash
CONFIRM_RESTORE=yes bash scripts/restore_postgres.sh .backups/postgres/suplematch_latest.dump
```

Validar después del restore:

```bash
curl http://localhost:${FRONTEND_PORT}/api/v1/health/ready
```

Probar restore en una base descartable:

```bash
RESTORE_DATABASE=suplematch_restore_test \
CONFIRM_RESTORE=yes \
bash scripts/restore_postgres.sh .backups/postgres/suplematch_latest.dump
```

Recomendación operativa:

- Backup diario automático en staging/prod.
- Retención local corta, por ejemplo 7 días.
- Copia externa cifrada para producción.
- Probar restore al menos una vez antes de abrir beta.

## 10. Observabilidad

Health de runtime:

```bash
curl http://localhost:${FRONTEND_PORT}/api/v1/health
```

Readiness:

```bash
curl http://localhost:${FRONTEND_PORT}/api/v1/health/ready
```

Métricas operativas agregadas:

```bash
curl http://localhost:${FRONTEND_PORT}/api/v1/health/ops
```

Métricas Prometheus:

```bash
curl http://localhost:${FRONTEND_PORT}/api/v1/metrics
```

Levantar Prometheus y Grafana junto al stack:

```bash
docker compose \
  --env-file .env.staging \
  -f docker-compose.staging.yml \
  -f docker-compose.monitoring.yml \
  up -d --build
```

URLs locales por defecto:

```txt
Prometheus: http://localhost:19090
Grafana:    http://localhost:13000
Loki:       http://localhost:13100
```

Grafana queda aprovisionado con datasource Prometheus, datasource Loki y dashboard `SupleMatch Overview`.

Promtail lee logs de contenedores Docker mediante el socket local, etiqueta por `project`, `service`, `container` y `stream`, y los envía a Loki:

```txt
backend/frontend/postgres -> Docker logs -> Promtail -> Loki -> Grafana Explore
```

Validar Loki:

```bash
curl http://localhost:13100/ready
curl http://localhost:13100/loki/api/v1/labels
```

Validar el stack completo de observabilidad desde el host:

```bash
bash scripts/validate_observability_stack.sh
```

El script valida Prometheus, targets, Loki y Grafana. Loki puede tardar unos
segundos en pasar a `ready`, por eso el validador reintenta antes de fallar.

Consultas útiles en Grafana Explore:

```txt
{service="backend"}
{service="backend"} |= "recommendation"
{service="backend"} |= "login_failed"
{service="cloudflared"}
```

`/health/ops` no devuelve secretos ni datos personales. Expone contadores agregados de catálogo, recomendaciones, feedback, reseñas pendientes, acciones admin e importación de catálogo.

Además expone los reportes operativos más recientes:

- `scraping_validation`: último JSON de validación del catálogo/scraping.
- `model2_quality`: último benchmark del ranker de componentes.
- `commercial_engine_quality`: último benchmark del motor comercial.
- `lab_ocr_quality`: último benchmark OCR por analito.
- `operational_quality`: suite agregada de calidad operativa.
- contadores Prometheus `suplematch_domain_events_total{event,status}` para
  recomendaciones, bloqueos comerciales y análisis de exámenes.

Generar reportes manualmente dentro del backend:

```bash
python scripts/ops/generar_reportes_operativos.py --skip-condition
```

En staging Docker se puede activar al arranque con:

```env
RUN_OPERATIONAL_REPORTS_ON_START=true
```

El script deja logs en `data/reports/operational/` y alimenta `/health/ops`.
Si `scraping_validation.status=failed` por `raw_stale_scraped_at_hours`, no
significa que Modelo 1/2 u OCR fallen; significa que toca ejecutar scraping
real semanal o aceptar un umbral mayor solo para auditoría histórica.

Desde Admin Ops también se puede controlar el job de catálogo:

```txt
GET  /api/v1/admin/catalog/jobs/status
POST /api/v1/admin/catalog/jobs/run
POST /api/v1/admin/catalog/jobs/cancel
POST /api/v1/admin/catalog/jobs/{job_id}/cancel
POST /api/v1/admin/catalog/jobs/{job_id}/approve-import
GET  /api/v1/admin/products/{product_id}/price-snapshots
```

Payload para validar el snapshot actual sin scrapear:

```json
{
  "mode": "validate_only",
  "limit_per_pharmacy": 1000,
  "pharmacies": [],
  "max_raw_age_hours": 168,
  "import_to_postgres": false
}
```

Payload para actualizar precios/stock por scraping real:

```json
{
  "mode": "update_prices",
  "limit_per_pharmacy": 1000,
  "pharmacies": [],
  "max_raw_age_hours": 168,
  "import_to_postgres": false
}
```

Payload para hacer una prueba rápida de precios por farmacia sin tocar el
catálogo aprobado:

```json
{
  "mode": "price_only",
  "limit_per_pharmacy": 20,
  "pharmacies": ["inkafarma"],
  "max_raw_age_hours": 168,
  "import_to_postgres": false
}
```

El job corre en background, usa lock compartido `catalog_update` para evitar
corridas duplicadas, persiste estado en PostgreSQL (`catalog_jobs`) y genera
diff contra el catálogo actual. El flujo recomendado para staging es:

1. Ejecutar `update_prices` con `import_to_postgres=false`.
2. Revisar `diff`: productos nuevos, removidos, cambios de precio y cambios de stock.
3. Aprobar con `POST /api/v1/admin/catalog/jobs/{job_id}/approve-import`.
4. Al aprobar se importa `data/catalog/approved_catalog.csv` y se guardan
   snapshots en `product_price_snapshots`.

`validate_only` y `price_only` nunca deben importar catálogo. La API bloquea
aprobaciones manuales para modos distintos a `update_prices`.

Métricas Prometheus agregadas:

```txt
suplematch_catalog_products_with_verified_restriction_flags
suplematch_catalog_products_with_label_source
suplematch_ingredient_safety_rules_active
suplematch_ocr_engine_available
suplematch_model2_quality_ok
suplematch_commercial_engine_quality_ok
suplematch_lab_ocr_quality_ok
suplematch_scraping_validation_ok
suplematch_operational_quality_ok
```

## 11. Datos personales de usuario

La persistencia de usuario queda separada por propósito:

- `users`: autenticación, email, estado, roles y nombre visible.
- `user_personal_info`: datos personales identificables, 1:1 con `users`, `ON DELETE CASCADE`.
- `user_profiles`: edad, peso normalizado, preferencias, encuesta enriquecida, restricciones, suplementos actuales y contexto de salud.
- `lab_reports`: datos de laboratorio, siempre filtrados por `user_id` en endpoints `/labs/me`.
- `recommendation_sessions`: historial de recomendaciones, filtrado por `user_id` en `/history`.

Endpoints de cuenta:

```bash
GET    /api/v1/users/me
GET    /api/v1/users/me/personal
PUT    /api/v1/users/me/personal
DELETE /api/v1/users/me/personal
PUT    /api/v1/users/me/profile
```

La migración `20260615_0008` crea `user_personal_info`.
La migración `20260615_0009` agrega `age_years`, `weight_value`, `weight_unit` y `weight_kg` a `user_profiles`.

La encuesta de recomendacion debe enviar datos exactos cuando esten disponibles:

- `age_years`
- `weight_value` + `weight_unit`
- `height_value` + `height_unit`
- derivados opcionales: `weight_kg`, `height_cm`, `bmi`, `edad_rango`, `peso_rango`, `talla_rango`

Si los derivados no llegan, backend los recalcula. Si llegan datos exactos, tienen prioridad sobre los rangos legacy.

Payload obligatorio de registro:

```json
{
  "email": "ana@suplematch.test",
  "password": "Initial123",
  "first_name": "Ana",
  "last_name": "Lopez",
  "age": 25,
  "weight_value": 154,
  "weight_unit": "lb"
}
```

Unidades de peso soportadas por backend: `kg`, `g`, `lb`, `lbs`, `libras`, `oz`, `stone`. El API guarda la unidad original normalizada y `weight_kg`.

Unidades de talla soportadas por backend: `cm`, `m`, `in`, `ft`, `pies`, `pulgadas`. El API normaliza a `height_cm`.

Alertar si:

- `ready` pasa a `degraded`.
- `catalog.products_active` queda en 0.
- `models_loaded` es falso.
- `suplematch_ocr_engine_available` queda en 0.
- `suplematch_model2_quality_ok`, `suplematch_commercial_engine_quality_ok` o
  `suplematch_lab_ocr_quality_ok` quedan en 0.
- `reviews.pending` crece sin moderación.
- No hay importación de catálogo reciente.
- `safety.active_ingredient_rules` queda en 0.

## 12. Admin de safety y catálogo

Reglas de seguridad por ingrediente:

```bash
curl http://localhost:${FRONTEND_PORT}/api/v1/admin/safety-rules
```

Calidad de catálogo:

```bash
curl http://localhost:${FRONTEND_PORT}/api/v1/admin/catalog/quality
```

Estos endpoints requieren token admin.

## 13. Exámenes de laboratorio y OCR

Endpoints:

```bash
POST /api/v1/labs/manual
POST /api/v1/labs/text
POST /api/v1/labs/upload
GET  /api/v1/labs/me
GET  /api/v1/labs/me/export
DELETE /api/v1/labs/me/{report_id}
DELETE /api/v1/labs/me
```

`/labs/upload` acepta texto, PDF e imágenes. En Docker se instala:

- `tesseract-ocr`
- `tesseract-ocr-spa`
- `poppler-utils`
- `pytesseract`
- `pypdf`
- `pdf2image`

Flujo OCR:

- PDF con texto embebido: `pypdf`.
- PDF escaneado: `pdf2image + poppler + Tesseract`.
- Imagen: `Pillow + Tesseract` con preprocesamiento de escala, contraste y umbral.
- Tesseract usa `OCR_GUIDE_WORDS` como diccionario de biomarcadores/unidades/etiquetas esperadas.
- El parser extrae valores desde ventanas cercanas a keywords de examen y tolera errores OCR comunes como `1/I`, `0/O`, `5/S`.
- Si una lectura tiene baja confianza, el API devuelve advertencia para confirmar valor, unidad y rango.
- Si hay valores criticos o señales renal/hepatica, `commercial_recommendations_blocked=true` y no se devuelven productos comerciales.

Si Tesseract no está disponible, el sistema mantiene análisis manual/texto y reporta `labs.ocr_engine_available=false` en `/health/ops`.

Privacidad operativa:

- `GET /labs/me/export` entrega los reportes no eliminados del usuario autenticado.
- `DELETE /labs/me/{report_id}` elimina texto OCR y biomarcadores de un reporte.
- `DELETE /labs/me` elimina texto OCR y biomarcadores de todos los reportes del usuario.
- El borrado deja una traza mínima con `status=deleted` para auditoría técnica, sin valores clínicos.

Recuperación/cambio de contraseña:

```bash
POST /api/v1/auth/forgot-password
POST /api/v1/auth/reset-password
POST /api/v1/auth/change-password
```

En local/demo se puede activar `PASSWORD_RESET_RETURN_TOKEN=true` para mostrar el token de reset. En staging/prod debe estar desactivado y conectarse a un proveedor de email.

Variables SMTP opcionales:

```env
PUBLIC_FRONTEND_URL=https://tu-dominio
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=usuario
SMTP_PASSWORD=secreto
SMTP_FROM_EMAIL=no-reply@tu-dominio
SMTP_USE_TLS=true
```

Si SMTP no está configurado y `PASSWORD_RESET_RETURN_TOKEN=false`, el endpoint responde de forma neutra pero no entrega el token al usuario. Esto es correcto para no filtrar cuentas, pero debe completarse antes de producción pública.

Exportación y borrado consolidado de datos de salud del usuario:

```bash
GET    /api/v1/users/me/health-data/export
DELETE /api/v1/users/me/health-data
```

Incluye perfil de salud, datos personales, reportes de laboratorio y snapshots
de recomendaciones. El borrado elimina o anonimiza señales sensibles de perfil,
reportes OCR y datos personales del usuario autenticado sin tocar otros
usuarios.

Validación de OCR con casos sintéticos realistas:

```bash
python scripts/validate_lab_ocr_quality.py
```

Genera:

```txt
data/reports/labs/01_ocr_lab_case_details.csv
data/reports/labs/01_ocr_lab_summary.json
```

Esta prueba no reemplaza PDFs/fotos reales de laboratorios, pero mantiene un
benchmark fijo para detectar regresiones en keywords, unidades, valores y
bloqueos críticos.

## 14. Privacidad y safety

Ver [privacy_and_safety.md](privacy_and_safety.md).
Ver tambien [legal_release_checklist.md](legal_release_checklist.md) y [production_readiness.md](production_readiness.md).

Antes de beta pública:

- Publicar términos y privacidad reales en el dominio.
- Mostrar consentimiento explícito antes de generar recomendaciones.
- Mantener bloqueo comercial para perfiles críticos.
- Evitar lenguaje de diagnóstico o promesa terapéutica.

## 15. Staging real con frontend Docker y Cloudflare Tunnel

Arquitectura aplicada:

```txt
Cloudflare Public Hostname /api/* -> cloudflared -> backend:8000 -> postgres:5432
Cloudflare Public Hostname /      -> cloudflared -> frontend:80
```

El backend no publica puertos del host. Solo es alcanzable desde la red Docker y desde `cloudflared`. El frontend Nginx mantiene un proxy `/api/` al backend para pruebas locales/fallback, pero la ruta recomendada en Cloudflare para staging es `/api/* -> http://backend:8000`.

Levantar staging sin túnel público:

```bash
cd /home/leo/DPD/Proyecto
docker compose --env-file .env.staging -f docker-compose.staging.yml up -d --build
```

Levantar staging con túnel:

```bash
cd /home/leo/DPD/Proyecto
bash scripts/start_staging_tunnel.sh
```

El token de Cloudflare va solo en `.env.staging`:

```env
CLOUDFLARE_TUNNEL_TOKEN=...
```

No usar:

```bash
docker run cloudflare/cloudflared:latest tunnel --no-autoupdate run --token TOKEN
```

Ese formato deja el token visible en historial/`ps`. El compose usa variable de
entorno dentro del contenedor.

Rutas requeridas en Cloudflare Zero Trust:

```txt
hostname: tu-dominio-publico
path: /api/*
service: http://backend:8000

hostname: tu-dominio-publico
path: /
service: http://frontend:80
```

La ruta `/api/*` debe evaluarse antes que `/`.

Validar dominio público:

```bash
cd /home/leo/DPD/Proyecto/Suplematch-Backend
API_BASE_URL=https://tu-dominio-publico \
ADMIN_TOKEN=token_admin \
bash scripts/ops/validar_staging_controlado.sh
```

Smoke funcional completo contra staging público:

```bash
cd /home/leo/DPD/Proyecto
python3 - <<'PY'
import os
import subprocess
from pathlib import Path

root = Path("/home/leo/DPD/Proyecto")
values = {}
for line in (root / ".env.staging").read_text(errors="ignore").splitlines():
    if line and not line.lstrip().startswith("#") and "=" in line:
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()

env = os.environ.copy()
env["API_BASE_URL"] = "https://suplematch.lmdemo.com"
env["ADMIN_EMAIL"] = values["ADMIN_EMAIL"]
env["ADMIN_PASSWORD"] = values["ADMIN_PASSWORD"]
subprocess.run(
    ["python3", "scripts/ops/validar_staging_flujo_completo.py"],
    cwd=root / "Suplematch-Backend",
    env=env,
    check=True,
)
PY
```

## 16. Smoke completo en DB limpia

Este smoke crea una base descartable, corre Alembic desde cero, importa
catálogo, crea admin, levanta una API temporal y prueba por HTTP:

- health/readiness;
- login admin;
- registro usuario;
- catálogo admin;
- recomendación;
- feedback;
- review unitaria;
- OCR/texto de laboratorio;
- ops/metrics.

Comando:

```bash
cd /home/leo/DPD/Proyecto/Suplematch-Backend
bash scripts/ops/smoke_db_limpia.sh
```

El script usa automáticamente `/home/leo/DPD/Proyecto/.venv/bin/python` si existe.
- recomendación;
- feedback con producto elegido;
- review unitaria;
- examen de laboratorio por texto/OCR parser;
- `/health/ops`;
- `/metrics`.

Comando:

```bash
cd /home/leo/DPD/Proyecto/Suplematch-Backend
PYTHON_BIN=/home/leo/DPD/Proyecto/.venv/bin/python \
bash scripts/ops/smoke_db_limpia.sh
```

Resultado esperado:

```txt
smoke_db_limpia=ok db=suplematch_smoke_...
```

Por defecto elimina la DB al terminar. Para conservarla:

```bash
KEEP_SMOKE_DB=1 bash scripts/ops/smoke_db_limpia.sh
```

## 17. Observabilidad externa

Levantar Prometheus, Grafana, Loki y Promtail junto a staging:

```bash
cd /home/leo/DPD/Proyecto
docker compose \
  --env-file .env.staging \
  -f docker-compose.staging.yml \
  -f docker-compose.monitoring.yml \
  up -d --build
```

Dashboards incluidos:

- `SupleMatch Overview`: requests, latencia, uptime.
- `SupleMatch Operations`: API, errores, catálogo, recomendaciones, feedback,
  reviews pendientes, exámenes y logs operativos.

Métricas agregadas nuevas:

```txt
suplematch_catalog_products_active
suplematch_catalog_products_available
suplematch_recommendation_sessions_total
suplematch_feedback_events_total
suplematch_reviews_pending
suplematch_lab_reports_total
suplematch_domain_events_total
```

Loki recibe logs Docker de `backend`, `frontend`, `postgres`, `cloudflared` y
jobs si se levantan en el mismo proyecto compose.

## 18. Worker semanal de catálogo

Levantar el worker semanal dentro de staging:

```bash
cd /home/leo/DPD/Proyecto
docker compose --env-file .env.staging -f docker-compose.staging.yml --profile jobs up -d catalog-weekly
```

Variables:

```env
CATALOG_WEEKLY_INTERVAL_SECONDS=604800
CATALOG_WEEKLY_RUN_ON_START=false
```

Con `CATALOG_WEEKLY_RUN_ON_START=true`, el scraper empieza apenas arranca el
contenedor. Si está en `false`, espera el intervalo antes de la primera corrida.

Cada corrida deja:

```txt
data/reports/scraping/catalog_pipeline_current_report.json
data/reports/scraping/catalog_pipeline_alert.json
data/reports/scraping/weekly_catalog_validation_*.json
```

`/health/ops` expone `scraping_validation` y `scraping_alert`.

## 19. Señales reales para validación

Reporte periódico:

```bash
cd /home/leo/DPD/Proyecto/Suplematch-Backend
DATABASE_URL=postgresql+psycopg://... \
python scripts/ops/evaluar_senales_reales.py
```

Salidas:

```txt
data/reports/real_feedback/real_feedback_summary.json
data/reports/real_feedback/real_feedback_conditions.csv
```

Mide:

- sesiones y condiciones observadas;
- cobertura comercial de packs;
- cobertura de `commercial_score`;
- feedback con contexto de productos;
- productos elegidos;
- reviews unitarias;
- backlog de moderación.

Este reporte no reentrena modelos automáticamente. Sirve para decidir cuándo ya
hay suficiente feedback real para calibrar ranking o preparar reentrenamiento.
