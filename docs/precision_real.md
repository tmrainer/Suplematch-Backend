# Precisión real (encuesta contra examen)

Fecha: 2026-10-24. Código: `app/ml/evaluation/precision_real.py` (métricas, puro) y `app/ml/evaluation/pares_reales.py`
(pares desde Postgres). Script: `python scripts/validation/precision_real.py`.

## Qué mide

Para cada persona que dio un examen y respondió la encuesta: ¿lo que el sistema estima **solo con la encuesta**
coincide con lo que el examen confirma? Es la única medida de precisión con datos reales y peruanos; el Modelo 1 se
entrena con datos sintéticos y NHANES es de EE. UU.

- **Verdad**: examen fuera de rango según `biomarkers.csv`, en la dirección de la condición (`TRUTH_BIOMARKERS`:
  vitamina D baja, HbA1c o glucosa alta, HDL bajo, TSH alta o baja, etc.). `borderline` no cuenta como déficit.
  Solo se evalúan condiciones que un examen define; sueño, energía o defensas no.
- **Predicción**: la misma encuesta **sin los exámenes**, por el mismo camino que `/recommend`
  (`build_pipeline_input`). Tres variantes:
  - `sistema`: lo que se sirve hoy (Modelo 1 + reglas + segunda opinión NHANES);
  - `reglas`: solo reglas (umbral + dos familias) + segunda opinión NHANES, la alternativa para jubilar el Modelo 1;
  - `nhanes`: solo el modelo real, en las condiciones que estima.
- **Métricas por condición**: prevalencia (la precisión de marcar a todos, la línea base), precisión ("de cada caso
  que marcamos, cuántos confirmó el examen"), sensibilidad ("de los confirmados, cuántos marcamos") y especificidad,
  con intervalo de Wilson al 95 %. Con menos de 10 casos marcados o 10 positivos la celda sale marcada con `*`.

## De dónde salen los pares

1. **Exámenes dentro de la encuesta** (`lab_results` en `recommendation_sessions`).
2. **Exámenes subidos aparte** (`lab_reports` con consentimiento y sin borrar), emparejados con la encuesta del mismo
   usuario más cercana en el tiempo dentro de 90 días (`--window-days`).

Un par por persona (el más reciente); las sesiones anónimas cuentan cada una como persona. Los descartes se cuentan
por motivo (`encuesta_invalida`, `examen_sin_encuesta_cercana`, `examen_sin_condicion_evaluable`).

## Privacidad

El reporte solo tiene conteos y métricas agregadas, dentro de la finalidad "métricas agregadas del prototipo" del
aviso de privacidad (`Legal.jsx`). **Entrenar un modelo con estos pares es otra finalidad**: requiere un
consentimiento aparte (opt-in) y su texto legal antes de exportar datos individuales.

## Siguiente paso

Cuando una condición tenga celdas suficientes, comparar `sistema` contra `reglas`: si la precisión y la sensibilidad
de `reglas` no son peores, el Modelo 1 se puede jubilar con evidencia. Con varios cientos de positivos por condición,
entrenar pesos de reglas con datos reales (regresión logística calibrada sobre las mismas reglas como variables).
Tests: `tests/unit/test_precision_real.py`, `tests/integration/test_precision_real_pairs.py`.
