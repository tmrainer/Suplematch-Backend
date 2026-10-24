# Base de eventos del recomendador (impresiones, acciones y recompensa)

Estado: implementado en la migración `20261022_0013`. Contexto: `docs/plan_fiabilidad.md`
(etapas "registrar impresiones, posición y acción" y "una recompensa mejor que un rating").

El objetivo es dejar de aprender solo de un rating de 1 a 5 por pack y empezar a acumular una base
de interacciones (qué se mostró, en qué posición, qué se clicó, qué se compró, qué se siguió tomando)
que sirva para un bandit contextual y, más adelante, learning-to-rank. Hoy el ranking sigue siendo
el score bayesiano; la diferencia es que ya usa recompensa contextual y que cada recomendación deja
rastro de impresiones sin depender del frontend.

## 1. Esquema de eventos (`recommendation_events`)

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id` | UUID | PK |
| `recommendation_session_id` | UUID FK → `recommendation_sessions` (SET NULL) | Sesión que generó la recomendación |
| `user_id` | UUID FK → `users` (SET NULL) | Nullable: usuarios anónimos |
| `anonymous_session_id` | str | Sesión anónima del frontend |
| `event_type` | str | `impression`, `click`, `product_click`, `purchase_intent`, `dismiss`, `still_taking_30d`, `stopped` |
| `pack_key` | str | `pack_<hash>` del reranker |
| `component_id` | str | Componente externo (opcional) |
| `product_id` | UUID FK → `commercial_products` (SET NULL) | Si el id externo no es un producto del catálogo se guarda en `payload_json.raw_product_id` |
| `position` | int | **Rank mostrado** (1 = primero) |
| `conditions_context_json` | JSONB lista | Condiciones del perfil en ese momento |
| `context_key` | str | `pack_key|COND_A+COND_B+COND_C` (ver §3) |
| `payload_json` | JSONB | Datos libres del cliente (`ui`, `source`, scores, etc.) |
| `created_at` | timestamptz | |

Índices: sesión, `pack_key`, `event_type`, `created_at`, `context_key`, `(sesión, event_type)` y
`(context_key, event_type)`.

### Fuentes de eventos

1. **Backend (automático)**: `RecommendationRepository.save_response` registra una `impression` por
   pack guardado, con `position = rank`, `context_key` y `payload_json.source = "backend"`. Así la
   base de impresiones no depende de que el frontend instrumente nada.
2. **Frontend** vía `POST /api/v1/feedback/events` (usuario opcional, máximo 50 eventos por lote):

```json
{
  "anonymous_session_id": "ses_abc",
  "events": [
    {"recommendation_id": "rec_123", "event_type": "impression", "pack_key": "pack_9f1c2a", "position": 1,
     "conditions": ["DEFICIT_VIT_D", "ESTRES_CRONICO"]},
    {"recommendation_id": "rec_123", "event_type": "product_click", "pack_key": "pack_9f1c2a",
     "product_id": "0b1e...-uuid", "position": 1, "payload": {"pharmacy": "inkafarma"}},
    {"recommendation_id": "rec_123", "event_type": "still_taking_30d", "pack_key": "pack_9f1c2a"}
  ]
}
```

Respuesta: `{"status": "saved", "accepted": 2, "deduplicated": 1, "event_ids": [...]}`.

Reglas:

- Todo `recommendation_id` debe existir en `recommendation_sessions` (404 si no; mismo criterio que
  `POST /feedback`, controlado por `FEEDBACK_REQUIRE_KNOWN_RECOMMENDATION`).
- **Idempotencia de impresiones**: una `impression` es única por
  `(sesión, event_type, pack_key, product_id, position)`; repetirla (dentro del lote o en lotes
  posteriores) se cuenta en `deduplicated` y no se inserta. Los demás tipos nunca se deduplican:
  dos clicks son dos clicks.
- Si el evento no trae `conditions`, se usan las de la sesión (`conditions_json.conditions`).

## 2. Recompensa (`app/domains/feedback/recompensa.py`)

`POST /feedback` acepta, además de `rating`, tres outcomes opcionales: `purchased: bool`,
`still_taking_30d: bool` y `perceived_benefit: "ninguno" | "leve" | "claro"`. Se guardan en
`recommendation_feedback.outcome_json` junto con la recompensa calculada y su versión (`v1`).

```
reward = 0.40 * (rating - 1) / 4
       + 0.20 * [purchased]
       + 0.30 * [still_taking_30d]
       + 0.10 * [perceived_benefit == "claro"]  |  0.05 * [perceived_benefit == "leve"]
