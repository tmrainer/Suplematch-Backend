# Cambios por feedback real de usuarios - 2026-06-25

## Encuesta

- Se agrego un paso inicial opcional para subir o revisar examenes de laboratorio antes de responder la encuesta.
- Las explicaciones largas ahora usan "Ver mas" para reducir lectura y scroll.
- Se agrego una leyenda de colores y terminos:
  - Verde: utilizable o trazable.
  - Amarillo: revisar precaucion, etiqueta o dosis.
  - Rojo/bloqueado: no mostrar compra directa sin revision profesional.
  - Penalizado: baja en ranking por precio, trazabilidad, restricciones o ajuste.
- Las preguntas nutricionales pasan a una semana tipica cuando corresponde.
- Proteina diaria queda opcional; si el usuario no la conoce, el backend estima desde alimentos declarados.
- Se separan carnes rojas/visceras, carnes blancas, huevos y opcion de no consumir carnes.
- Lacteos aceptan frecuencia semanal para casos de consumo bajo, por ejemplo una vez por semana.
- Se agregaron senales de hierro/anemia, cafeina por fuente, agua, sudoracion, dolor de cabeza, fatiga por dias/semana y alcohol cuantitativo.

## OCR y laboratorios

- El flujo de examenes ya permite subir PDF/imagen/texto, revisar biomarcadores detectados y corregir valor, unidad o rango.
- Al subir PDF/imagen, la pantalla de verificacion muestra una vista previa del documento original junto a los campos extraidos.
- El flujo sigue funcionando si el usuario no sube examen.

## Packs por presupuesto

- La encuesta permite elegir presupuesto mensual y tamano de pack Top 3 o Top 5.
- El frontend arma combinaciones dentro del presupuesto maximo declarado.
- Los packs evitan productos bloqueados, productos inseguros y combinaciones reportadas como alertas por el motor.
- Cada producto conserva farmacia, precio y link de compra cuando existe.

## Backend

- Se extendio el contrato de encuesta a `2026-06-25.1`.
- Los campos nuevos son opcionales y mantienen compatibilidad con payloads anteriores.
- El feature builder estima proteina si faltan gramos directos y usa nuevas senales para hidratacion, fatiga, cafeina y alcohol.

## Validacion

```bash
cd /home/leo/DPD/Proyecto/Suplematch-Backend
/home/leo/DPD/Proyecto/.venv/bin/python -m pytest \
  tests/unit/test_encuesta_input.py \
  tests/unit/test_recommendation_service.py \
  tests/unit/test_lab_ocr_peru.py -q
```

Resultado: `54 passed`.

```bash
cd /home/leo/DPD/Proyecto/frontend-suplematch
npm run lint
PATH=/home/leo/DPD/Proyecto/.venv/bin:/home/leo/DPD/Proyecto/.venv/src/node-v20.19.0-linux-x64/bin:$PATH npm run build
```

Resultado: lint y build correctos.
