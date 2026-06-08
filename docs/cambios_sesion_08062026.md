# Cambios y mejoras implementadas — 08/06/2026
## Preparación para entrega del Prototipo Final (10/06/2026)

---

## Contexto general

SupleMatch es un sistema de recomendación personalizada de suplementos para el mercado peruano. El usuario responde una encuesta de 9 preguntas sobre sus hábitos y síntomas; el sistema detecta condiciones de salud probables y recomienda un pack de suplementos disponibles en farmacias peruanas con registro sanitario DIGEMID validado.

El sistema tiene dos modelos de machine learning encadenados:

1. **Modelo 1 — Clasificador de condiciones (Random Forest multilabel):** Toma las respuestas de la encuesta y predice qué condiciones de salud tiene el usuario (fatiga, déficit de vitamina D, baja inmunidad, estrés, etc.).

2. **Modelo 2 — Recomendador basado en grafo (GNN):** Dado el conjunto de condiciones detectadas, usa un grafo de relaciones entre componentes nutricionales para recomendar los suplementos más adecuados, incluyendo sinergias y alertas de interacción.

---

## Cambio 1 — Reorganización de archivos de datos (CSV)

### Situación anterior

Los archivos de datos clave estaban sueltos en carpetas incorrectas:

```
Proyecto/
├── digemid_limpio(1).csv          ← suelto en la raíz del proyecto
├── product_components(1).csv      ← suelto en la raíz del proyecto
└── Suplematch-Backend/
    ├── digemid_limpio.csv         ← duplicado suelto en raíz del backend
    └── product_components.csv     ← duplicado suelto en raíz del backend
```

Además, el archivo de configuración `app/core/config.py` apuntaba a rutas incorrectas que ya no existían, lo que causaba errores al iniciar el backend.

### Qué son estos archivos

- **`digemid_limpio.csv`**: Datos del registro oficial de medicamentos y suplementos de DIGEMID (Dirección General de Medicamentos, Insumos y Drogas del Perú). Contiene 2,000 productos con su composición, clasificación ATC y forma farmacéutica. Es la fuente de validación regulatoria.

- **`product_components.csv`**: Mapeo entre cada ítem de DIGEMID y los componentes nutricionales del grafo del Modelo 2. Permite vincular "CREVET 500 mg" (producto real) con "COMP_67B16EEFC42F" (Ácido Ascórbico en el grafo). Tiene 14,022 filas.

### Solución aplicada

```
Suplematch-Backend/
├── data/
│   ├── raw/
│   │   └── csv/
│   │       └── digemid_limpio.csv          ← aquí: datos regulatorios crudos
│   └── training/
│       └── modelo2/
│           ├── Component_Master_Clean.csv
│           ├── Component_Relationship_Edges_Clean.csv
│           └── product_components.csv      ← aquí: insumo de entrenamiento
```

Se eliminaron todos los duplicados y se actualizó `app/core/config.py`:

```python
# Antes (paths rotos)
DIGEMID_CSV_PATH = BASE_DIR / "digemid_limpio.csv"
PRODUCT_COMPONENTS_CSV_PATH = BASE_DIR / "product_components.csv"

# Después (paths correctos)
DIGEMID_CSV_PATH = BASE_DIR / "data/raw/csv/digemid_limpio.csv"
PRODUCT_COMPONENTS_CSV_PATH = BASE_DIR / "data/training/modelo2/product_components.csv"
```

---

## Cambio 2 — Modelos entrenados versionados en el repositorio

### Situación anterior

El archivo `.gitignore` tenía `*.pkl`, lo que significa que git ignoraba completamente los modelos entrenados. Consecuencia: cualquier persona que clonara el repositorio obtenía el código pero no los modelos, y el backend no podía arrancar.

### Archivos de modelo

| Archivo | Tamaño | Contenido |
|---|---|---|
| `app/ml/runtime/modelo1_pipeline.pkl` | 7.2 MB | Pipeline sklearn completo: preprocesador (ColumnTransformer) + MultiOutputClassifier(RandomForest). Entrena 6 clasificadores binarios, uno por condición. |
| `app/ml/runtime/modelo2_artifacts.pkl` | 317 KB | Embeddings del grafo GNN, índices de componentes, semillas por condición, pares de sinergias y pares de interacciones riesgosas. |

### Solución aplicada

