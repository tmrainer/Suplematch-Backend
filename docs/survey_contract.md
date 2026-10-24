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

Desde el contrato `2026-10-24.1`:

- La app pregunta por grupo (`red_meat_servings_week`, `poultry_servings_week`, `fish_servings_week`, `eggs_servings_week`, `legume_servings_week`, `dairy_servings_week`) con la escala `0, 1, 3, 5, 7, 14` porciones/semana (no consumo, 1/sem, 2-3/sem, 4-6/sem, 1 al dia, 2+ al dia) y porciones de referencia peruanas. La escala anterior terminaba en 7 (=1 al dia): lacteos y proteina salian bajos para casi todos.
- Cada grupo tiene "No se": queda faltante. `protein_g_day_estimate` solo se estima con el bloque completo; los grupos que excluye `tipo_dieta` (p. ej. carnes en vegetarianos) cuentan como 0 aunque no se respondan. Un grupo sin responder deja la proteina como faltante.
- La estimacion suma 15 g/dia de cereales y tuberculos (arroz, pan, fideos, papa), que el bloque no pregunta; y 20 g si toma proteina en polvo sin dosis declarada. Heuristicas pendientes de revision por nutricionista.
- `meat_servings_week` solo se calcula si se respondieron carne roja y pollo.

### Seguimiento y factores de riesgo (contrato `2026-10-24.1`)

| Campo | Valores | Cuando se pregunta | Efecto |
| --- | --- | --- | --- |
| `analisis_ultimo_anio` | `si_a_mano`, `si_sin_resultados`, `no`, `no_se` | Primera pregunta | Con `si_a_mano` la app ofrece subir el examen o tipear 5 valores clave (vitamina D, B12, ferritina, hemoglobina, glucosa) que llegan como `lab_results`. No cambia features. |
| `fatiga_duracion` | `menos_2_semanas`, `2_semanas_3_meses`, `mas_3_meses` | `fatiga` = a menudo / siempre | `menos_2_semanas` limita `fatiga_general` a 3. |
| `fatiga_mejora_descanso` | `si`, `no`, `a_veces` | idem | `si` con sueño corto limita `fatiga_general` a 3 (la explica el sueño). |
| `protector_solar`, `piel_expuesta` | `nunca/a_veces/siempre`; `cara_manos/brazos/brazos_piernas` | Siempre (opcional) | `vitamin_d_sun_barrier` = protector siempre + solo cara y manos. |
| `menstruacion_abundante`, `parto_ultimo_anio` | `si/no/no_aplica`; `si/no` | Sexo femenino | `iron_loss_risk`. Incompatible con sexo masculino. |
| `dona_sangre` | `no`, `1_al_anio`, `2_o_mas_al_anio` | Siempre (opcional) | `iron_loss_risk` (+1 con 2 o mas al año). |
| `anios_dieta_vegetal` | `menos_1`, `1_3`, `mas_3` | Vegetariano o vegano | Vegano de menos de 1 año: B12 dietaria `low` en vez de `critical_low`; mas de 3 años sin B12: `b12_absorption_risk` +1. |
| `medicamentos_b12` | lista: `metformina`, `antiacidos_ibp` | Siempre (opcional) | `b12_absorption_risk` +1 por cada uno. |
| `alimentos_fortificados_b12` | `no`, `si`, `no_se` | Siempre (opcional) | `si` (o `vitamina_b12` / `multivitaminico` en `suplementos_actuales`) deja la B12 dietaria en `normal`. |

Los tres conteos (`iron_loss_risk`, `vitamin_d_sun_barrier`, `b12_absorption_risk`) son features del Modelo 1 (`FEATURE_CONTRACT_VERSION` `2026-10-24.1`) con -1 cuando no se respondio ninguna pregunta del grupo, y tienen reglas en `condition_rules.csv` (DEFICIT_HIERRO, DEFICIT_VIT_D, DEFICIT_B12).

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

### Tabaco y salud autopercibida (contrato `2026-10-23.1`)

| Campo | Valores | Descripcion corta |
| --- | --- | --- |
| `tabaco` | `nunca`, `ex`, `actual` | ¿Fuma? Opcional. Alimenta el modelo real de riesgo de laboratorio (`lab_risk_estimates`); no bloquea productos. |
| `salud_autopercibida` | `excelente`, `muy_buena`, `buena`, `regular`, `mala` | "En general, ¿cómo diría que es su salud?" Opcional. Alimenta `lab_risk_estimates`. |

Medido con NHANES (ver `docs/condition_lab_model.md`): su aporte al modelo real es marginal (|ΔAUC| ≤ 0.006), así
que no merecen pantalla propia; pueden ir como dos preguntas rápidas al final.

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
- `diabetes_medicada` (añadido 2026-10-22: activa reglas de cromo y afines)
- `inmunosupresion` (añadido 2026-10-22: probióticos y herbales requieren revisión; bloquea comercial)
- `sedantes` (añadido 2026-10-22: melatonina, valeriana, L-teanina)
- `hipertension` (añadido 2026-10-22: cafeína, energizantes)

