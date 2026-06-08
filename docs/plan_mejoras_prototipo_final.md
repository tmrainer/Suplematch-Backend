# Plan de Mejoras — Prototipo Final SupleMatch
**Entrega:** 10 de junio de 2026  
**Requisito:** *"Final Prototype: Presentation of the final Data Product prototype with substantially improved functionality, integration, and usability."*

---

## Arquitectura del sistema

```
┌─────────────────────────────────────────────────────────┐
│                    USUARIO                              │
│   Responde 9 preguntas sobre hábitos y síntomas        │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│              MODELO 1 — Random Forest multilabel        │
│                                                         │
│  Input: edad, fatiga, sueño, sol, ejercicio,           │
│         estrés, inmunidad, dieta, alcohol               │
│                                                         │
│  Output: probabilidad de cada condición                 │
│  ┌─────────────────────────────────────────┐            │
│  │ FATIGA          → 83%                   │            │
│  │ DEFICIT_VIT_D   → 71%                   │            │
│  │ BAJA_INMUNIDAD  → 52%                   │            │
│  │ ESTRES          → 31% (descartado <45%) │            │
│  └─────────────────────────────────────────┘            │
│                                                         │
│  + SHAP TreeExplainer: qué variables causaron cada     │
│    condición, personalizado por usuario                 │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│              MODELO 2 — GNN (Grafo)                     │
│                                                         │
│  Grafo de 935 componentes nutricionales con             │
│  1,604 relaciones entre ellos                           │
│                                                         │
│  Por cada condición detectada:                          │
│  1. Selecciona semillas directas (ej: Vitamina D        │
│     para DEFICIT_VIT_D)                                 │
│  2. Busca candidatos por similitud coseno en el         │
│     espacio de embeddings GNN                           │
│  3. Filtra por relaciones funcionales del grafo         │
│  4. Detecta sinergias (pares que se potencian)          │
│  5. Detecta alertas (interacciones riesgosas)           │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│              RE-RANKING POR FEEDBACK                    │
│                                                         │
│  Los packs de suplementos se reordenan según el         │
│  historial de feedback de usuarios anteriores.          │
│  Si usuarios similares calificaron bien un pack,        │
│  sube en el ranking.                                    │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│              ENRIQUECIMIENTO CON DIGEMID                │
│                                                         │
│  Cada suplemento recomendado se vincula a productos     │
│  reales disponibles en farmacias peruanas:              │
│  Inkafarma, Mifarma, Boticas y Salud, etc.             │
│                                                         │
│  Solo aparecen productos con:                           │
│  ✓ Registro Sanitario validado en DIGEMID              │
│  ✓ Precio scrapeado recientemente                       │
│  ✓ URL activa en la farmacia                            │
└─────────────────────────────────────────────────────────┘
```

---

## Diagnóstico del estado anterior (antes de las mejoras)

Esta sección documenta los problemas que existían antes del 08/06/2026.

### Problemas críticos (el sistema no funcionaba correctamente)

| Problema | Archivo | Impacto |
|---|---|---|
| `explainability.py` estaba vacío | `app/ml/explainability.py` | No había ninguna explicabilidad implementada |
| Nombre incorrecto del pkl del Modelo 2 | `modelo2_inference.py` | El Modelo 2 nunca cargaba, lanzaba error |
| Rutas de CSV rotas en config | `app/core/config.py` | El backend no encontraba los datos de DIGEMID |
| Modelos pkl en `.gitignore` | `.gitignore` | Quien clonaba el repo no tenía los modelos |

### Problemas de integración (datos reales ignorados)

| Problema | Impacto visible |
|---|---|
| Probabilidades hardcodeadas (0.82, 0.70, 0.58...) | Todos los usuarios veían exactamente las mismas probabilidades |
| Sinergias hardcodeadas en el JSX del frontend | "Zinc + Vitamina C" aparecía siempre, sin importar el resultado real |
| Lista de suplementos hardcodeada en Feedback | Siempre mostraba Vitamina D3, Zinc, Vitamina C, sin importar la recomendación |
| `dieta` y `alcohol` de la encuesta ignorados | El FeatureBuilder no los usaba, eran preguntas decorativas |

### Problemas de datos

| Problema | Impacto |
|---|---|
| CSVs duplicados en múltiples carpetas | Confusión sobre cuál es la fuente de verdad |
| README con información incorrecta | Instrucciones de instalación con nombre de pkl equivocado |
| `shap` no en requirements.txt | Dependencia no documentada |

