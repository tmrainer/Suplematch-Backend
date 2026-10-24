"""Clave contextual del feedback y utilidades puras para el sistema de eventos de recomendacion.

Un mismo pack puede ser excelente para alguien con deficit de vitamina D y mediocre para alguien
con estres cronico. Agregar el feedback solo por `pack_key` mezcla ambos publicos; por eso cada
feedback y cada evento llevan una `context_key`:

    context_key = pack_key + "|" + "+".join(sorted(condiciones_principales))

donde `condiciones_principales` son las 3 primeras condiciones del perfil (en el orden en que
las devuelve el modelo, es decir por confianza), excluyendo `SALUDABLE`, ordenadas
alfabeticamente para que la clave sea canonica.

Las funciones de este modulo son puras (sin BD) para poder testearlas sin Postgres.
"""

from __future__ import annotations

from typing import Any, Iterable

HEALTHY_CONDITION = "SALUDABLE"
PRINCIPAL_CONDITIONS_LIMIT = 3
CONTEXT_SEPARATOR = "|"
CONDITION_JOINER = "+"

# Minimo de feedback contextual para confiar en el contexto antes de caer al pack global.
MIN_CONTEXT_FEEDBACK = 3
# Prior y pseudo-conteo del score bayesiano (alineados con feedback_reranker).
FEEDBACK_PRIOR = 0.70
FEEDBACK_BAYES_M = 8

IMPRESSION_EVENT = "impression"


def principal_conditions(conditions: Iterable[Any] | None, limit: int = PRINCIPAL_CONDITIONS_LIMIT) -> list[str]:
    """Primeras `limit` condiciones (sin SALUDABLE, sin duplicados ni vacios), devueltas ordenadas."""
    picked: list[str] = []
    seen: set[str] = set()
    for raw in conditions or []:
        text = str(raw or "").strip()
        if not text or text.upper() == HEALTHY_CONDITION or text in seen:
            continue
        seen.add(text)
        picked.append(text)
        if len(picked) >= limit:
            break
    return sorted(picked)


def build_context_key(pack_key: Any, conditions: Iterable[Any] | None) -> str | None:
    """`pack_key|COND_A+COND_B+COND_C`. Devuelve None si no hay pack_key."""
    key = str(pack_key or "").strip()
    if not key:
        return None
    return f"{key}{CONTEXT_SEPARATOR}{CONDITION_JOINER.join(principal_conditions(conditions))}"


def _get(event: Any, name: str) -> Any:
    if isinstance(event, dict):
        return event.get(name)
    return getattr(event, name, None)


def impression_key(event: Any, session_ref: Any = None) -> tuple:
    """Clave de idempotencia de una impresion: (sesion, event_type, pack_key, product_id, position)."""
    session = session_ref if session_ref is not None else _get(event, "recommendation_id")
    product_id = _get(event, "product_id")
    position = _get(event, "position")
    return (
        str(session) if session is not None else None,
        str(_get(event, "event_type") or ""),
        str(_get(event, "pack_key")) if _get(event, "pack_key") is not None else None,
        str(product_id) if product_id is not None else None,
        int(position) if position is not None else None,
    )


def dedupe_impressions(
    events: Iterable[Any],
    *,
    existing_keys: Iterable[tuple] = (),
    session_ref_for: Any = None,
) -> tuple[list[Any], int]:
    """Filtra impresiones repetidas dentro del lote y contra `existing_keys` (ya persistidas).

    Los eventos que no son `impression` pasan siempre (un segundo click si cuenta).
    `session_ref_for(event)` permite resolver recommendation_id -> id de sesion antes de comparar.
    Devuelve (eventos_aceptados, cantidad_descartada).
    """
    seen: set[tuple] = set(existing_keys)
    accepted: list[Any] = []
    dropped = 0
    for event in events:
        if str(_get(event, "event_type") or "") != IMPRESSION_EVENT:
            accepted.append(event)
            continue
        ref = session_ref_for(event) if session_ref_for is not None else None
        key = impression_key(event, ref)
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        accepted.append(event)
    return accepted, dropped


def bayesian_feedback_score(
    avg_reward: float | None,
    n: int,
    *,
    prior: float = FEEDBACK_PRIOR,
    m: int = FEEDBACK_BAYES_M,
) -> float:
    """Media de recompensa suavizada hacia el prior: (n*avg + m*prior) / (n + m)."""
    n = int(n or 0)
    if n <= 0 or avg_reward is None:
        return float(prior)
    avg = max(0.0, min(1.0, float(avg_reward)))
    return float((n / (n + m)) * avg + (m / (n + m)) * prior)


def select_feedback_stats(
    context_stats: tuple[float | None, int] | None,
    global_stats: tuple[float | None, int] | None,
    *,
    min_context_n: int = MIN_CONTEXT_FEEDBACK,
    prior: float = FEEDBACK_PRIOR,
    m: int = FEEDBACK_BAYES_M,
) -> dict[str, Any]:
    """Elige la fuente de feedback: contexto si tiene al menos `min_context_n` votos, si no el pack global.

    `context_stats` y `global_stats` son `(avg_reward, n)`. Devuelve score bayesiano, fuente usada
    ("context" | "global" | "none") y ambos conteos para exponerlos en la respuesta.
    """
    ctx_avg, ctx_n = context_stats if context_stats else (None, 0)
    glob_avg, glob_n = global_stats if global_stats else (None, 0)
    ctx_n = int(ctx_n or 0)
    glob_n = int(glob_n or 0)

    if ctx_n >= min_context_n and ctx_avg is not None:
        score, source, used = bayesian_feedback_score(ctx_avg, ctx_n, prior=prior, m=m), "context", ctx_n
    elif glob_n > 0 and glob_avg is not None:
        score, source, used = bayesian_feedback_score(glob_avg, glob_n, prior=prior, m=m), "global", glob_n
    else:
        score, source, used = float(prior), "none", 0

    return {
        "score": score,
        "source": source,
        "feedback_count": used,
        "feedback_context_count": ctx_n,
        "feedback_global_count": glob_n,
    }
