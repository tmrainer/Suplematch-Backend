# Privacidad, consentimiento y seguridad

SupleMatch es una herramienta de orientación nutricional. No diagnostica, no prescribe y no reemplaza evaluación médica, nutricional ni farmacéutica.

## Consentimiento mínimo antes de recomendar

Antes de enviar la encuesta, el usuario debe aceptar que:

- La recomendación es informativa y puede ser incorrecta o incompleta.
- Los suplementos pueden tener contraindicaciones, efectos adversos e interacciones.
- Si declara embarazo, lactancia, minoría de edad, anticoagulantes, enfermedad renal/hepática o medicación crónica, no se deben mostrar productos comerciales para compra directa.
- Sus respuestas pueden guardarse si inicia sesión para mejorar historial, perfil y recomendaciones futuras.
- Las reseñas y feedback pueden usarse como señales agregadas para ranking, moderación y mejora del sistema.

## Datos sensibles

Evitar pedir texto libre de salud en la encuesta principal. Preferir opciones cerradas para:

- Síntomas.
- Suplementos actuales.
- Restricciones y alergias.
- Condiciones de seguridad.
- Presupuesto.

No guardar diagnósticos clínicos detallados. Los resultados de laboratorio son opcionales y requieren consentimiento separado.

Base normativa de referencia para el prototipo peruano:

- Ley N. 29733, Ley de Protección de Datos Personales: la información relacionada con salud debe tratarse como dato sensible.
- Ley N. 29459 y DIGEMID: productos farmacéuticos, dispositivos médicos y productos sanitarios se tratan con registro/control sanitario; el registro informado no equivale a recomendación individual.

Esto no reemplaza revisión legal. Antes de producción pública, validar textos, consentimiento, retención, transferencia y ejercicio de derechos con asesoría especializada.

## Exámenes de laboratorio y OCR

El módulo de exámenes permite:

- Ingreso manual estructurado de biomarcadores.
- Pegado de texto de resultados.
- Upload de PDF o imagen para extracción de texto/OCR.

Reglas obligatorias:

- No interpretar resultados como diagnóstico.
- Mostrar que unidades y rangos varían por laboratorio.
- Guardar solo texto/valores necesarios para el análisis; no usar archivos originales como fuente permanente.
- Bloquear recomendaciones comerciales si hay valores críticos o señales renal/hepática.
- Derivar a revisión profesional para patrones sensibles como ferritina baja + hemoglobina baja.
- Permitir análisis sin cuenta; persistir historial solo si corresponde.
- Permitir exportación y eliminación de datos de salud guardados.

Biomarcadores soportados inicialmente:

- Vitamina D 25-OH.
- Vitamina B12.
- Ferritina.
- Hemoglobina.
- Calcio.
- Magnesio.
- Zinc.
- Creatinina/eGFR.
- AST/ALT.
- Glucosa.

## Retención, exportación y borrado

Endpoints de usuario autenticado:

```txt
GET    /api/v1/labs/me
GET    /api/v1/labs/me/export
DELETE /api/v1/labs/me/{report_id}
DELETE /api/v1/labs/me
```

Reglas:

- El historial solo muestra reportes no eliminados.
- La exportación incluye reportes no eliminados, texto OCR guardado, payload parseado y análisis.
- El borrado elimina el texto OCR y los valores de biomarcadores.
- La fila `lab_reports` queda con `status=deleted` y `deleted_at` para traza técnica mínima.
- No se deben mostrar reportes eliminados ni usarlos para recomendaciones futuras.

## Perfiles críticos

Debe bloquearse la recomendación comercial y mostrar solo guía para conversación profesional cuando exista:

- Menor de 18 años.
- Embarazo o lactancia.
- Enfermedad renal.
- Enfermedad hepática.
- Uso de anticoagulantes.
- Medicación crónica.

## Catálogo comercial

Cada producto debe distinguir:

- Registro sanitario verificado.
- Registro sanitario inferido.
- Componente verificado.
- Componente inferido.
- Restricciones detectadas por texto.
- Restricciones verificadas por metadatos.

Si una restricción no puede verificarse, el frontend debe indicar revisar etiqueta y fuente oficial antes de comprar.

## Reglas de seguridad por ingrediente

El backend mantiene reglas administrables en `ingredient_safety_rules`.

Acciones soportadas:

- `warn`: agrega advertencia y penalización leve.
- `penalize`: baja el ranking del producto.
- `block`: excluye el producto de candidatos comerciales.

Las reglas base se cargan con:

```bash
python scripts/seed_database.py
```

Ejemplos cubiertos:

- Pescado/mariscos si el usuario declara alergia.
- Lácteos/lactosa si declara alergia.
- Soya si declara alergia.
- Gelatina/cápsulas blandas si evita gelatina.
- Vitamina K si usa anticoagulantes.
- Creatina si declara enfermedad renal.
- Retinol/vitamina A si declara embarazo o lactancia.

## Moderación

Las reseñas de suplementos deben pasar por moderación antes de influir plenamente en ranking público. Rechazar:

- Spam.
- Promesas curativas.
- Dosis peligrosas.
- Información médica personal excesiva.
- Comentarios no relacionados al producto unitario.