---

## Mejora 1 — Explainability con SHAP

### ¿Qué pide el profesor?

Que el sistema pueda explicar **por qué** generó ese resultado: qué variables del usuario influyeron en cada condición detectada y cuánto.

### ¿Qué es SHAP y por qué se eligió?

SHAP (SHapley Additive exPlanations) es el estándar de la industria para explicabilidad de modelos de machine learning. Se basa en la teoría de juegos de Shapley (1953): calcula la contribución justa de cada "jugador" (variable) al resultado del "juego" (predicción del modelo).

**Ventajas sobre otras alternativas:**
- **Exacto para árboles:** `TreeExplainer` calcula valores exactos (no aproximaciones) aprovechando la estructura del Random Forest
- **Personalizado:** cada usuario obtiene una explicación diferente según sus respuestas
- **Consistente:** si una variable tiene más impacto, siempre tiene un SHAP value mayor
- **Interpretable:** SHAP value positivo = empuja hacia "sí tiene esa condición"; negativo = empuja hacia "no la tiene"

### Cómo se implementó en SupleMatch

El Modelo 1 es un `MultiOutputClassifier` que contiene un `RandomForestClassifier` por cada condición. Para explicar la predicción de un usuario:

**Paso 1 — Separar preprocesador del clasificador:**
```python
steps = list(pipeline.steps)
preprocessor = Pipeline(steps[:-1])       # ColumnTransformer (OHE + passthrough)
classifier = steps[-1][1]                  # MultiOutputClassifier
```

**Paso 2 — Transformar el input:**
```python
X_transformed = preprocessor.transform(row_df)
# Convierte: "baja" → [1, 0, 0] (one-hot encoding de exposicion_solar)
# Pasa numéricas sin cambio: fatiga_general=4 → 4
```

**Paso 3 — SHAP por condición:**
```python
for i, label in enumerate(labels):
    if condition_scores[label] < 0.45:
        continue  # solo condiciones detectadas
    estimator = classifier.estimators_[i]  # el RF para esta condición
    explainer = shap.TreeExplainer(estimator)
    shap_values = explainer.shap_values(X_transformed)
    # shap_values[1][0] = valores para clase "sí tiene condición", primera muestra
```

**Paso 4 — Top-3 features:**
```python
top_indices = np.argsort(np.abs(vals))[::-1][:3]
# Ordena por impacto absoluto, toma los 3 más importantes
```

**Paso 5 — Mapear al nombre original:**
```python
# "cat__exposicion_solar_baja" → feature="exposicion_solar", valor="baja"
# "num__fatiga_general" → feature="fatiga_general", valor=4
```

### Visualización en la app

La pantalla de Condiciones muestra para cada condición detectada:

```
┌────────────────────────────────────────────┐
│ ☀️  Déficit de Vitamina D            71%  │
│ ████████████████░░░░░░                     │
│ Alta prioridad                             │
├────────────────────────────────────────────┤
│ ¿Por qué?                                  │
│ Exposición solar    [Menos de 15 min/día] │ ← rojo (alto)
│ Prioridad salud ósea         [Priorizada] │ ← rojo (alto)
│ Edad                                  [24] │ ← verde (bajo)
└────────────────────────────────────────────┘
```

Los badges de color indican el nivel de impacto de cada variable en la predicción:
- 🔴 **Alto** (shap_value > 0.15): variable muy determinante
- 🟡 **Medio** (shap_value 0.05-0.15): contribución moderada
- 🟢 **Bajo** (shap_value < 0.05): contribución menor

### Fallback automático

Si `shap` no está instalado en el entorno, el sistema detecta el `ImportError` y usa un mapeo de reglas de dominio (qué variables son relevantes para cada condición según conocimiento experto). El resultado visual es el mismo pero sin los valores exactos de SHAP.

---

## Mejora 2 — Probabilidades reales del Modelo 1

### ¿Por qué importa?

Las probabilidades son el indicador principal de confianza del sistema. Mostrar valores reales del modelo:
- Da credibilidad científica al resultado
- Permite al usuario entender qué tan seguro está el sistema de cada condición
- Es diferente para cada usuario (personalización real)

### Implementación

```python
# Antes: predict binario (0 o 1)
pred = pipeline.predict(row)[0]
# → [1, 0, 1, 0, 0, 0] — sin gradación

# Después: predict_proba (probabilidad continua)
proba_list = pipeline.predict_proba(row)
# → {"FATIGA": 0.83, "DEFICIT_VIT_D": 0.71, "BAJA_INMUNIDAD": 0.52, ...}
```