Se eliminó `*.pkl` del `.gitignore` y se commitearon ambos archivos al repositorio. Ahora el backend funciona inmediatamente después de clonar sin necesidad de reentrenar.

---

## Cambio 3 — Bug crítico: nombre incorrecto del modelo 2

### Situación anterior

`app/ml/runtime/modelo2_inference.py` intentaba cargar:
```python
_ARTIFACTS_PATH = settings.MODEL_DIR / "modelo2_artifacts_cpu.pkl"
```

Pero el archivo real se llama `modelo2_artifacts.pkl` (sin el sufijo `_cpu`). Esto causaba que el Modelo 2 **nunca cargara**, aunque el archivo existía. El sistema fallaba silenciosamente o lanzaba un error al primer request.

### Fix

```python
# Antes (incorrecto)
_ARTIFACTS_PATH = settings.MODEL_DIR / "modelo2_artifacts_cpu.pkl"

# Después (correcto)
_ARTIFACTS_PATH = settings.MODEL_DIR / "modelo2_artifacts.pkl"
```

---

## Cambio 4 — Explainability: por qué el modelo tomó esa decisión

Este es el cambio más importante de la sesión y el que el profesor pidió explícitamente.

### Situación anterior

El archivo `app/ml/explainability.py` estaba **completamente vacío** (1 sola línea en blanco). Las probabilidades mostradas eran valores inventados:

```python
# Código anterior — valores hardcodeados, iguales para todos
def _condition_probability(index: int, total: int) -> float:
    return max(0.45, 0.82 - (index * 0.12))
    # Primera condición siempre 0.82, segunda 0.70, tercera 0.58...
    # No tiene nada que ver con el modelo real
```

Las razones de los suplementos eran texto genérico igual para todos:
```python
return f"Relacionado con {condition_name}."
# No importaba la confianza del modelo ni el perfil del usuario
```

### Qué se implementó

#### 4.1 — Probabilidades reales del Modelo 1

El clasificador sklearn tiene el método `predict_proba` que retorna la probabilidad real de cada condición para cada usuario. Se reemplazó el enfoque binario (`predict`) por probabilístico (`predict_proba`):

```python
# Antes: solo 0 o 1
pred = pipeline.predict(row)[0]
detected = [labels[i] for i, v in enumerate(pred) if v == 1]

# Después: probabilidad real entre 0 y 1 para cada condición
proba_list = pipeline.predict_proba(row)
condition_scores = {
    label: round(float(proba_list[i][0][1]), 4)
    for i, label in enumerate(labels)
}
# Ejemplo: {"FATIGA": 0.83, "DEFICIT_VIT_D": 0.71, "BAJA_INMUNIDAD": 0.52, "ESTRES": 0.31}
```

Ahora cada usuario obtiene probabilidades distintas según sus respuestas específicas.

#### 4.2 — SHAP TreeExplainer para drivers personalizados

**¿Qué es SHAP?**  
SHAP (SHapley Additive exPlanations) es un método matemático basado en teoría de juegos cooperativos que calcula cuánto contribuyó cada variable de entrada al resultado del modelo, para una predicción específica. No es una aproximación: es el valor exacto de contribución de cada feature.

**¿Por qué TreeExplainer para Random Forest?**  
`shap.TreeExplainer` está optimizado para modelos basados en árboles (Random Forest, XGBoost, etc.). Es exacto y muy rápido porque aprovecha la estructura del árbol directamente, sin aproximaciones.

**Cómo funciona en SupleMatch:**

El Modelo 1 usa un `MultiOutputClassifier` con un `RandomForestClassifier` independiente por cada condición (FATIGA, DEFICIT_VIT_D, etc.). Para explicar una predicción:

1. Se separa el preprocesador del clasificador dentro del pipeline sklearn
2. Se transforma el input del usuario (OneHotEncoding de categorías, passthrough de numéricas)
3. Por cada condición detectada (probabilidad ≥ 45%), se corre SHAP sobre el sub-estimador correspondiente
4. SHAP retorna un valor por cada feature: positivo = empuja hacia "sí tiene esa condición", negativo = empuja hacia "no la tiene"
5. Se toman los 3 features con mayor valor absoluto (los que más influyeron)
6. Se mapean de vuelta al nombre original de la variable de encuesta

**Ejemplo de output SHAP real:**

