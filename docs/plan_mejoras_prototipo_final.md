# Plan de Mejoras — Prototipo Final Suplematch
**Entrega:** 10 de junio de 2026  
**Requisito del profesor:** Prototipo final con funcionalidad, integración y usabilidad sustancialmente mejoradas.

---

## Diagnóstico del estado actual

| Área | Estado | Problema |
|---|---|---|
| `app/ml/explainability.py` | Vacío (1 línea) | No hay explicabilidad real implementada |
| Probabilidades de condición | Hardcodeadas | `0.82 - index * 0.12` — no salen del modelo |
| `FeatureBuilder` | Incompleto | `sexo`, `peso_kg`, `altura_cm`, `tipo_dieta` son constantes, no vienen de la encuesta |
| Frontend → Backend | Desconectado | El frontend lee `r.nombre` / `r.razon` pero la API retorna `name` / `reason` |
| Sinergias y alertas | Hardcodeadas en UI | El frontend ignora los datos reales que retorna la API |
| Condiciones detectadas | No se muestran | La API las retorna pero la pantalla `Recomendaciones` no las renderiza |
| Pregunta `dieta` | Recogida, no usada | `buildPayload` en la encuesta la envía pero `FeatureBuilder` la ignora |
| Pregunta `alcohol` | Recogida, no usada | Igual que dieta |

---

## Mejora 1 — Explainability real (prioridad crítica)

El profesor pide que el usuario entienda **por qué** obtuvo ese resultado y **qué variables lo determinaron**.

### 1.1 Probabilidades reales del Modelo 1

**Archivo:** `app/ml/runtime/pipeline_completo.py`

El Modelo 1 es un clasificador sklearn multilabel. En lugar de `predict`, usar `predict_proba` para obtener la probabilidad real de cada condición.

```python
# Antes (pipeline_completo.py)
pred = _pipe_m1.predict(row)[0]
detected = [_labels[i] for i, v in enumerate(pred) if v == 1]

# Después
proba = _pipe_m1.predict_proba(row)  # lista de arrays, uno por label
detected = []
condition_scores = {}
for i, label in enumerate(_labels):
    p = proba[i][0][1]  # probabilidad de clase 1
    condition_scores[label] = round(float(p), 4)
    if p >= 0.45:
        detected.append(label)

resultado["condition_scores"] = condition_scores
```

Pasar `condition_scores` hasta la respuesta de la API para que el frontend muestre barras de probabilidad reales.

### 1.2 Feature importance del Modelo 1

**Archivo nuevo:** `app/ml/explainability.py`

El pipeline sklearn expone `feature_importances_` en el estimador final. Se puede extraer qué features (columnas de la encuesta) más influyeron en cada condición.

```python
def get_feature_importance(pipeline, feature_names: list[str]) -> dict[str, float]:
    """Extrae importancia de features del clasificador dentro del pipeline."""
    estimator = pipeline.named_steps.get("classifier") or pipeline[-1]
    if not hasattr(estimator, "estimators_"):
        return {}
    
    importances = {}
    for label_idx, est in enumerate(estimator.estimators_):
        if hasattr(est, "feature_importances_"):
            importances[label_idx] = dict(
                zip(feature_names, est.feature_importances_.tolist())
            )
    return importances


def explain_conditions(
    condition_scores: dict[str, float],
    feature_importances: dict,
    user_payload: dict,
    labels: list[str],
) -> list[dict]:
    """
    Para cada condición detectada, devuelve las top-3 variables que más
    contribuyeron a activarla, con el valor que el usuario ingresó.
    """
    explanations = []
    FEATURE_LABELS = {
        "fatiga_general":      "Fatiga frecuente",
        "problemas_sueno":     "Problemas de sueño",
        "irritabilidad":       "Nivel de estrés",
        "enfermedad_frecuente":"Frecuencia de enfermedades",
        "exposicion_solar":    "Exposición al sol",
        "nivel_actividad":     "Actividad física",
        "edad":                "Edad",
        "niebla_mental":       "Niebla mental",
    }
    
    for label_idx, label in enumerate(labels):
        score = condition_scores.get(label, 0.0)
        if score < 0.45:
            continue
        
        feat_imp = feature_importances.get(label_idx, {})
        top_features = sorted(feat_imp.items(), key=lambda x: x[1], reverse=True)[:3]
        
        drivers = []
        for feat_name, importance in top_features:
            drivers.append({
                "feature":       feat_name,
                "label":         FEATURE_LABELS.get(feat_name, feat_name),
                "value":         user_payload.get(feat_name),
                "importance":    round(importance, 4),
            })
        
        explanations.append({
            "condition":    label,
            "probability":  score,
            "drivers":      drivers,
        })
    
    return explanations
```