Se considera que una condición está "detectada" si su probabilidad ≥ 45%.

---

## Mejora 3 — Integración real de dieta y alcohol

### Justificación

La encuesta recogía estas preguntas pero el modelo las ignoraba completamente. Para una entrega de prototipo final, todas las variables de la encuesta deben tener efecto en el resultado.

### Lógica implementada

**Calidad de dieta (`dieta`):**

Una dieta poco variada aumenta el riesgo de déficits nutricionales. Se usa para activar metas:

| Respuesta | Efecto en el modelo |
|---|---|
| `poco_variada` | `meta_energia=1`, `meta_salud_osea=1` |
| `regular` | `meta_energia=1` si también hay fatiga |
| `bastante_variada` | Sin cambio adicional |
| `muy_balanceada` | Sin cambio adicional |

**Consumo de alcohol (`alcohol`):**

El alcohol afecta la absorción de vitaminas y el sistema inmune:

| Respuesta | Efecto en el modelo |
|---|---|
| `frecuente` | `enfermedad_frecuente += 2`, `meta_inmunidad=1` |
| `ocasional` | `enfermedad_frecuente += 1` |
| `raro` / `nunca` | Sin cambio |

---

## Mejora 4 — Correcciones de integración Frontend ↔ Backend

### El problema de los datos hardcodeados

En una primera versión del MVP es normal hardcodear datos para probar la interfaz. Pero en el prototipo final, todos los datos deben venir de la API real.

### Lo que se corrigió

**Sinergias y alertas (antes hardcodeadas):**

Las sinergias y alertas se generan en el Modelo 2 analizando el grafo. Por ejemplo, si el modelo recomienda Vitamina C y Zinc, detecta automáticamente que tienen sinergia funcional porque están conectados en el grafo con `relationship_class: FUNCIONAL`. Esto ahora se muestra en la pantalla.

**Suplementos en feedback:**

El formulario de feedback ahora lista los suplementos reales recomendados para ese usuario, no siempre "Vitamina D3, Zinc, Vitamina C".

**Probabilidades en pantalla de condiciones:**

La barra de probabilidad y el porcentaje mostrado son los valores reales del `predict_proba` del Modelo 1.

---

## Estado del sistema tras las mejoras

### Flujo completo funcional

```
Encuesta (9 preguntas)
    ↓ dieta y alcohol ahora se usan
FeatureBuilder → payload para el modelo
    ↓
Modelo 1 (Random Forest)
    ↓ predict_proba → probabilidades reales
    ↓ SHAP TreeExplainer → drivers personalizados
Condiciones detectadas + explicaciones
    ↓
Modelo 2 (GNN)
    ↓ semillas + embeddings + grafo
Suplementos recomendados + sinergias + alertas reales
    ↓
Re-ranking por feedback
    ↓
Enriquecimiento DIGEMID → productos con precio y RS
    ↓
Respuesta API con campos explainability, conditions_display, sinergias, alertas
    ↓
Frontend muestra todo de forma dinámica (no hardcodeada)
```

### Lo que muestra el usuario en cada pantalla

| Pantalla | Datos dinámicos (desde API) |
|---|---|
| **Condiciones** | Probabilidad real por condición · Drivers SHAP personalizados · Valores de las respuestas del usuario |
| **Recomendaciones** | Pack recomendado · Razón con % de confianza · Sinergias reales del grafo · Alertas reales de interacción · Productos con precio real |
| **Precios** | Productos disponibles por farmacia · RS DIGEMID · Precio scrapeado |
| **Feedback** | Lista real de suplementos recomendados |

---

## Pendientes futuros (post-entrega)

Estas mejoras quedaron identificadas pero no se implementaron por tiempo:

| Mejora | Descripción | Complejidad |
|---|---|---|
| Pregunta de sexo en la encuesta | Agregar al frontend y al schema de la API | Baja |
| SHAP para el Modelo 2 (GNN) | SHAP no aplica directamente; se necesitaría GNNExplainer (PyTorch Geometric) | Alta |
| Guardar preferencias del usuario | Persistir perfil entre sesiones | Media |
| Dashboard de métricas | Visualizar distribución de condiciones y feedback | Media |
| Actualización semanal del catálogo | Automatizar el scraping y re-validación DIGEMID | Media |
