# Production readiness

Estado esperado para abrir beta cerrada o produccion controlada.

## 1. Legal y privacidad

- Completar `docs/legal_release_checklist.md`.
- Publicar terminos, privacidad y consentimiento en el dominio final.
- Revisar textos con asesoria legal/local antes de beta publica.

## 2. Safety por ingrediente

- Las reglas base se cargan con `python scripts/ops/sembrar_base.py`.
- Admin puede auditar reglas en `GET /api/v1/admin/safety-rules`.
- Admin puede crear/actualizar reglas en `POST/PATCH /api/v1/admin/safety-rules`.
- Productos con regla `block` no salen en candidatos comerciales.

## 3. Catalogo verificable

- Admin puede revisar calidad en `GET /api/v1/admin/catalog/quality`.
- Cada producto expone `verification_status`, flags verificados/inferidos y fuente de etiqueta.
- Productos con restricciones inferidas deben mostrarse con cautela hasta verificacion manual.

## 4. Moderacion

- Las resenas quedan `pending` o `hidden` si hay spam/riesgo.
- Moderacion crea `admin_actions`.
- `/health/ops` expone backlog pendiente y hidden.

## 5. Observabilidad

- Revisar `/api/v1/health/ready` y `/api/v1/health/ops`.
- Validar Prometheus, Loki y Grafana con `bash scripts/validate_observability_stack.sh`.
- Revisar que `/api/v1/metrics` exponga `suplematch_domain_events_total`.
- Alertar si:
  - `status != ready`.
  - `catalog.products_active == 0`.
  - `safety.active_ingredient_rules == 0`.
  - `reviews.pending >= 100`.
  - `catalog.products_with_registro_sanitario` cae abruptamente.
  - `labs.reports_blocking_commercial_recommendations` sube sin revisión profesional.
  - `labs.ocr_engine_available` es falso en staging si se quiere OCR de imágenes.

## 6. CI/CD

- `Validate full stack` debe pasar en cada push/PR.
- El despliegue staging debe correr solo desde imagen validada.
- No desplegar si frontend build, tests backend o smoke fallan.

## 7. Backups

Instalar backup diario:

```bash
bash scripts/install_backup_cron.sh
```

Probar restore descartable:

```bash
RESTORE_DATABASE=suplematch_restore_test \
CONFIRM_RESTORE=yes \
bash scripts/restore_postgres.sh .backups/postgres/suplematch_latest.dump
```

## 8. Auth/admin

- `JWT_SECRET_KEY` fuerte y por entorno.
- `CORS_ORIGINS` sin `*` en staging/prod.
- Passwords admin/moderador por variables de entorno.
- Registro requiere contrasena con letras y numeros.

## 9. E2E

- Playwright debe cubrir flujos descritos en `/home/leo/DPD/Proyecto/joaquinfront.md`.
- El backend ya tiene smoke full-stack y prueba HTTP de perfil critico.
- Agregar flujo de exámenes:
  - pegar texto de laboratorio
  - subir archivo de ejemplo
  - valor crítico bloquea productos comerciales

## 10. Calidad del recomendador

- Ejecutar `python scripts/validate_model2_quality.py`.
- Revisar `data/reports/supplement_model/01_model2_summary.json`.
- Usar feedback, resenas y exposicion para re-ranking antes de reentrenar.
- Monitorear tasa de perfiles bloqueados, clicks, feedback positivo, diversidad de farmacia y repeticion de producto.
- Usar biomarcadores solo como señales complementarias; nunca como diagnóstico autónomo.

## 11. OCR de laboratorio

- Ejecutar `python scripts/validate_lab_ocr_quality.py`.
- Revisar `data/reports/labs/01_ocr_lab_summary.json`.
- Probar manualmente PDFs/fotos reales anonimizados antes de cualquier demo pública.
- Mantener `commercial_recommendations_blocked=true` para valores críticos o
  señales renal/hepática sensibles.

## 12. Datos de salud por usuario

- Probar `GET /api/v1/users/me/health-data/export`.
- Probar `DELETE /api/v1/users/me/health-data`.
- Confirmar que el borrado afecta solo al usuario autenticado.
- No usar estos endpoints desde pantallas admin salvo flujo explícito de soporte.
