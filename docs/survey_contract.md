# Contrato de encuesta SupleMatch

Este contrato define el payload aceptado por `POST /api/v1/recommend` y debe mantenerse alineado con `frontend-suplematch/src/screens/Encuesta.jsx` y `app/domains/survey/esquemas_encuesta.py`.

La encuesta usa datos exactos cuando aportan precision (`edad`, `peso`, `talla`) y valores cerrados para sintomas, habitos, restricciones y seguridad. No se aceptan textos libres de salud en la encuesta base para evitar ambiguedad, contradicciones y mala interpretacion del sistema.

Desde la persistencia por cuenta, `POST /api/v1/recommend` requiere `Authorization: Bearer <token>`. Las evaluaciones nuevas deben quedar asociadas a un usuario autenticado; el frontend puede conservar un borrador local temporal de encuesta, pero no debe presentar historial local como historial de cuenta.

## Registro y perfil base

`POST /api/v1/auth/register` requiere datos mínimos para crear perfil reutilizable:

| Campo | Reglas |
| --- | --- |
| `email` | Email de cuenta |
| `password` | 8-128 caracteres, letras y números |
| `first_name`, `last_name` | Obligatorios |
| `age` | Entero 1-120 |
| `weight_value` + `weight_unit` | Peso positivo; unidades soportadas por backend: `kg`, `g`, `lb`, `oz`, `st` |
| `height_value` + `height_unit` | Estatura positiva; unidades soportadas por backend: `cm`, `m`, `in`, `ft` |

La app mobile puede ofrecer `cm` o `ft + in`; si usa `ft + in`, debe convertir a `cm` antes de enviar o convertir a una unidad soportada por backend.

## Datos exactos recomendados

El frontend debe pedir estos campos al inicio de la encuesta:

| Campo | Reglas | Derivado backend |
| --- | --- | --- |
| `age_years` | Entero 0-120 | `edad_rango` |
| `weight_value` + `weight_unit` | Peso positivo en `kg` o `lb`; el frontend convierte a `weight_kg` | `weight_kg`, `peso_rango` |
| `height_value` + `height_unit` | El backend recibe talla positiva en `cm`. La UI puede pedir `cm` o `ft + in`, pero `ft + in` se convierte a centímetros antes de enviar | `height_cm`, `talla_rango` |
| `bmi` | Opcional. Si no llega, backend lo calcula con `weight_kg` y `height_cm` | Senal contextual interna, no mostrar al usuario |

Rangos razonables aplicados por backend:

- `weight_kg`: 2 a 500 kg.
- `height_cm`: 40 a 260 cm.

Los rangos legacy (`edad_rango`, `peso_rango`, `talla_rango`) siguen aceptandose para compatibilidad, pero si llegan datos exactos el backend los recalcula y los usa para el modelo.

## Campos base requeridos

| Campo | Valores |
| --- | --- |
| `edad_rango` | `menos_18`, `18_30`, `31_50`, `mas_50` |
| `horas_sueno` | `menos_5h`, `5_7h`, `7_9h`, `mas_9h` |
| `frecuencia_ejercicio` | `casi_nunca`, `1_2_semana`, `3_4_semana`, `diario` |
| `dieta` | `poco_variada`, `regular`, `bastante_variada`, `muy_balanceada` |
| `fatiga` | `siempre`, `a_menudo`, `a_veces`, `casi_nunca` |
| `exposicion_solar` | `menos_15min`, `15_30min`, `30_60min`, `mas_1h` |
| `frecuencia_enfermedad` | `muy_seguido`, `3_4_anio`, `1_2_anio`, `casi_nunca` |
| `estres` | `muy_alto`, `alto`, `moderado`, `bajo` |
| `alcohol` | `frecuente`, `ocasional`, `raro`, `nunca` |

## Campos extendidos

| Campo | Valores | Default backend |
| --- | --- | --- |
| `sexo` | `femenino`, `masculino`, `prefiero_no_decir` | `prefiero_no_decir` |
| `tipo_dieta` | `omnivoro`, `pescetariano`, `vegetariano`, `vegano` | `omnivoro` |
| `dolor_muscular` | `nunca`, `leve`, `moderado`, `frecuente`, `severo` | `nunca` |
| `dolor_articular` | `nunca`, `leve`, `moderado`, `frecuente`, `severo` | `nunca` |
| `niebla_mental` | `nunca`, `leve`, `moderado`, `frecuente`, `severo` | `nunca` |
| `caida_cabello` | `nunca`, `leve`, `moderado`, `frecuente`, `severo` | `nunca` |
| `piel_seca` | `nunca`, `leve`, `moderado`, `frecuente`, `severo` | `nunca` |
| `unas_quebradizas` | `nunca`, `leve`, `moderado`, `frecuente`, `severo` | `nunca` |
| `calambres` | `nunca`, `leve`, `moderado`, `frecuente`, `severo` | `nunca` |
| `objetivo_principal` | `energia`, `inmunidad`, `suenio_estres`, `rendimiento`, `salud_osea`, `cabello_piel_unas`, `nutricion_general` | `null` |
| `presupuesto` | `bajo`, `medio`, `alto`, `sin_preferencia` | `null` |
| `presupuesto_min`, `presupuesto_max` | Numeros en soles, 0-2000 | `null` |

