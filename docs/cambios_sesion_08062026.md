# Cambios realizados — Sesión 08/06/2026

## 1. Reorganización de archivos CSV

### Problema
Los archivos CSV estaban sueltos en la raíz del proyecto y del backend, sin una ubicación coherente.

### Lo que se hizo
| Archivo original | Nueva ubicación |
|---|---|
| `Proyecto/digemid_limpio(1).csv` | `Suplematch-Backend/data/raw/csv/digemid_limpio.csv` |
| `Proyecto/product_components(1).csv` | `Suplematch-Backend/data/training/modelo2/product_components.csv` |
| `Suplematch-Backend/digemid_limpio.csv` (duplicado) | Eliminado |
| `Suplematch-Backend/product_components.csv` (duplicado) | Eliminado |

### Config actualizado
`app/core/config.py` — rutas corregidas para apuntar a las nuevas ubicaciones:
```python
DIGEMID_CSV_PATH = BASE_DIR / "data/raw/csv/digemid_limpio.csv"
PRODUCT_COMPONENTS_CSV_PATH = BASE_DIR / "data/training/modelo2/product_components.csv"
```

---

## 2. Modelos pkl versionados en git

### Problema
`*.pkl` estaba en `.gitignore`, por lo que los modelos entrenados no se subían al repo. Cualquier clon del repo quedaba sin modelos.

### Lo que se hizo
- Se eliminó `*.pkl` del `.gitignore`
- Se commitearon los modelos entrenados:
  - `app/ml/runtime/modelo1_pipeline.pkl` (7.2 MB — Random Forest multilabel)
  - `app/ml/runtime/modelo2_artifacts.pkl` (317 KB — embeddings GNN)

---

## 3. Bug fix: nombre incorrecto del pkl del Modelo 2

### Problema
`app/ml/runtime/modelo2_inference.py` intentaba cargar `modelo2_artifacts_cpu.pkl` pero el archivo se llama `modelo2_artifacts.pkl`. El Modelo 2 nunca cargaba.

### Fix
```python
# Antes
_ARTIFACTS_PATH = settings.MODEL_DIR / "modelo2_artifacts_cpu.pkl"

# Después
_ARTIFACTS_PATH = settings.MODEL_DIR / "modelo2_artifacts.pkl"
```

---

## 4. Explainability real con SHAP

### Problema
`app/ml/explainability.py` estaba completamente vacío. Las probabilidades de condición eran valores hardcodeados (`0.82 - index * 0.12`), no salían del modelo.

### Lo que se hizo

#### `app/ml/explainability.py` (implementado desde cero)
- **`get_condition_scores`**: usa `predict_proba` del pipeline sklearn para obtener probabilidades reales por condición, distintas para cada usuario.
- **`_shap_drivers`**: corre `shap.TreeExplainer` sobre cada sub-estimador Random Forest del `MultiOutputClassifier`. Extrae los top-3 features por valor absoluto de SHAP, resolviendo nombres de features post-`ColumnTransformer` de vuelta a las variables originales de la encuesta.
- **`_rule_based_drivers`**: fallback automático si `shap` no está instalado. Usa mapeo por reglas de dominio.
- **`build_explainability`**: intenta SHAP, cae al fallback silenciosamente si falla.

#### `app/ml/runtime/pipeline_completo.py`
- `predecir_condicion` ahora usa `predict_proba` en lugar de `predict`
- Retorna `(condiciones, condition_scores, row_df)` — las probabilidades reales y el DataFrame para SHAP
- `pipeline_vitaminas` agrega `condition_scores` y `explainability` al resultado

#### `app/schemas/recomendacion.py`
Nuevos schemas:
```python
class FeatureDriver(BaseModel):
    feature: str
    label: str
    value: Any
    value_label: str
    impact: str          # "alto" | "medio" | "bajo"
    shap_value: float    # contribución real del feature al score (si SHAP disponible)

class ConditionExplanation(BaseModel):
    condition: str
    probability: float
    drivers: list[FeatureDriver]
```
`RecommendationResponse` ahora incluye `explainability: list[ConditionExplanation]`.

#### `app/services/recommendation_service.py`
- `_normalize_conditions_display` ahora acepta `condition_scores` y usa probabilidades reales
- `_recommendation_reason_with_score` genera razones con porcentaje de confianza:
  - Ej: *"Alta prioridad por fatiga o baja energía (confianza 83%)."*
- `_normalize_recommendations` pasa el score de condición para enriquecer la razón por suplemento

---

## 5. Feature builder: integración de dieta y alcohol