Código derivado por el backend, no se pregunta: `insomnio` cuando `sleep_quality == "mala"`,
`night_wakeups == "3_o_mas"` o `horas_sueno == "menos_5h"`. Solo activa reglas de interacción (cafeína) y un aviso.

Reglas:

- `ninguna` es excluyente y no puede combinarse con otras condiciones.
- `embarazo_lactancia` no puede combinarse con `sexo == "masculino"`.
- Cualquier condicion distinta de `ninguna` debe generar advertencias visibles en `profile_warnings`.
- `enfermedad_renal`, `enfermedad_hepatica`, `embarazo_lactancia`, `inmunosupresion` y minoría de edad bloquean recomendaciones comerciales directas hasta revision profesional.
- `problema_tiroideo`, `anticoagulantes`, `medicacion_cronica`, `diabetes_medicada`, `sedantes` e `hipertension` activan `safety_level=caution`: se muestran alertas y se bloquean o penalizan productos específicos por ingrediente, pero no se oculta todo el catálogo comercial.

## Pasos condicionales, pregunta retirada y embudo (2026-10-24)

- La app solo muestra los pasos opcionales a quien le cambian el resultado (`rules.conditional_steps`):
  - detalle de sol si la exposición es baja o moderada;
  - hierro si es mujer de 12 a 50 años o hay fatiga persistente;
  - B12 si es vegetariana/vegana o tiene 50+;
  - metformina/omeprazol (paso aparte, después de seguridad) si declaró medicación para glucosa o crónica, o tiene 50+.
- `dieta` (autoevaluación de variedad) ya no se pregunta: cambiaba la detección en 3 de 120 casos
  (`scripts/clinical/valor_preguntas.py`). El backend la sigue aceptando (`rules.deprecated_ui_fields`).
- Media de pasos visibles en los 120 perfiles del paquete: 27 → 24.
- Embudo: la app envía `view` / `complete` / `submit` por paso a `POST /api/v1/survey/events` (solo clave del
  paso, posición y número de pasos visibles; nunca respuestas). `GET /api/v1/survey/funnel?days=30` (admin) da
  abandono por paso. Tabla `survey_step_events`, migración `20261024_0015`.

## Efecto en features del modelo

`FeatureBuilder` traduce la encuesta extendida a las features esperadas por el pipeline actual:

- `tipo_dieta == vegano|vegetariano` aumenta el riesgo de B12, zinc y omega 3 por sus propios estados; desde `2026-10-24.1` ya no marca `dieta_deficiente` por si solo.
- `dieta_deficiente`: `dieta == poco_variada`, antecedente de anemia, o 2+ nutrientes bajos calculados con cantidades respondidas (antes bastaba uno, y "regular" tambien contaba).
- sintomas especificos alimentan `dolor_muscular`, `dolor_articular`, `niebla_mental`, `caida_cabello`, `piel_seca`, `unas_quebradizas`, `calambres`.
- `objetivos` NO entra en la deteccion desde `2026-10-24.1`: las banderas `meta_*` se calculan solo con sintomas, habitos y edad. Los objetivos ordenan las condiciones detectadas y, dentro de cada grupo de prioridad, los componentes (`GOAL_CONDITIONS` en `reglas_presentacion.py`).
- `age_years`, `weight_kg` y `height_cm` tienen prioridad sobre los rangos legacy en features numericas.
- `presupuesto` o `presupuesto_min/max` no cambia la condicion estimada; solo ajusta ranking comercial de productos.
- `suplementos_actuales`, `restricciones` y `condiciones_seguridad` generan advertencias y penalizaciones comerciales cuando aplique.
- `bmi` puede guardarse y usarse como senal interna, pero no debe mostrarse en la encuesta ni en el resumen de respuestas.
- porciones dietarias generan estados cerrados para `benchmark_diet_b12_status`, `benchmark_diet_vitamin_c_status`, `benchmark_diet_zinc_status`, `benchmark_diet_magnesium_status`, `benchmark_diet_calcium_status`, `benchmark_diet_folate_status`, `benchmark_diet_protein_status` y `benchmark_diet_omega3_status`.
- campos faltantes de alimentacion se guardan como `unknown`; el modelo no debe forzar una conclusion por ausencia de respuesta.
- sueno, cafeina tardia y recuperacion ajustan prioridades de bienestar, no diagnosticos.
- `tabaco` y `salud_autopercibida` no entran al Modelo 1 (reglas); solo al modelo real NHANES (`lab_risk_estimates`).

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
- `risk_index`: **indice de riesgo basado en reglas** (0-1), no una probabilidad clinica. Mientras el Modelo 1 se
  entrene con datos sinteticos, la UI debe rotularlo con `score_label` ("Índice de riesgo basado en reglas").
- `score_semantics`: `indice_riesgo_reglas` en estas tres listas; `probabilidad_calibrada_real` solo en
  `lab_risk_estimates`. La respuesta repite esto en `condition_score_semantics` / `condition_score_label`.
- `probability`: obsoleto, mismo valor que `risk_index`; se conserva por compatibilidad. No mostrar la palabra
  "probabilidad" en la UI.
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