## Campos optimizados recomendados

Estos campos son opcionales para compatibilidad, pero son los recomendados para la encuesta final porque mejoran el modelo sin hacer demasiadas preguntas ni aceptar texto libre.

### Alimentacion medible

| Campo | Tipo | Descripcion corta para frontend |
| --- | --- | --- |
| `fish_servings_week` | Numero 0-21 | Porciones de pescado o mariscos por semana. Una porcion equivale aprox. a una palma de mano. |
| `dairy_servings_day` | Numero 0-10 | Porciones de leche, yogurt, queso o bebidas fortificadas por dia. |
| `legume_servings_week` | Numero 0-21 | Porciones de menestras o legumbres por semana. Incluye lentejas, frejoles, garbanzos, pallares. |
| `meat_servings_week` | Numero 0-21 | Porciones de carne, pollo, pescado o visceras por semana. No incluye huevos. |
| `fruit_veg_servings_day` | Numero 0-20 | Porciones de frutas y verduras por dia. Una fruta mediana o media taza cuenta como una porcion. |
| `protein_g_day_estimate` | Numero 0-300 | Proteina diaria aproximada si el usuario la conoce. Si no la conoce, no pedir texto libre. |

Backend guarda los faltantes como `unknown`, no como cero. Esto evita interpretar "no respondio" como "no consume".

### Sueno y estres

| Campo | Valores | Descripcion corta |
| --- | --- | --- |
| `sleep_quality` | `buena`, `regular`, `mala` | Como percibe la calidad del sueno en las ultimas dos semanas. |
| `night_wakeups` | `nunca`, `1_2`, `3_o_mas` | Cuantas veces suele despertarse durante la noche. |
| `caffeine_after_3pm` | `no`, `a_veces`, `si` | Si consume cafe, energizantes o pre-entreno despues de las 3 p.m. |

### Entrenamiento y recuperacion

| Campo | Valores | Descripcion corta |
| --- | --- | --- |
| `exercise_days_week` | Entero 0-7 | Dias de ejercicio o entrenamiento por semana. |
| `training_type` | `no_aplica`, `fuerza`, `cardio`, `mixto`, `movilidad` | Tipo principal de entrenamiento. Si `exercise_days_week` es 0, debe ser `no_aplica` o omitirse. |
| `recovery_difficulty` | `no`, `leve`, `moderada`, `alta` | Dificultad para recuperarse despues de entrenar o actividad fisica. |

### Suplementos actuales

| Campo | Valores | Regla |
| --- | --- | --- |
| `suplementos_frecuencia` | `diario`, `varias_semana`, `ocasional`, `no_se` | Solo aplica si `toma_suplementos == "si"`. |
| `suplementos_dosis_conocida` | Booleano | `true` si el usuario conoce la dosis de lo que toma. No pedir dosis como texto libre en encuesta base. |

## Listas cerradas

### `objetivos`

Lista opcional, maximo 4 valores:

- `energia`
- `inmunidad`
- `suenio`
- `rendimiento`
- `salud_osea`
- `cabello_piel_unas`
- `estres`

### `toma_suplementos` y `suplementos_actuales`

`toma_suplementos` acepta `no` o `si`.

Si `toma_suplementos == "si"`, `suplementos_actuales` es obligatorio y debe incluir al menos uno:

- `vitamina_d`
- `calcio`
- `magnesio`
- `zinc`
- `vitamina_c`
- `hierro`
- `omega_3`
- `multivitaminico`
- `proteina`
- `otro`

Si `toma_suplementos == "no"`, `suplementos_actuales` debe ser una lista vacia.

### `restricciones`

Lista opcional:

- `sin_restricciones`
- `alergia_lacteos`
- `alergia_soya`
- `alergia_pescado_mariscos`
- `evita_gelatina`
- `sin_gluten`

Regla: `sin_restricciones` es excluyente y no puede combinarse con otras restricciones.

### `condiciones_seguridad`

Lista opcional:

- `ninguna`
- `embarazo_lactancia`
- `enfermedad_renal`
- `enfermedad_hepatica`
- `problema_tiroideo`
- `anticoagulantes`
- `medicacion_cronica`

Reglas:

- `ninguna` es excluyente y no puede combinarse con otras condiciones.
- `embarazo_lactancia` no puede combinarse con `sexo == "masculino"`.
- Cualquier condicion distinta de `ninguna` debe generar advertencias visibles en `profile_warnings`.
- `enfermedad_renal`, `enfermedad_hepatica`, `embarazo_lactancia` y minoría de edad bloquean recomendaciones comerciales directas hasta revision profesional.
- `problema_tiroideo`, `anticoagulantes` y `medicacion_cronica` activan `safety_level=caution`: se muestran alertas y se bloquean o penalizan productos específicos por ingrediente, pero no se oculta todo el catálogo comercial.

## Efecto en features del modelo

`FeatureBuilder` traduce la encuesta extendida a las features esperadas por el pipeline actual:

- `tipo_dieta == vegano|vegetariano` aumenta riesgo dietario.
- sintomas especificos alimentan `dolor_muscular`, `dolor_articular`, `niebla_mental`, `caida_cabello`, `piel_seca`, `unas_quebradizas`, `calambres`.
- `objetivos` activa metas (`meta_energia`, `meta_inmunidad`, `meta_belleza`, `meta_rendimiento`, `meta_salud_osea`, `meta_cognitivo`).
- `age_years`, `weight_kg` y `height_cm` tienen prioridad sobre los rangos legacy en features numericas.
- `presupuesto` o `presupuesto_min/max` no cambia la condicion estimada; solo ajusta ranking comercial de productos.
- `suplementos_actuales`, `restricciones` y `condiciones_seguridad` generan advertencias y penalizaciones comerciales cuando aplique.
- `bmi` puede guardarse y usarse como senal interna, pero no debe mostrarse en la encuesta ni en el resumen de respuestas.
- porciones dietarias generan estados cerrados para `benchmark_diet_b12_status`, `benchmark_diet_vitamin_c_status`, `benchmark_diet_zinc_status`, `benchmark_diet_magnesium_status`, `benchmark_diet_calcium_status`, `benchmark_diet_folate_status`, `benchmark_diet_protein_status` y `benchmark_diet_omega3_status`.
- campos faltantes de alimentacion se guardan como `unknown`; el modelo no debe forzar una conclusion por ausencia de respuesta.
- sueno, cafeina tardia y recuperacion ajustan prioridades de bienestar, no diagnosticos.

## Respuesta separada para frontend

`POST /api/v1/recommend` mantiene los campos historicos (`conditions`, `conditions_display`, `recommendations`, `packs_ranked`) y agrega tres listas para evitar confundir diagnostico, bienestar y seguridad:

| Campo | Uso en UI |
| --- | --- |
| `condition_results` | Riesgos nutricionales o biomedicos estimados. Pueden venir de encuesta, dieta o laboratorio. Mostrar como "riesgo estimado", no como diagnostico. |
| `wellness_priorities` | Prioridades blandas por encuesta, como sueno/estres, rendimiento, inmunidad o cabello/piel/unas. No se validan con NHANES; se deben validar con casos golden de encuesta. |
| `safety_flags` | Alertas que bloquean o limitan recomendaciones comerciales. Deben mostrarse antes de productos. |

Cada elemento incluye:

- `code`
- `display_name`
- `kind`: `nutrition_risk`, `biomedical_risk`, `wellness_priority`, `safety_flag` o `context`
- `probability`: probabilidad estimada, no afirmacion clinica
- `evidence_group`: `lab_only`, `diet_or_lab`, `lab_or_diet`, `survey_wellness`, `safety_only` o `unknown`
- `confidence_label`: `baja`, `media`, `alta`
- `recommendation_strength`: `no_convertir`, `baja`, `media`, `alta` o `bloqueada`
- `benchmark_status`
- `validation_source`
- `allowed_for_commercial_recommendation`
- `requires_disclaimer`
- `explanation`

## Ejemplo valido

```json
{
  "edad_rango": "31_50",
  "age_years": 32,
  "weight_value": 154,
  "weight_unit": "lb",
  "weight_kg": 69.8532,
  "peso_rango": "66_80",
  "height_value": 170,
  "height_unit": "cm",
  "height_cm": 170,
  "talla_rango": "166_175",
  "bmi": 24.17,
  "horas_sueno": "5_7h",
  "frecuencia_ejercicio": "1_2_semana",
  "dieta": "regular",
  "fatiga": "a_menudo",
  "exposicion_solar": "menos_15min",
  "frecuencia_enfermedad": "1_2_anio",
  "estres": "moderado",
  "alcohol": "ocasional",
  "sexo": "femenino",
  "tipo_dieta": "vegano",
  "dolor_muscular": "frecuente",
  "dolor_articular": "nunca",
  "niebla_mental": "moderado",
  "caida_cabello": "nunca",
  "piel_seca": "leve",
  "unas_quebradizas": "nunca",
  "calambres": "nunca",
  "objetivos": ["energia", "salud_osea"],
  "toma_suplementos": "si",
  "suplementos_actuales": ["vitamina_d"],
  "restricciones": ["sin_gluten"],
  "condiciones_seguridad": ["medicacion_cronica"],
  "presupuesto_min": 0,
  "presupuesto_max": 80
}
```

## Informacion que no se debe pedir como texto libre

Para un MVP confiable, no pedir texto libre sobre diagnosticos, medicamentos, dosis o sintomas. Usar listas cerradas o formularios estructurados:

- Medicacion: marcar solo categorias de riesgo en encuesta base (`anticoagulantes`, `medicacion_cronica`).
- Resultados de laboratorio: usar el flujo OCR/labs, con biomarcadores estructurados y revision visual.
- Suplementos actuales: lista cerrada de componentes frecuentes; si se necesita detalle de dosis, agregarlo como campos numericos por suplemento, no texto libre.
- Restricciones: checkboxes cerrados para alergias/excipientes relevantes.
