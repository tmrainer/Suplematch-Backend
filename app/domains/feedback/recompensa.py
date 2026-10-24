"""Recompensa escalar del feedback (etapa "una recompensa mejor que un rating").

El ranking bayesiano y el futuro bandit no aprenden de un rating de 1 a 5 sino de una
recompensa en [0, 1] que combina la opinion declarada con resultados observables:

    reward = 0.40 * rating_normalizado
           + 0.20 * purchased
           + 0.30 * still_taking_30d
           + 0.10 * (perceived_benefit == "claro")  |  0.05 * (perceived_benefit == "leve")

Reglas:
- `rating_normalizado = (rating - 1) / 4` (1 estrella -> 0.0, 5 estrellas -> 1.0).
- Si el feedback solo trae rating (ningun outcome informado), `reward == rating_normalizado`:
  asi el historico previo a esta version sigue siendo comparable.
- En cuanto se informa al menos un outcome, el rating pesa 0.40 y el resto del credito
  se gana con hechos: compro (0.20), sigue tomandolo a 30 dias (0.30) y beneficio percibido.
  Un outcome negativo (`purchased=False`) no resta: simplemente no suma.
- El resultado siempre se recorta a [0, 1].

Ver docs/recommender_events.md para la justificacion y el plan por etapas.
"""

from __future__ import annotations

from typing import Any, Literal

PerceivedBenefit = Literal["ninguno", "leve", "claro"]

REWARD_VERSION = "v1"
RATING_WEIGHT = 0.40
PURCHASED_WEIGHT = 0.20
STILL_TAKING_WEIGHT = 0.30
PERCEIVED_BENEFIT_WEIGHTS: dict[str, float] = {"claro": 0.10, "leve": 0.05, "ninguno": 0.0}
OUTCOME_FIELDS = ("purchased", "still_taking_30d", "perceived_benefit")


def _get(feedback: Any, name: str) -> Any:
    if isinstance(feedback, dict):
        return feedback.get(name)
    return getattr(feedback, name, None)


def normalize_rating(rating: Any) -> float | None:
    """Convierte un rating 1-5 a [0, 1]; devuelve None si no hay rating valido."""
    if rating is None:
        return None
    try:
        value = float(rating)
    except (TypeError, ValueError):
        return None
    value = max(1.0, min(5.0, value))
    return (value - 1.0) / 4.0


def has_outcomes(feedback: Any) -> bool:
    """True si el feedback informa al menos un resultado observable (no solo rating)."""
    return any(_get(feedback, field) is not None for field in OUTCOME_FIELDS)


def reward(feedback: Any) -> float:
    """Recompensa en [0, 1] para un feedback (dict u objeto con rating/purchased/still_taking_30d/perceived_benefit).

    Funcion pura: no toca base de datos ni settings. Ver docstring del modulo para la formula.
    """
    rating_norm = normalize_rating(_get(feedback, "rating"))

    if not has_outcomes(feedback):
        return float(rating_norm) if rating_norm is not None else 0.0

    total = RATING_WEIGHT * (rating_norm or 0.0)
    if _get(feedback, "purchased") is True:
        total += PURCHASED_WEIGHT
    if _get(feedback, "still_taking_30d") is True:
        total += STILL_TAKING_WEIGHT
    benefit = _get(feedback, "perceived_benefit")
    if benefit is not None:
        total += PERCEIVED_BENEFIT_WEIGHTS.get(str(benefit).strip().lower(), 0.0)
    return max(0.0, min(1.0, float(total)))


def outcome_payload(feedback: Any) -> dict[str, Any]:
    """Construye `outcome_json` para persistir: outcomes declarados + recompensa calculada y su version."""
    payload: dict[str, Any] = {field: _get(feedback, field) for field in OUTCOME_FIELDS}
    payload["reward"] = round(reward(feedback), 6)
    payload["reward_version"] = REWARD_VERSION
    return payload
