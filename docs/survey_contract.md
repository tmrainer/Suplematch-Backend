# Contrato de encuesta SupleMatch

Este contrato define el payload aceptado por `POST /api/v1/recommend` y debe mantenerse alineado con `frontend-suplematch/src/screens/Encuesta.jsx` y `app/schemas/encuesta.py`.

La encuesta usa solo valores cerrados. No se aceptan textos libres para evitar ambiguedad, contradicciones y mala interpretacion del sistema.

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
| `presupuesto` | `bajo`, `medio`, `alto`, `sin_preferencia` | `sin_preferencia` |

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
- `anticoagulantes`
- `medicacion_cronica`

Reglas:

- `ninguna` es excluyente y no puede combinarse con otras condiciones.
- `embarazo_lactancia` no puede combinarse con `sexo == "masculino"`.
- Cualquier condicion distinta de `ninguna` debe generar advertencias visibles en `profile_warnings`.

## Efecto en features del modelo

`FeatureBuilder` traduce la encuesta extendida a las features esperadas por el pipeline actual:

- `tipo_dieta == vegano|vegetariano` aumenta riesgo dietario.
- sintomas especificos alimentan `dolor_muscular`, `dolor_articular`, `niebla_mental`, `caida_cabello`, `piel_seca`, `unas_quebradizas`, `calambres`.
- `objetivos` activa metas (`meta_energia`, `meta_inmunidad`, `meta_belleza`, `meta_rendimiento`, `meta_salud_osea`, `meta_cognitivo`).
- `presupuesto` no cambia la condicion estimada; solo ajusta ranking comercial de productos.
- `suplementos_actuales`, `restricciones` y `condiciones_seguridad` generan advertencias y penalizaciones comerciales cuando aplique.

## Ejemplo valido

```json
{
  "edad_rango": "31_50",
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
  "presupuesto": "bajo"
}
```