### Problema
`FeatureBuilder` hardcodeaba `sexo="F"`, y los campos `dieta` y `alcohol` de la encuesta se recogían pero nunca llegaban al modelo.

### Lo que se hizo en `app/ml/feature_builder.py`
- **`dieta`**: calidad de dieta `poco_variada` o `regular` activa `meta_energia` y `meta_salud_osea`
- **`alcohol`**: consumo frecuente incrementa `enfermedad_frecuente` y activa `meta_inmunidad`
- **`sexo`**: se lee del campo `encuesta.sexo` si existe (con default `"F"`)

---

## 6. Correcciones de integración frontend ↔ backend

### Problema
Varios campos de la API no se mostraban porque el frontend usaba nombres distintos a los que retornaba el backend. Las sinergias y alertas estaban hardcodeadas en el JSX.

### Cambios en el frontend

#### `src/screens/Loading.jsx`
- Mapea el nuevo campo `explainability` de la API
- Adjunta `drivers` de SHAP a cada condición normalizada para que `Condiciones.jsx` los pueda mostrar
- Agrega `explainability: result.explainability ?? []` al resultado normalizado

#### `src/screens/Condiciones.jsx`
Nueva sección **"¿Por qué?"** bajo cada condición detectada:
- Muestra los top-3 features que más influyeron en esa condición para ese usuario
- Badges de impacto con código de color: 🔴 Alto · 🟡 Medio · 🟢 Bajo
- Muestra el valor real que respondió el usuario (ej: "Fatiga frecuente → A menudo")
- Barra de probabilidad con porcentaje real del modelo

#### `src/screens/Recomendaciones.jsx`
- Sinergias y alertas ahora son dinámicas desde `apiResult.sinergias` y `apiResult.alertas`
- Ya no son strings hardcodeados — vienen del análisis real del grafo GNN

#### `src/screens/Feedback.jsx`
- Lista de suplementos para calificar viene de `apiResult.recomendaciones` (nombres reales)
- Antes estaba hardcodeada como `['Vitamina D3', 'Zinc', 'Vitamina C']`

---

## 7. shap agregado a requirements.txt

```
shap>=0.45.0
```

Si no está instalado, el sistema usa el fallback rule-based automáticamente sin errores.

Para instalar:
```bash
pip install shap
```

---

## 8. READMEs actualizados

### `Suplematch-Backend/README.md`
- Documentación completa del pipeline de recomendación
- Sección de explainability con ejemplo de respuesta JSON con SHAP values
- Tabla de campos del endpoint `/recommend`
- Estructura correcta de la carpeta `data/`
- Notas de versión: advertencia sobre `scikit-learn==1.5.0`
- Fix: nombre correcto del pkl (`modelo2_artifacts.pkl`, sin sufijo `_cpu`)

### `frontend-suplematch/README.md`
- Reemplazó el README default de Vite
- Documenta el flujo completo de pantallas
- Explica cómo funciona la explicabilidad en la UI
- Setup, variables de entorno y conexión con el backend

---

## 9. Plan de mejoras

Creado `docs/plan_mejoras_prototipo_final.md` con:
- Diagnóstico del estado anterior (bugs, campos ignorados, hardcodes)
- Roadmap priorizado para la entrega del 10/06/2026
- Descripción técnica de cada mejora con ejemplos de código

---

## Resumen de archivos modificados

### Backend
| Archivo | Tipo |
|---|---|
| `app/core/config.py` | Fix rutas CSV |
| `app/ml/explainability.py` | Nuevo — SHAP + fallback |
| `app/ml/feature_builder.py` | Integra dieta y alcohol |
| `app/ml/runtime/pipeline_completo.py` | predict_proba + explainability |
| `app/ml/runtime/modelo2_inference.py` | Fix nombre pkl |
| `app/schemas/recomendacion.py` | Nuevos schemas explainability |
| `app/services/recommendation_service.py` | Probabilidades reales, razones con confianza |
| `requirements.txt` | Agrega shap>=0.45.0 |
| `README.md` | Reescrito |
| `.gitignore` | Elimina `*.pkl` |
| `docs/plan_mejoras_prototipo_final.md` | Nuevo |
| `docs/cambios_sesion_08062026.md` | Nuevo (este archivo) |

### Frontend
| Archivo | Tipo |
|---|---|
| `src/screens/Loading.jsx` | Mapea explainability y drivers |
| `src/screens/Condiciones.jsx` | Muestra drivers SHAP con badges |
| `src/screens/Recomendaciones.jsx` | Sinergias/alertas dinámicas |
| `src/screens/Feedback.jsx` | Nombres reales de suplementos |
| `README.md` | Reescrito |
