# Cambios 3 — Sesión completa 08/06/2026 (tarde)

Mejoras de UX, navegación, visualización y persistencia implementadas sobre el frontend y el backend de SupleMatch. Esta sesión se centró en pulir la experiencia del usuario para la entrega del prototipo final.

---

## Backend

### 1. Bloqueo comercial en perfiles medicos criticos

**Archivo:** `Suplematch-Backend/app/services/recommendation_service.py`

Nota actualizada: la eliminacion del bloqueo comercial fue revertida por safety. Los perfiles con `safety_level == "medical_review_required"` deben mantener `commercial_recommendations_blocked = True` y no deben recibir productos comerciales ni packs comprables hasta revision profesional.

```python
commercial_recommendations_blocked = safety_level == "medical_review_required"
if not commercial_recommendations_blocked:
    recommendations = _attach_products_to_recommendations(...)
    packs_ranked = _attach_products_to_packs(...)
```

El frontend puede mostrar recomendaciones de componentes, pero debe ocultar enlaces de compra cuando `commercial_recommendations_blocked` sea verdadero.

---

### 2. Traducción de nombres de suplementos al español

**Archivo:** `Suplematch-Backend/app/services/recommendation_service.py`

Los nombres de suplementos venían en inglés desde el catálogo (ej: `"Folic Acid"`, `"Cobalamin"`). Se agregó un diccionario `COMPONENT_NAME_ES` con ~50 traducciones y la función `_translate_component_name(name)` que se aplica a todos los campos `display_name` de recomendaciones y componentes del pack.

```python
COMPONENT_NAME_ES = {
    'Vitamin D': 'Vitamina D',
    'Vitamin B12': 'Vitamina B12',
    'Folic Acid': 'Ácido Fólico',
    'Iron': 'Hierro',
    'Magnesium': 'Magnesio',
    # ... ~50 entradas
}
```

---

### 3. Expansión de CONDITION_LABELS

**Archivo:** `Suplematch-Backend/app/services/recommendation_service.py`

El diccionario `CONDITION_LABELS` que traduce códigos internos del modelo a nombres legibles en español se amplió de 6 a 13 condiciones, cubriendo las nuevas etiquetas del Modelo 1:

- `DEFICIT_B12` → "Déficit de Vitamina B12"
- `DEFICIT_HIERRO` → "Déficit de Hierro"
- `DEFICIT_MAGNESIO` → "Déficit de Magnesio"
- `FATIGA_CRONICA` → "Fatiga Crónica"
- `RENDIMIENTO_DEPORTIVO` → "Rendimiento Deportivo"
- `SALUD_OSEA` → "Salud Ósea"
- `SALUD_COGNITIVA` → "Salud Cognitiva"
- `SALUD_CAPILAR` → "Salud Capilar"

---

### 4. Expansión de CONDITION_FEATURE_MAP en explainability

**Archivo:** `Suplematch-Backend/app/ml/explainability.py`

El `CONDITION_FEATURE_MAP` (que mapea cada condición a los features relevantes para SHAP) solo tenía 6 condiciones, por lo que la mayoría de condiciones caía al fallback rule-based sin drivers reales. Se amplió a 13 condiciones con sus features y `VALUE_LABELS` correspondientes.

También se añadieron nuevas entradas a `VALUE_LABELS`:
- `dolor_muscular`, `caida_cabello`, `calambres`
- `meta_rendimiento`, `meta_cognitivo`, `meta_belleza`

Resultado: ahora prácticamente todas las condiciones detectadas muestran drivers SHAP personalizados en lugar del fallback genérico.

---

## Frontend

### 5. Exposición pública del frontend

Nota actualizada: la exposicion publica no debe depender de ngrok manual. Para staging/demo se debe usar Cloudflare Tunnel gestionado por Docker Compose, con token rotado en `.env.staging` y sin secretos en argumentos de procesos.

```bash
docker compose --env-file .env.staging -f docker-compose.staging.yml --profile tunnel up -d --build
```

El hostname publico se configura en Cloudflare con dos rutas internas del mismo tunnel:

```txt
/api/* -> http://backend:8000
/      -> http://frontend:80
```

La ruta `/api/*` debe quedar antes que `/`. El proxy `/api` del frontend queda como fallback/local.

El comando de Cloudflare tipo `docker run ... --token TOKEN` se tradujo a Compose usando `CLOUDFLARE_TUNNEL_TOKEN`, para que el token no aparezca en argumentos de proceso.

### 5.1 Auth con refresh tokens rotativos

**Archivos:** `app/domains/auth/servicio_autenticacion.py`, `app/domains/auth/rutas.py`, `app/db/models.py`

Se agrego tabla `refresh_tokens`, migracion Alembic y endpoints:

- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/logout-all`

Los refresh tokens se guardan hasheados, expiran por `REFRESH_TOKEN_EXPIRE_DAYS`, se rotan en cada refresh y se revocan al logout, reset o cambio de contrasena.

### 5.2 Loki para logs operativos

**Archivos:** `docker-compose.monitoring.yml`, `monitoring/loki.yml`, `monitoring/promtail.yml`

Se agrego Loki y Promtail al stack de monitoreo. Promtail lee logs Docker, los etiqueta por servicio y los envia a Loki. Grafana queda con datasource `SupleMatch Loki`.

---

### 6. Filtro GOAL_CODES: separar déficits de objetivos de salud

**Archivos:** `src/screens/Condiciones.jsx`, `src/screens/Historial.jsx`

El Modelo 1 detecta tanto condiciones de salud reales (déficits) como objetivos del usuario (rendimiento deportivo, salud capilar, etc.). Mostrarlos juntos como "condiciones detectadas" era confuso para el usuario.

Se definió `GOAL_CODES` como un conjunto de códigos que representan objetivos (no déficits) y se filtra en todas las pantallas que los muestran:

```js
const GOAL_CODES = new Set([
  'RENDIMIENTO_DEPORTIVO',
  'SALUD_CAPILAR',
  'SALUD_CAPILAR_PIEL',
  'SALUD_COGNITIVA',
  'SALUD_OSEA'
])
const deficits = condiciones.filter(c => !GOAL_CODES.has(c.code))
```

---

### 7. Reestructuración completa de Recomendaciones

**Archivo:** `src/screens/Recomendaciones.jsx`

La pantalla anterior estaba muy cargada visualmente. Se simplificó:

- Las tarjetas individuales de suplementos son el contenido principal
- El pack de productos se movió a una sección colapsable al final
- Se eliminó el bloque "Uso responsable" (era redundante y largo)
- El aviso de seguridad médica se condensó a un banner compacto de una línea
- Se agregó `packOpen` state para controlar el acordeón del pack

---

### 8. Simplificación de la pantalla Loading

**Archivo:** `src/screens/Loading.jsx`

- Se eliminó el `setTimeout(run, 1200)` que añadía 1.2 s de espera artificial
- Se eliminaron los checkmarks falsos que simulaban pasos de análisis
- UI reducida a: spinner + "Analizando tu perfil..." + "Esto puede tomar unos segundos"
- La llamada al backend es inmediata

---

### 9. Mejoras de flujo en la encuesta

**Archivo:** `src/screens/Encuesta.jsx`

**Editar desde el resumen:**
Al pulsar "editar" en el resumen final, el botón `←` y el botón "Siguiente" devuelven al resumen en lugar de avanzar linearmente. Se implementó mediante el estado `editingFromSummary`.

**Modal de confirmación de salida:**
Al intentar salir en el paso 0 (primer paso) de la encuesta, aparece un modal de confirmación: "¿Salir de la evaluación?" con botones Cancelar y Salir.

**Validación embarazo/lactancia:**
Si el usuario selecciona sexo masculino, la opción "Embarazo o lactancia" se oculta automáticamente en la pregunta de condiciones de seguridad. Si ya estaba seleccionada, se limpia del estado.

```js
if (q.key === 'sexo' && value === 'masculino') {
  next.condiciones_seguridad = (next.condiciones_seguridad || [])
    .filter(item => item !== 'embarazo_lactancia')
}
```

---

### 10. Logo y acceso al historial sin login

**Archivo:** `src/screens/Landing.jsx`

- El logo de 💊 se reemplazó por un cuadrado verde con "SM" en texto blanco
- El botón "Historial" ahora lleva siempre a la pantalla de historial sin requerir autenticación

---

### 11. Historial con última sesión local

**Archivo:** `src/screens/Historial.jsx`

La pantalla de historial ya no requiere cuenta para mostrar información. Lee el último resultado desde `localStorage` (`suplematch_last_result`) y muestra:

- Fecha y hora de la última evaluación
- Condiciones detectadas (filtradas por GOAL_CODES)
- Hasta 4 suplementos recomendados
- Botón "Ver resultados →"

La sección de cuenta aparece como un card secundario invitando a iniciar sesión para guardar historial entre dispositivos.

---

### 12. Guardado de resultados en localStorage desde App

**Archivo:** `src/App.jsx`

Se reemplazó `setApiResult` por `saveApiResult`, que además de actualizar el estado de React guarda el resultado en localStorage:

```js
function saveApiResult(result) {
  setApiResult(result)
  try {
    localStorage.setItem('suplematch_last_result', JSON.stringify({
      result,
      savedAt: new Date().toISOString()
    }))
  } catch {}
}
```

---

### 13. Botones de navegación hacia atrás

**Archivos:** `src/screens/Recomendaciones.jsx`, `src/screens/Condiciones.jsx`

- **Recomendaciones:** botón `← Volver` en la cabecera que navega a la pantalla anterior (ver punto 17 sobre `prevScreen`)
- **Condiciones:** enlace `← Modificar respuestas` debajo del botón principal que regresa a la encuesta

---

### 14. Persistencia de respuestas de la encuesta

**Archivo:** `src/screens/Encuesta.jsx`

Las respuestas sobreviven recargas de página:

- **Lectura:** `useState` inicializa con `localStorage.getItem('suplematch_encuesta_answers')`
- **Escritura:** función `persistAnswers()` envuelve todas las llamadas a `setAnswers` y guarda en localStorage simultáneamente
- **Limpieza:** al confirmar y enviar al backend, se ejecuta `localStorage.removeItem('suplematch_encuesta_answers')`

---

### 15. Modal "¿Continuar evaluación guardada?"

**Archivo:** `src/screens/Encuesta.jsx`

Si el usuario abre la encuesta con respuestas guardadas en localStorage, aparece un modal con dos opciones:

- **Continuar** → cierra el modal y retoma desde donde estaba
- **Empezar de cero** → borra el localStorage y resetea `answers` a `{}`

---

### 16. Botón "Nueva evaluación" en Historial

**Archivo:** `src/screens/Historial.jsx`

Junto al botón "Ver resultados →" se añadió un botón secundario "Nueva evaluación" que limpia `suplematch_encuesta_answers` de localStorage y navega a la encuesta con estado limpio.

---

### 17. Historial de navegación (`prevScreen`) en App

**Archivo:** `src/App.jsx`

Se agregó `prevScreen` state y se modificó `goTo` para registrar la pantalla anterior en cada navegación:

```js
const goTo = useCallback((s) => {
  setScreen(prev => { setPrevScreen(prev); return s })
}, [])
```

`prevScreen` se pasa como prop a todas las pantallas. El botón `← Volver` de Recomendaciones lo usa para volver a la pantalla correcta:

- Llegando desde **Condiciones** → vuelve a Condiciones
- Llegando desde **Historial** → vuelve a Historial

---

### 18. Vínculo condición → suplemento en cada tarjeta

**Archivos:** `src/screens/Loading.jsx`, `src/screens/Recomendaciones.jsx`

El backend ya devuelve `condition_display` (nombre legible de la condición que originó cada recomendación). Ahora se mapea en `Loading.jsx` y se muestra en la tarjeta de cada suplemento como un chip verde:

```
Para: Déficit de Vitamina B12
```

Solo aparece cuando el campo está presente; los suplementos de soporte general no muestran chip.

---

### 19. Botón "Ir al menú principal" en Recomendaciones

**Archivo:** `src/screens/Recomendaciones.jsx`

Enlace discreto al final de la pantalla, debajo del botón de feedback, que lleva directamente a Landing. Útil especialmente cuando el usuario llega desde Historial.

---

### 20. Animación de transición entre pantallas

**Archivo:** `src/index.css`

Se actualizó el `@keyframes fadeIn` de desvanecimiento vertical a slide horizontal, más natural en navegación tipo app móvil. Se dispara automáticamente en cada cambio de pantalla gracias a `key={screen}` en `App.jsx`.

```css
@keyframes fadeIn {
  from { opacity: 0; transform: translateX(18px); }
  to   { opacity: 1; transform: translateX(0); }
}
```

---

## Resumen de archivos modificados

### Backend
| Archivo | Cambio |
|---|---|
| `app/services/recommendation_service.py` | Sin bloqueo comercial, traducción ES, CONDITION_LABELS ampliado |
| `app/ml/explainability.py` | CONDITION_FEATURE_MAP ampliado de 6 a 13 condiciones |

### Frontend
| Archivo | Cambio |
|---|---|
| `src/App.jsx` | `saveApiResult` con localStorage + `prevScreen` tracking |
| `src/index.css` | Animación slide horizontal |
| `src/screens/Loading.jsx` | Sin delay artificial, mapeo `condicion_display` |
| `src/screens/Landing.jsx` | Logo "SM", historial sin auth |
| `src/screens/Encuesta.jsx` | Persistencia localStorage, modal continuar/reiniciar, editar desde resumen, modal salida, filtro embarazo |
| `src/screens/Condiciones.jsx` | Filtro GOAL_CODES, botón "← Modificar respuestas" |
| `src/screens/Recomendaciones.jsx` | Reestructuración completa, botón volver inteligente, chip condición, botón menú principal |
| `src/screens/Historial.jsx` | Última sesión desde localStorage, botón "Nueva evaluación" |