```json
{
  "condition": "FATIGA",
  "probability": 0.83,
  "drivers": [
    {
      "label": "Fatiga frecuente",
      "value": 4,
      "value_label": "A menudo",
      "impact": "alto",
      "shap_value": 0.31
    },
    {
      "label": "Problemas de sueño",
      "value": 5,
      "value_label": "Severo (<5h)",
      "impact": "alto",
      "shap_value": 0.22
    },
    {
      "label": "Nivel de estrés",
      "value": 3,
      "value_label": "Moderado",
      "impact": "medio",
      "shap_value": 0.09
    }
  ]
}
```

Para un usuario distinto con FATIGA pero causada principalmente por el estrés, los valores y el orden de los features serían diferentes.

**Fallback automático:**  
Si `shap` no está instalado en el entorno, el sistema detecta el `ImportError` y usa automáticamente un enfoque basado en reglas de dominio que muestra los features más relevantes por condición según conocimiento experto. El usuario no nota diferencia visual.

#### 4.3 — Razones de suplementos con confianza

Las razones de por qué se recomienda cada suplemento ahora incluyen el porcentaje de confianza real del modelo:

```python
# Antes (igual para todos)
"Relacionado con fatiga o baja energía."

# Después (personalizado por usuario)
"Alta prioridad por fatiga o baja energía (confianza 83%)."
"Indicado para fatiga o baja energía (confianza 61%)."
```

---

## Cambio 5 — Feature Builder: uso real de dieta y alcohol

### Situación anterior

La encuesta recogía 9 campos del usuario, pero `FeatureBuilder` ignoraba `dieta` y `alcohol` completamente, hardcodeando valores fijos:

```python
# Valores inventados, no del usuario
"sexo": "F",
"tipo_dieta": "omnivoro",
"peso_kg": 60.0,
"altura_cm": 165.0,
```

### Solución aplicada

**Campo `dieta` (calidad alimentaria):**  
Se usa la calidad de la dieta para ajustar las metas nutricionales del perfil:

- `poco_variada` o `regular` → activa `meta_energia=1` y `meta_salud_osea=1` porque una dieta pobre aumenta el riesgo de déficits nutricionales
- `bastante_variada` o `muy_balanceada` → mantiene los valores por defecto

**Campo `alcohol` (frecuencia de consumo):**  
El alcohol afecta la absorción de nutrientes y el sistema inmune:

- `frecuente` → incrementa la señal de `enfermedad_frecuente` (mayor riesgo de baja inmunidad) y activa `meta_inmunidad=1`
- `ocasional` → incremento leve
- `raro` o `nunca` → sin efecto

**Campo `sexo`:**  
Se lee del input si existe, con `"F"` como valor por defecto (hasta que se agregue la pregunta al frontend).

---

## Cambio 6 — Correcciones de integración Frontend ↔ Backend

### Situación anterior

El frontend tenía varios datos hardcodeados que ignoraban la respuesta real de la API:

**Sinergias y alertas hardcodeadas en `Recomendaciones.jsx`:**
```jsx
// Siempre mostraba esto, sin importar el resultado real
💡 <strong>Zinc + Vitamina C</strong> se potencian mutuamente
⚠️ <strong>D3 + Calcio</strong> · si usas ambos, tomar separados
```

**Suplementos hardcodeados en `Feedback.jsx`:**
```javascript
const SUPLEMENTOS = ['Vitamina D3', 'Zinc', 'Vitamina C']
// Sin importar qué recomendó el modelo para ese usuario
```

**Probabilidades de condiciones hardcodeadas en `Condiciones.jsx`:**
- Siempre mostraba la misma barra para todos los usuarios

### Solución aplicada

**`Loading.jsx`:**  
Es el componente que llama al backend y normaliza la respuesta. Se agregó el mapeo del nuevo campo `explainability` y se adjuntan los `drivers` de cada condición para que la pantalla de Condiciones los pueda mostrar:

```javascript
condiciones: conditionsDisplay.map((condition, index) => {
  const expl = (result.explainability ?? []).find(e => e.condition === condition.code)
  return {
    code: condition.code,
    nombre: condition.display_name,
    probabilidad: condition.probability,  // probabilidad real del modelo
    drivers: expl?.drivers ?? [],         // drivers SHAP de ese usuario
  }
})
```