```

- Si **solo hay rating**, `reward = rating normalizado` (histórico y nuevo quedan en la misma escala).
- En cuanto se informa un outcome, el rating pesa 0.40 y el resto se gana con hechos. Un outcome
  negativo no resta, solo deja de sumar (5 estrellas sin compra = 0.40).
- Siempre en `[0, 1]`. Es una función pura (`reward(feedback)`) testeada en
  `tests/unit/test_feedback_reward_context.py`.

El **score bayesiano** de `RecommendationMetricsRepository._feedback_score` promedia esta
recompensa (`coalesce(outcome_json.reward, (rating-1)/4)`) y la suaviza hacia el prior 0.70 con
pseudo-conteo 8: `score = (n·avg + 8·0.70) / (n + 8)`. Ya no usa el rating crudo.

## 3. Clave contextual (`app/domains/feedback/contexto.py`)

```
context_key = pack_key + "|" + "+".join(sorted(condiciones_principales))
condiciones_principales = las 3 primeras de `conditions` (orden del modelo = confianza),
                          excluyendo SALUDABLE, deduplicadas, ordenadas alfabéticamente
```

Ejemplo: `pack_9f1c2a|DEFICIT_VIT_D+ESTRES_CRONICO`.

`apply_metrics_to_packs(packs, conditions)` calcula el feedback de cada pack en dos niveles:

1. **Contextual**: feedback con el mismo `context_key` (usuarios con las mismas condiciones). Se usa
   si tiene al menos `MIN_CONTEXT_FEEDBACK` votos.
2. **Global**: si no, el `pack_key` sin importar condiciones, también desde `MIN_FEEDBACK_TO_RERANK` votos.
3. **Insuficiente**: con menos votos el score queda en el prior (0.70) y el orden no cambia.

`MIN_FEEDBACK_TO_RERANK = MIN_CONTEXT_FEEDBACK = 5` desde el 2026-10-24: con 1 voto bastaba para sacar al pack
principal del primer puesto para todos los usuarios (`tests/integration/test_feedback_ranking.py` lo prueba de
punta a punta). Cada pack expone `feedback_count` (el usado), `feedback_context_count`, `feedback_global_count`,
`feedback_source` (`context` | `global` | `insufficient` | `none`) y `feedback_context_key`. La selección es pura
(`select_feedback_stats`) y se testea sin Postgres.

El reranker (`feedback_reranker.rerank_packs`) no cambió de firma: su `feedback_stats` debe
venir ya resuelto por `context_key` (el caller decide contexto vs global por pack) y con
`avg_score` = recompensa media, no rating.

## 4. Por qué la posición importa (sesgo de posición)

Un pack en la posición 1 recibe muchos más clicks que el mismo pack en la posición 3 aunque sea
igual de bueno: el usuario mira arriba primero y se cansa. Si entrenáramos con clicks sin saber
dónde se mostró cada pack, el modelo aprendería "lo que ya estaba arriba es bueno" y se
auto-reforzaría (feedback loop). Guardar `position` en cada impresión y acción permite:

- Calcular CTR **por posición** (`clicks / impresiones` en cada rank) y normalizar.
- Estimar la propensión de examen por posición (`P(ver | rank)`) y entrenar con
  inverse-propensity weighting: cada click pesa `1 / P(ver | rank)`.
- Comparar packs solo cuando compitieron en la misma posición (interleaving sencillo).

Sin la columna `position` nada de esto es posible a posteriori; por eso se registra desde el día uno
aunque todavía no se use en el ranking.

## 5. Plan por etapas

| Etapa | Cuándo | Qué cambia | Datos que necesita |
| --- | --- | --- | --- |
| **A. Bayesiano contextual** (actual) | Ya | Score bayesiano de recompensa por `context_key` con fallback a `pack_key`; impresiones automáticas | `recommendation_feedback.outcome_json`, `context_key` |
| **B. Bandit contextual** | ~2 000 eventos con acción (click/compra/retención) y ≥ 30 contextos con ≥ 20 impresiones | Thompson sampling por `(context_key)` con recompensa = `reward` del feedback o proxy (`purchase_intent` 0.5, `still_taking_30d` 1.0, `dismiss`/`stopped` 0). El bonus UCB actual del reranker se reemplaza por el muestreo posterior; se registra la propensión de exploración en `payload_json` | `recommendation_events` + `position` para corregir sesgo |
| **C. Learning-to-rank** | ~20 000 impresiones con acción y catálogo estable | Modelo pairwise/listwise (LightGBM lambdarank) con features de perfil, pack, producto y posición; entrenamiento offline con IPW; evaluación por nDCG@3 y uplift en compras | Todo lo anterior + `recommended_pack_items` para features de producto |

Criterios de paso entre etapas: volumen (arriba), que la métrica offline del candidato supere al
bayesiano con intervalo de confianza no solapado, y revisión de seguridad (ninguna etapa relaja
las reglas de `app/domains/catalog` ni el bloqueo comercial de perfiles críticos).

## 6. Operación

- Migración: `alembic upgrade head` (idempotente; backfillea `context_key` del feedback existente).
- Consultas útiles: CTR por posición
  `select position, count(*) filter (where event_type='impression') imp, count(*) filter (where event_type in ('click','product_click')) clk from recommendation_events group by 1 order by 1;`
- Retención: los eventos no contienen datos de salud identificables (solo códigos de condición y
  `pack_key`); la política de retención de reportes de laboratorio está en `docs/privacy_and_safety.md`.