### 1.3 Razón por componente (Modelo 2)

**Archivo:** `app/services/recommendation_service.py`

Actualmente la razón es texto genérico: `"Relacionado con fatiga o baja energía."`. Mejorar para incluir la condición que lo activó y su probabilidad:

```python
def _recommendation_reason(condition: str | None, score: float | None, rec_type: str | None) -> str:
    condition_name = _condition_display_name(condition)
    if score and score > 0.70:
        return f"Alta prioridad por {condition_name.lower()} (confianza {round(score*100)}%)."
    if condition and condition != "soporte_funcional":
        return f"Indicado para {condition_name.lower()}."
    if rec_type == "candidato_gnn":
        return "Complementa el pack por sinergia funcional con los demás componentes."
    return "Recomendado para el perfil evaluado."
```

### 1.4 Nuevo campo en la respuesta API

Agregar `explainability` al response de `/recommend`:

```json
{
  "conditions_display": [...],
  "explainability": [
    {
      "condition": "FATIGA",
      "probability": 0.83,
      "drivers": [
        { "label": "Fatiga frecuente",   "value": 4, "importance": 0.38 },
        { "label": "Problemas de sueño", "value": 5, "importance": 0.22 },
        { "label": "Nivel de estrés",    "value": 4, "importance": 0.17 }
      ]
    }
  ],
  "recommendations": [...]
}
```

**Archivo:** `app/schemas/recomendacion.py` — agregar `explainability: list[ConditionExplanation]`.

---

## Mejora 2 — Cerrar brechas de integración frontend ↔ backend

### 2.1 Mapeo de campos en `Recomendaciones.jsx`

El componente lee campos inexistentes en la respuesta real de la API:

| Lo que lee el frontend | Lo que retorna la API | Fix |
|---|---|---|
| `r.nombre` | `r.name` | Cambiar a `r.name` |
| `r.razon` | `r.reason` | Cambiar a `r.reason` |
| `r.dosis` | `r.dosage_hint` | Cambiar a `r.dosage_hint` |
| `apiResult?.recomendaciones` | `apiResult?.recommendations` | Cambiar key |

### 2.2 Mostrar condiciones detectadas

La pantalla `Recomendaciones.jsx` ignora `apiResult.conditions_display`. Agregar una sección de "Perfil detectado" con las condiciones y sus probabilidades (recibidas desde el backend real en Mejora 1.1).

### 2.3 Sinergias y alertas desde la API

Las sinergias/alertas están hardcodeadas en el JSX. Reemplazar por los datos reales:

```jsx
// Antes (hardcoded)
<div>💡 <strong>Zinc + Vitamina C</strong> se potencian mutuamente</div>

// Después (dinámico)
{(apiResult?.sinergias ?? []).map(s => (
  <div key={`${s.component_a}-${s.component_b}`}>
    💡 <strong>{s.component_a} + {s.component_b}</strong> — {s.type}
  </div>
))}
{(apiResult?.alertas ?? []).map(a => (
  <div key={`${a.component_a}-${a.component_b}`}>
    ⚠️ <strong>{a.component_a} + {a.component_b}</strong> — {a.type}
  </div>
))}
```

---

## Mejora 3 — Encuesta más completa

### 3.1 Campos faltantes en FeatureBuilder

**Archivo:** `app/ml/feature_builder.py`

Actualmente se hardcodean valores que deberían venir de la encuesta:

```python
# Hardcodeado (incorrecto)
"sexo": "F",
"tipo_dieta": "omnivoro",
"peso_kg": 60.0,
"altura_cm": 165.0,
```

**Fix en `FeatureBuilder.build_pipeline_payload`:**

```python
DIETA_MAP = {
    "poco_variada":     "omnivoro",
    "regular":          "omnivoro",
    "bastante_variada": "omnivoro",
    "muy_balanceada":   "omnivoro",
}

def build_pipeline_payload(self, encuesta: EncuestaInput) -> dict:
    ...
    tipo_dieta = self.DIETA_MAP.get(encuesta.dieta, "omnivoro")
    ...
    return {
        "sexo": encuesta.sexo if hasattr(encuesta, "sexo") else "F",
        "tipo_dieta": tipo_dieta,
        ...
    }
```

### 3.2 Agregar pregunta de sexo a la encuesta

**Archivo:** `frontend-suplematch/src/screens/Encuesta.jsx`

Agregar como primera pregunta (antes de edad):

