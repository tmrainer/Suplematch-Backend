# Checklist legal para beta publica

SupleMatch no debe publicarse sin reemplazar los textos placeholder por documentos revisados para Peru y para el canal comercial real.

## Textos obligatorios

- Terminos y condiciones.
- Politica de privacidad.
- Consentimiento informado antes de generar recomendaciones.
- Disclaimer visible en resultados.
- Politica de moderacion de resenas.
- Canal de contacto para ejercer derechos ARCO o solicitud equivalente.

## Reglas de producto

- No usar lenguaje de diagnostico, cura, tratamiento o promesa terapeutica.
- No sugerir dosis como receta individual.
- Bloquear compra/recomendacion comercial en perfiles criticos.
- Diferenciar componente recomendado de producto comercial disponible.
- Mostrar cuando una etiqueta o restriccion fue inferida y no verificada.

## Datos personales

- Evitar texto libre de salud salvo que sea estrictamente necesario.
- No pedir diagnosticos clinicos detallados ni resultados de laboratorio en la encuesta base.
- Guardar solo lo necesario para historial, perfil y mejora de ranking.
- No exponer email, tokens, IPs ni datos sensibles en logs.

## Resenas

- Moderar antes de publicar.
- Rechazar spam, datos personales, promesas curativas y recomendaciones de dosis peligrosas.
- Las resenas deben corresponder a suplemento unitario, no al pack completo.

## Evidencia antes de beta

- `bash scripts/validate_full_stack.sh` pasa.
- Restore probado en DB descartable.
- `/api/v1/health/ready` en estado `ready`.
- `/api/v1/health/ops` sin alertas criticas.
- Tokens rotados y tuneles manuales detenidos.
