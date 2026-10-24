"""Calificacion de usuarios por suplemento y su efecto en el orden de `recommendations[]`.

Reglas (docs/propuesta_recomendacion_por_suplemento.md):

- Score bayesiano de recompensa por `component_id|condicion` (prior 0.70, m = 20); si ese contexto tiene menos de
  MIN_ITEM_FEEDBACK_TO_RERANK votos se usa el suplemento en todas sus condiciones, y con menos todavia el score queda
  en el prior.
- **El feedback ordena dentro del mismo nivel, nunca por encima**: solo reordena suplementos con la misma prioridad
  (principal/complementaria), el mismo `evidence_grade` y el mismo estado de bloqueo comercial. Un suplemento con
  evidencia debil y muchas estrellas no pasa a uno con evidencia fuerte, y el feedback no levanta un bloqueo.

Funciones puras: las estadisticas llegan ya calculadas (RecommendationMetricsRepository.apply_item_feedback).
"""

from __future__ import annotations

from typing import Any

from app.domains.feedback.contexto import (
    FEEDBACK_PRIOR,
    ITEM_FEEDBACK_BAYES_M,
    MIN_ITEM_FEEDBACK_TO_RERANK,
    build_item_context_key,
    select_feedback_stats,
)

ItemStats = dict[str, tuple[float | None, float | None, int]]  # clave -> (avg_reward, avg_rating, n)


def tier_key(item: dict[str, Any]) -> tuple:
    """Nivel dentro del cual el feedback puede reordenar."""
    return (
        item.get("priority"),
        item.get("evidence_grade") or "",
        bool(item.get("commercial_recommendation_blocked")),
    )


def user_rating(item: dict[str, Any], context_stats: ItemStats, component_stats: ItemStats) -> dict[str, Any]:
    """Calificacion visible y score de ranking de un suplemento.

    `stars` (promedio de estrellas, 1 decimal) solo se muestra con votos suficientes: con 2 votos un promedio
    engaña mas de lo que informa.
    """
    component_id = item.get("component_id")
    context_key = build_item_context_key(component_id, item.get("condition"))
    ctx = context_stats.get(context_key) if context_key else None
    glob = component_stats.get(str(component_id)) if component_id else None
    chosen = select_feedback_stats(
        (ctx[0], ctx[2]) if ctx else None,
        (glob[0], glob[2]) if glob else None,
        min_context_n=MIN_ITEM_FEEDBACK_TO_RERANK,
        min_global_n=MIN_ITEM_FEEDBACK_TO_RERANK,
        prior=FEEDBACK_PRIOR,
        m=ITEM_FEEDBACK_BAYES_M,
    )
    source_stats = {"context": ctx, "global": glob}.get(chosen["source"])
    stars = round(float(source_stats[1]), 1) if source_stats and source_stats[1] is not None else None
    return {
        "stars": stars,
        "count": chosen["feedback_count"],
        "score": round(float(chosen["score"]), 4),
        "source": chosen["source"],
        "context_count": chosen["feedback_context_count"],
        "total_count": chosen["feedback_global_count"],
    }


def rerank_within_tiers(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reordena por `user_rating.score` solo entre suplementos del mismo nivel (`tier_key`).

    Cada nivel conserva las posiciones que ocupaba; dentro de el, empate (todos en el prior) mantiene el orden del
    modelo.
    """
    positions: dict[tuple, list[int]] = {}
    for index, item in enumerate(recommendations):
        positions.setdefault(tier_key(item), []).append(index)
    result: list[dict[str, Any] | None] = [None] * len(recommendations)
    for indexes in positions.values():
        items = sorted(
            (recommendations[i] for i in indexes),
            key=lambda item: -float((item.get("user_rating") or {}).get("score", FEEDBACK_PRIOR)),
        )
        for position, item in zip(indexes, items):
            result[position] = item
    return [item for item in result if item is not None]