```js
{
  key: 'sexo',
  title: '¿Cuál es tu sexo biológico?',
  sub: 'Relevante para el perfil nutricional',
  type: 'single',
  options: [
    { label: 'Femenino',    value: 'F' },
    { label: 'Masculino',   value: 'M' },
    { label: 'Prefiero no indicar', value: 'F' },
  ],
},
```

**Archivo:** `app/schemas/encuesta.py` — agregar campo `sexo: Literal["M", "F"] = "F"`.

### 3.3 Usar variable `alcohol` en las metas

La pregunta `alcohol` ya se recoge pero no se usa. Puede alimentar la meta de toxicidad hepática o desactivar ciertos suplementos:

```python
ALCOHOL_MAP = {
    "nunca":     0,
    "raro":      1,
    "ocasional": 2,
    "frecuente": 4,
}
```

---

## Mejora 4 — Nueva pantalla de Explainability en el frontend

**Archivo nuevo:** `frontend-suplematch/src/screens/Explicacion.jsx`

Pantalla que se muestra entre `Loading` y `Recomendaciones`, o como tab en `Recomendaciones`:

```
┌──────────────────────────────────────┐
│  Por qué te recomendamos esto        │
├──────────────────────────────────────┤
│  🔍 Fatiga o baja energía      83%  │
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░         │
│                                      │
│  Factores que lo determinaron:       │
│  • Fatiga frecuente         (alta)   │
│  • Problemas de sueño       (media)  │
│  • Nivel de estrés          (media)  │
├──────────────────────────────────────┤
│  🦠 Baja inmunidad          61%  │
│  ▓▓▓▓▓▓▓▓▓░░░░░░░░░         │
│                                      │
│  Factores que lo determinaron:       │
│  • Enfermedades frecuentes  (alta)   │
│  • Exposición al sol        (media)  │
└──────────────────────────────────────┘
```

Flujo actualizado: `Landing → Encuesta → Loading → Recomendaciones (con tab "¿Por qué?") → Precios → Feedback`

---

## Mejora 5 — Usabilidad general

### 5.1 Pantalla de Condiciones actual
`screens/Condiciones.jsx` existe pero no se sabe si está integrada al flujo. Verificar que muestra `conditions_display` de la API antes de `Recomendaciones`.

### 5.2 Feedback loop visible
El usuario no sabe que su feedback mejora futuras recomendaciones. Agregar en `Feedback.jsx` un mensaje post-envío:

> "Gracias. Tu opinión ayuda a mejorar las recomendaciones para todos los usuarios."

### 5.3 Manejo de error de API
Si la API falla, el frontend cae en el fallback hardcodeado sin notificar al usuario. Mostrar un toast con mensaje claro y opción de reintentar.

---

## Resumen de archivos a modificar

| Archivo | Tipo de cambio |
|---|---|
| `app/ml/explainability.py` | Implementar desde cero |
| `app/ml/runtime/pipeline_completo.py` | Usar `predict_proba`, pasar `condition_scores` |
| `app/services/recommendation_service.py` | Integrar `explainability`, mejorar `_recommendation_reason` |
| `app/schemas/recomendacion.py` | Agregar `explainability` al response schema |
| `app/schemas/encuesta.py` | Agregar campo `sexo`, `dieta` como requerido |
| `app/ml/feature_builder.py` | Usar `dieta`, `sexo`, `alcohol` de la encuesta |
| `frontend/src/screens/Recomendaciones.jsx` | Corregir campos, mostrar condiciones, sinergias reales |
| `frontend/src/screens/Encuesta.jsx` | Agregar pregunta de sexo |
| `frontend/src/screens/Explicacion.jsx` | Crear pantalla nueva (o tab) |
| `frontend/src/App.jsx` | Integrar nueva pantalla al flujo |

---

## Priorización para el 10/06/2026

| Prioridad | Tarea | Impacto |
|---|---|---|
| 🔴 1 | Implementar `explainability.py` con feature importance real | Alto — es el requisito explícito del profesor |
| 🔴 2 | Corregir mapeo de campos frontend ↔ backend | Alto — sin esto la app muestra datos vacíos |
| 🔴 3 | Mostrar `conditions_display` y probabilidades reales en UI | Alto — explica el porqué visualmente |
| 🟡 4 | Sinergias y alertas dinámicas desde la API | Medio — reemplaza hardcode por datos reales |
| 🟡 5 | Integrar `dieta` y `sexo` al `FeatureBuilder` | Medio — cierra brecha de datos entre encuesta y modelo |
| 🟢 6 | Pantalla `Explicacion.jsx` dedicada | Medio — visual impactante para la presentación |
| 🟢 7 | Manejo de errores y feedback post-envío | Bajo — mejora usabilidad |
