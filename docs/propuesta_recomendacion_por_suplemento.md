# Propuesta: recomendar suplementos individuales con calificación de 1 a 5 estrellas

Fecha: 2026-10-24. Estado: **evaluación, no implementado**. Reemplazaría los packs (grupos de 3 suplementos) por una
lista de suplementos individuales, cada uno calificable por el usuario con 1 a 5 estrellas.

## Por qué

Lo que se midió el 2026-10-24 (`tests/integration/test_feedback_ranking.py`, `scripts/validation/validar_calidad_recomendaciones.py`):

1. **El feedback por pack es muy escaso y muy sensible a la vez.** El `pack_key` es un hash de los 3 componentes:
   cada combinación distinta es un ítem nuevo sin historia. Con los modelos reales, **un solo voto negativo** saca al
   pack principal del primer puesto (score_feedback 0.70 → 0.62), porque los packs candidatos tienen scores casi
   iguales. Un voto de un usuario cambia el orden para todos los usuarios con ese pack.
2. **Un voto a un pack no dice qué suplemento falló.** Si a alguien le cae mal el magnesio, "Vitamina D + Calcio +
   Magnesio" baja entero, y la vitamina D pierde puntos que no merecía.
3. **Los packs ya no cubren a todos.** En 5 de 15 escenarios no hay pack comercial por diseño (solo prioridades
   blandas o perfil crítico), y antes del arreglo de hoy esos perfiles compartían un pack vacío (`pack_d41d8cd98f`,
   md5 de la cadena vacía) que mezclaba su feedback.
4. **La API ya calcula todo por suplemento.** `recommendations[]` trae cada componente con score, evidencia,
   condición, productos y reglas de interacción; los packs son una combinación posterior (`feedback_reranker._make_candidate_packs`).
   Los eventos (`recommendation_events`) ya guardan `component_id` y `position`.

## Qué cambiaría

| Pieza | Hoy | Propuesta |
|---|---|---|
| Unidad que se ordena | Pack de 3 (`packs_ranked`) | Suplemento (`recommendations[]`) |
| Calificación | 1 rating por recomendación (3 opciones: 5/3/1) | 1-5 estrellas por suplemento, opcional, solo de los que vio |
| Clave de feedback | `pack_key\|COND_A+COND_B+COND_C` | `component_id\|condición que lo motivó` (la condición de la recomendación) |
| Recompensa | `recompensa.reward(rating, compra, sigue a 30 días, beneficio)` | La misma fórmula, por suplemento |
| Score final | 0.30 gnn + 0.20 cobertura + 0.15 productos + 0.15 feedback + ... (por pack) | score del Modelo 2 + evidencia + feedback del suplemento (ver reglas abajo) |
| Interacciones | Se evalúan dentro del pack | Se evalúan entre los suplementos que el usuario elija (ya existe `alertas`) |

### Reglas que deberían acompañar el cambio

- **Más inercia que hoy.** Prior bayesiano con más pseudo-votos (p. ej. `m = 20` en lugar de 8) y un mínimo de votos
  antes de mover el orden (p. ej. 10 por clave), para que un usuario no reordene la lista de todos.
- **El feedback ordena dentro del mismo nivel de evidencia y seguridad, nunca por encima.** Un suplemento con
  evidencia débil y muchas estrellas no debe pasar a uno con evidencia fuerte para el déficit detectado, y el
  feedback nunca levanta un bloqueo de seguridad.
- **Corrección del sesgo de posición.** Lo primero se ve y se califica más; `recommendation_events.position` ya
  permite ponderar por impresiones.
- **Sesgo de selección.** Califica sobre todo quien compró. Separar "calificó sin comprar" de "compró y siguió a 30
  días" en la recompensa (la fórmula actual ya pesa compra y retención).

## Impacto estimado

Backend (17 archivos usan packs):

- Migración: columna `component_id` + `rating` por ítem (tabla `recommendation_item_feedback` o filas en
  `recommendation_feedback` con `component_id`). `recommended_packs` queda como histórico.
- `FeedbackInput`: lista `item_ratings: [{component_id, rating, purchased?, still_taking_30d?}]`; mantener `rating`
  global un tiempo por compatibilidad.
- `RecommendationMetricsRepository`: métricas por `component_id|condición` en lugar de `pack_key`.
- `feedback_reranker`: ordenar suplementos; `packs_ranked` se sigue devolviendo una versión como obsoleto.
- Historial: guardar y mostrar los suplementos de la sesión en vez del pack.

Frontend (`Recomendaciones.jsx` 10 usos de packs, `Feedback.jsx`, `Historial.jsx`, `events.js`, `Loading.jsx`):

- Recomendaciones: lista de suplementos con su producto sugerido, sin agrupar en packs.
- Feedback: un selector de 1 a 5 estrellas por suplemento (accesible: botones con `aria-pressed` y etiqueta
  "4 de 5 estrellas"), todos opcionales, más la pregunta general que ya existe.
- Eventos: `pack_key` pasa a ser opcional; `component_id` ya se envía.

Esfuerzo aproximado: 2-3 días de backend con migración y tests, 1-2 días de frontend con E2E.

## Riesgos

- **Datos más finos, pero todavía pocos.** Hasta tener volumen real, el feedback casi no debería mover el orden
  (de ahí el prior más fuerte). Con `component_id|condición` hay 98 claves posibles (pares de
  `condition_component_links.csv`) en lugar de miles de combinaciones de pack, así que los votos se acumulan más rápido que hoy.
- **Se pierde la "receta" armada.** Los packs comunicaban combinaciones con sinergia (vitamina D + K2, hierro +
  vitamina C). Se puede conservar como sugerencia de "suele combinarse con" usando `sinergias`, sin que sea la unidad
  de ranking.
- **Compatibilidad.** Clientes que lean `packs_ranked` deben seguir funcionando durante la transición.

## Recomendación

Hacerlo, en este orden:

1. Backend: feedback y métricas por suplemento en paralelo a los packs (sin quitar nada) y medir con
   `test_feedback_ranking.py` adaptado.
2. Frontend: estrellas por suplemento en Feedback y lista individual en Recomendaciones.
3. Quitar packs del ranking y dejar `packs_ranked` como obsoleto una versión.

Antes de empezar conviene decidir con el nutricionista la regla "el feedback no supera la evidencia".
