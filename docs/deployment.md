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

El servicio `cloudflared` se levanta desde Docker Compose con el perfil `tunnel` y recibe `TUNNEL_TOKEN` desde `.env.staging`. El token no debe aparecer como argumento del proceso:

```bash
docker compose --env-file .env.staging -f docker-compose.staging.yml --profile tunnel up -d cloudflared
```

El comando Docker entregado por Cloudflare suele tener esta forma:

```bash
docker run cloudflare/cloudflared:latest tunnel --no-autoupdate run --token TOKEN
```

En este proyecto no se usa directamente porque deja el token visible en `ps` y en historiales de shell. Su equivalente seguro es guardar el token en `CLOUDFLARE_TUNNEL_TOKEN` y levantar el servicio `cloudflared` de Compose.

En el dashboard de Cloudflare, configurar el hostname público para enrutar al servicio interno:

```txt
http://frontend:80
```

El puerto `FRONTEND_PORT` solo es para acceso directo local al host. El tráfico público entra por Cloudflare Tunnel.

No levantar `ngrok` o `cloudflared` manualmente con tokens en la línea de comandos. Si un token apareció en `ps`, logs o capturas, rotarlo en el proveedor y actualizar `.env.staging`.

Auditar procesos manuales:

```bash
ps -eo pid,user,comm,args | rg 'cloudflared|ngrok'
```

Intentar detenerlos:

```bash
bash scripts/stop_manual_tunnels.sh
```

Si pertenecen a otro usuario, detenerlos con el usuario propietario o `sudo`, y rotar cualquier token expuesto.

## 3. Levantar staging

```bash
docker compose --env-file .env.staging -f docker-compose.staging.yml --profile tunnel up -d --build
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
python scripts/seed_database.py
gunicorn app.main:app -k uvicorn.workers.UvicornWorker
```

El catálogo no se importa automáticamente. Importarlo explícitamente:

```bash
docker compose --env-file .env.staging -f docker-compose.staging.yml exec backend \
  python scripts/import_catalog_to_postgres.py --catalog data/catalog/approved_catalog.csv
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

Consultas útiles en Grafana Explore:

```txt
{service="backend"}
{service="backend"} |= "recommendation"
{service="backend"} |= "login_failed"
{service="cloudflared"}
```

`/health/ops` no devuelve secretos ni datos personales. Expone contadores agregados de catálogo, recomendaciones, feedback, reseñas pendientes, acciones admin e importación de catálogo.

Alertar si:

- `ready` pasa a `degraded`.
- `catalog.products_active` queda en 0.
- `models_loaded` es falso.
- `reviews.pending` crece sin moderación.
- No hay importación de catálogo reciente.
- `safety.active_ingredient_rules` queda en 0.

## 11. Admin de safety y catálogo

Reglas de seguridad por ingrediente:

```bash
curl http://localhost:${FRONTEND_PORT}/api/v1/admin/safety-rules
```

Calidad de catálogo:

```bash
curl http://localhost:${FRONTEND_PORT}/api/v1/admin/catalog/quality
```

Estos endpoints requieren token admin.

## 12. Exámenes de laboratorio y OCR

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
- `pytesseract`
- `pypdf`

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

## 13. Privacidad y safety

Ver [privacy_and_safety.md](privacy_and_safety.md).
Ver tambien [legal_release_checklist.md](legal_release_checklist.md) y [production_readiness.md](production_readiness.md).

Antes de beta pública:

- Publicar términos y privacidad reales en el dominio.
- Mostrar consentimiento explícito antes de generar recomendaciones.
- Mantener bloqueo comercial para perfiles críticos.
- Evitar lenguaje de diagnóstico o promesa terapéutica.
