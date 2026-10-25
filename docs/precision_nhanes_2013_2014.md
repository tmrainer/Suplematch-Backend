# Precisión con datos reales: NHANES 2013-2014

Fecha: 2026-10-24. Script: `python scripts/validation/precision_nhanes.py` (mapeo en su docstring). Reporte:
`data/reports/precision_real/precision_nhanes_2013_2014_<fecha>.json`. Primera medición del sistema completo
contra exámenes reales.

**Población**: 2 932 adultos de 20 a 59 años de EE. UU. con el módulo de sol (DEQ_H) y exámenes; descartados por
pregunta obligatoria sin respuesta: fatiga 506, alcohol 399, otros 87. Sin pesos muestrales. Predicción con la
encuesta, sin exámenes, por el mismo camino que `/recommend`. Verdad con los cortes de `biomarkers.csv`.

## Resultados

Precisión = de cada caso marcado, cuántos confirmó el examen. Sensibilidad = de los confirmados, cuántos se marcaron.
La prevalencia es la precisión de marcar a todos.

| Condición | Prevalencia | Sistema (prec / sens) | Solo reglas | Modelo NHANES | AUC reglas | AUC Modelo 1 | AUC NHANES | AUC reglas con pesos aprendidos (CV) |
|---|---|---|---|---|---|---|---|---|
| Vitamina D baja | 35 % | 45 % / 11 % | 45 % / 11 % | **54 % / 29 %** | 0.46 | 0.48 | **0.70** | 0.60 |
| Azúcar alta (HbA1c o glucosa) | 30 % | no marca | no marca | **47 % / 72 %** | 0.67 | 0.56 | **0.77** | 0.67 |
| Colesterol alto o HDL bajo | 48 % | no marca | no marca | 61 % / 12 % | 0.56 | 0.50 | 0.61 | 0.55 |
| Enzimas del hígado altas | 13 % | no marca | no marca | 42 % / 3 % | 0.50 | 0.64 | 0.71 | – |
| Anemia (solo hemoglobina) | 8 % | no marca | no marca | – | 0.63 | 0.57 | – | 0.67 |
| B12 baja (< 200 pg/mL) | 1.5 % | 3 % / 2 % | no marca | – | 0.57 | 0.61 | – | 0.48 |

## Lectura

1. **El Modelo 1 no agrega nada a las reglas**: en vitamina D marca exactamente lo mismo (45 % / 11 %) y su AUC no es
   mejor. Es evidencia para jubilarlo.
2. **El modelo NHANES es la mejor señal donde existe**: vitamina D, azúcar e hígado. Con la encuesta solo, las reglas
   casi nunca marcan azúcar, colesterol ni hígado: hoy esas condiciones dependen de tener examen.
3. **Las reglas de vitamina D apuntan mal (AUC 0.46, peor que el azar)**:

   | Factor (vitamina D < 20 ng/mL) | Con el factor | Sin el factor |
   |---|---|---|
   | Toma suplemento de vitamina D | **15 %** | **44 %** |
   | Poco sol (< 15 min/día al aire libre) | 42 % | 34 % |
   | Protector solar siempre o casi siempre | 23 % | 39 % |
   | Edad 50-59 (sin suplemento) | 41 % | 45 % |
   | Edad 50-59 y poco sol (sin suplemento) | 43 % | 44 % |
   | Piel oscura (afroamericanos, como indicador) | 64 % | 28 % |

   - Las reglas no descuentan a quien ya toma vitamina D, que es el factor más fuerte después del color de piel.
   - La "barrera solar" por usar protector va al revés. Coincide con la literatura: en la práctica, el uso de
     protector no se asocia a déficit.
   - Entre los 50 y 59 años la edad no suma riesgo, ni sola ni con poco sol. **Esto no respalda el cambio
     `DEFICIT_VIT_D edad>=50` 0.12 → 0.25 del 2026-10-24.** NHANES no pregunta sol a mayores de 59, así que no dice
     nada de los mayores de 70, el grupo que NIH ODS señala.
   - El color de piel es el factor más fuerte y la encuesta no lo pregunta.
4. **Aprender los pesos con datos reales ayuda donde las reglas tienen el signo cambiado** (vitamina D: AUC 0.46 →
   0.60; anemia 0.63 → 0.67), pero no supera al modelo NHANES. Son pesos de EE. UU.: propuesta, no reemplazo.
5. **El AUC 0.815 de vitamina D del modelo NHANES no es el de producción.** Se midió con etnia, educación e ingreso,
   que la encuesta no pregunta. Con encuestas como las de SupleMatch da 0.70 en esta población (0.61 si la persona no
   da la dosis de sus suplementos). Reentrenarlo sin esas variables da 0.770 en su test de 2017-2018, pero no mejora
   aquí (0.616 sin dosis), así que no se cambió el modelo servido.

## Aplicado el 2026-10-25 (aprobado por el usuario, pendiente del nutricionista)

1. `DEFICIT_VIT_D edad>=50` vuelve a 0.12.
2. Quien toma vitamina D o un multivitamínico no recibe `DEFICIT_VIT_D` solo por la encuesta; con examen observado
   sí (`SUPPLEMENTS_SUPPRESSING_CONDITION` en `condition_mvp_inference.py`, `suppressed_by_supplement` en el detalle).
   La segunda opinión NHANES no la reactiva.
3. El protector solar deja de contar en `vitamin_d_sun_barrier` (queda piel expuesta: cara y manos); se quita la
   regla `vitamin_d_sun_barrier>=2`, que ya no se puede cumplir. La pregunta de protector sigue en la encuesta pero
   no cambia nada: candidata a retirarse.

Efecto:

| | Antes | Después |
|---|---|---|
| NHANES 2013-2014, vitamina D: precisión / sensibilidad del sistema | 45 % / 11 % | **63 % / 6 %** |
| NHANES, AUC del puntaje de reglas de vitamina D | 0.46 | 0.50 |
| Paquete clínico (120 casos), vitamina D | 25 | 12 (13 casos cambian; nada más cambia) |
| Escenarios de calidad | 16/16 | 16/16 (`mayor_50_activo_sol_bajo` acepta salud ósea, ver comentario) |

Marca menos y acierta más. La sensibilidad sigue baja porque la encuesta no ve el factor más fuerte (color de piel);
el modelo NHANES encuentra 29 % de los casos con 54 % de precisión. El Modelo 1 se reentrenó manteniendo la secuencia
aleatoria del generador; sin eso cambiaban 47 de 120 casos por puro ruido del reentreno.

## Propuestas pendientes

- Evaluar una pregunta opcional de fototipo de piel.
- Usar la estimación NHANES de azúcar (HbA1c) para sugerir el examen, no las reglas.

## Límites

Población de EE. UU. de 20 a 59 años, sin pesos muestrales. La frecuencia de enfermedad y la dieta detallada no
tienen equivalente (quedan en el valor típico y sin responder). Ferritina no se midió en 2013-2014; folato solo en
glóbulos rojos (otro corte), así que ninguno de los dos se evalúa.