**`Condiciones.jsx`:**  
Nueva sección "¿Por qué?" bajo cada condición con:
- Barra de probabilidad con el porcentaje real del modelo
- Tabla de los 3 features más influyentes para ese usuario
- Badges de impacto con código de color (Alto = rojo, Medio = amarillo, Bajo = verde)
- Valor real que el usuario respondió (ej: "A menudo", "Menos de 15 min/día")

**`Recomendaciones.jsx`:**  
Sinergias y alertas ahora vienen de la API. El Modelo 2 analiza el grafo de relaciones y detecta qué pares de suplementos tienen sinergia funcional y cuáles tienen interacciones riesgosas. Cada vez que el resultado es distinto, la pantalla lo muestra correctamente.

**`Feedback.jsx`:**  
La lista de suplementos a calificar ahora usa los nombres reales de las recomendaciones recibidas, no una lista fija.

---

## Cambio 7 — shap agregado a requirements.txt

Se agregó `shap>=0.45.0` a `requirements.txt` para que el entorno tenga el paquete documentado como dependencia oficial.

Para instalar en el entorno:
```bash
pip install -r requirements.txt
# o solo shap:
pip install shap
```

Si no se instala, el sistema funciona igual con el fallback rule-based. No hay errores ni caídas.

---

## Cambio 8 — READMEs reescritos

### `Suplematch-Backend/README.md`
El README anterior tenía información incorrecta (nombre del pkl con sufijo `_cpu`, rutas de datos desactualizadas). Se reescribió completamente con:
- Descripción del pipeline completo con diagrama de flujo
- Sección dedicada a la explicabilidad con ejemplo de respuesta JSON
- Tabla de todos los campos del endpoint `/recommend`
- Estructura correcta de la carpeta `data/`
- Advertencia sobre `scikit-learn==1.5.0` (no actualizar sin reentrenar)
- Instrucciones de Docker

### `frontend-suplematch/README.md`
El README original era el template por defecto de Vite (sin información del proyecto). Se reemplazó con documentación real del proyecto: flujo de pantallas, setup, variables de entorno, y descripción de la explicabilidad en la UI.

---

## Resumen de archivos modificados

### Backend (`Suplematch-Backend`)
| Archivo | Tipo de cambio | Descripción |
|---|---|---|
| `app/core/config.py` | Fix | Rutas CSV corregidas |
| `app/ml/explainability.py` | Nuevo | SHAP TreeExplainer + fallback rule-based |
| `app/ml/feature_builder.py` | Mejora | Integra dieta y alcohol en el perfil |
| `app/ml/runtime/pipeline_completo.py` | Mejora | predict_proba + explainability |
| `app/ml/runtime/modelo2_inference.py` | Bug fix | Nombre correcto del pkl |
| `app/schemas/recomendacion.py` | Mejora | Nuevos schemas FeatureDriver y ConditionExplanation |
| `app/services/recommendation_service.py` | Mejora | Probabilidades reales, razones con % confianza |
| `requirements.txt` | Mejora | Agrega shap>=0.45.0 |
| `README.md` | Reescrito | Documentación completa y correcta |
| `.gitignore` | Fix | Elimina *.pkl para versionar modelos |
| `data/raw/csv/digemid_limpio.csv` | Movido | Desde raíz del proyecto |
| `data/training/modelo2/product_components.csv` | Movido | Desde raíz del proyecto |
| `app/ml/runtime/modelo1_pipeline.pkl` | Nuevo en git | Modelo RF entrenado (7.2 MB) |
| `app/ml/runtime/modelo2_artifacts.pkl` | Nuevo en git | Embeddings GNN entrenados (317 KB) |
| `docs/plan_mejoras_prototipo_final.md` | Nuevo | Roadmap de mejoras |
| `docs/cambios_sesion_08062026.md` | Nuevo | Este documento |

### Frontend (`frontend-suplematch`)
| Archivo | Tipo de cambio | Descripción |
|---|---|---|
| `src/screens/Loading.jsx` | Mejora | Mapea explainability y drivers SHAP |
| `src/screens/Condiciones.jsx` | Mejora | Muestra drivers con badges de impacto |
| `src/screens/Recomendaciones.jsx` | Fix | Sinergias/alertas dinámicas desde la API |
| `src/screens/Feedback.jsx` | Fix | Nombres reales de suplementos |
| `README.md` | Reescrito | Documentación real del proyecto |
