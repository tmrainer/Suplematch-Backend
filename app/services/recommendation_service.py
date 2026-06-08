from __future__ import annotations

import math
from uuid import uuid4
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.schemas.encuesta import EncuestaInput
from app.ml.feature_builder import FeatureBuilder
from app.core.errors import ModelNotLoadedError, RecommendationGenerationError
from app.repositories.recommendation_repository import RecommendationRepository
from app.services.product_catalog_service import ProductCatalogService


DISCLAIMER = (
    "Estas recomendaciones son orientativas y no reemplazan una evaluación médica. "
    "Consulta con un profesional de salud antes de iniciar suplementos, especialmente "
    "si tomas medicamentos, tienes una condición médica o estás embarazada."
)

CONDITION_LABELS = {
    "SALUDABLE": "Base saludable",
    "DEFICIT_VIT_D": "Déficit de vitamina D",
    "DEFICIT_CALCIO": "Déficit de calcio",
    "BAJA_INMUNIDAD": "Baja inmunidad",
    "FATIGA": "Fatiga o baja energía",
    "ESTRES": "Estrés elevado",
    "PROBLEMAS_SUENO": "Problemas de sueño",
}

TYPE_LABELS = {
    "semilla_directa": "Recomendación principal",
    "candidato_gnn": "Soporte complementario",
    "soporte_funcional": "Soporte funcional",
    "INTERACCION_RIESGOSA": "Interacción riesgosa",
}

COMPONENT_ICONS = {
    "vitamin d": "sun",
    "vitamina d": "sun",
    "calcium": "bone",
    "calcio": "bone",
    "zinc": "zap",
    "vitamin c": "citrus",
    "vitamina c": "citrus",
    "magnesium": "moon",
    "magnesio": "moon",
    "iron": "activity",
    "hierro": "activity",
    "omega": "waves",
}

COMPONENT_DOSAGE_HINTS = {
    "vitamin d": "Consultar dosis según niveles y exposición solar",
    "vitamina d": "Consultar dosis según niveles y exposición solar",
    "calcium": "Tomar según dieta y recomendación profesional",
    "calcio": "Tomar según dieta y recomendación profesional",
    "zinc": "Evitar exceder uso prolongado sin supervisión",
    "vitamin c": "Puede tomarse junto con alimentos",
    "vitamina c": "Puede tomarse junto con alimentos",
    "magnesium": "Suele tolerarse mejor por la noche",
    "magnesio": "Suele tolerarse mejor por la noche",
    "iron": "Evitar combinarlo con calcio en la misma toma",
    "hierro": "Evitar combinarlo con calcio en la misma toma",
}


def _to_builtin(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _to_builtin(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_to_builtin(v) for v in value]

    if isinstance(value, tuple):
        return [_to_builtin(v) for v in value]

    if isinstance(value, np.integer):
        return int(value)

    if isinstance(value, np.floating):
        return float(value)

    if isinstance(value, np.bool_):
        return bool(value)

    if isinstance(value, np.ndarray):
        return value.tolist()

    return value


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value

    return None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _clean_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(number):
        return None

    return number


def _clean_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _humanize_code(value: str | None) -> str:
    if value is None:
        return "Perfil evaluado"

    return (
        value.replace("_", " ")
        .strip()
        .lower()
        .capitalize()
    )


def _condition_display_name(condition: str | None) -> str:
    if condition is None:
        return "Perfil evaluado"

    return CONDITION_LABELS.get(condition, _humanize_code(condition))


def _type_display_name(value: str | None) -> str | None:
    if value is None:
        return None

    return TYPE_LABELS.get(value, _humanize_code(value))


def _component_icon_key(name: str) -> str:
    clean = name.lower()

    for key, icon in COMPONENT_ICONS.items():
        if key in clean:
            return icon

    return "pill"


def _dosage_hint(name: str, rec_type: str | None) -> str:
    clean = name.lower()

    for key, hint in COMPONENT_DOSAGE_HINTS.items():
        if key in clean:
            return hint

    if rec_type == "semilla_directa":
        return "Prioritario para el perfil detectado"

    return "Complementario para el perfil detectado"


def _recommendation_reason(condition: str | None, rec_type: str | None) -> str:
    if condition and condition != "soporte_funcional":
        return f"Relacionado con {_condition_display_name(condition).lower()}."

    if rec_type == "candidato_gnn":
        return "Complementa el pack por soporte funcional."

    return "Recomendado para el perfil evaluado."


def _condition_probability_fallback(index: int, total: int) -> float:
    if total <= 1:
        return 0.82
    return max(0.45, 0.82 - (index * 0.12))


def _condition_level(probability: float) -> str:
    if probability >= 0.70:
        return "Alta prioridad"
    if probability >= 0.55:
        return "Prioridad media"
    return "Contexto"


def _recommendation_reason_with_score(
    condition: str | None,
    condition_score: float | None,
    rec_type: str | None,
) -> str:
    if condition and condition != "soporte_funcional":
        name = _condition_display_name(condition).lower()
        if condition_score and condition_score >= 0.70:
            return f"Alta prioridad por {name} (confianza {round(condition_score * 100)}%)."
        if condition_score and condition_score >= 0.50:
            return f"Indicado para {name} (confianza {round(condition_score * 100)}%)."
        return f"Indicado para {name}."
    if rec_type == "candidato_gnn":
        return "Complementa el pack por sinergia funcional con los demás componentes."
    return "Recomendado para el perfil evaluado."


def _normalize_conditions(values: Any) -> list[str]:
    if not isinstance(values, list):
        values = [values]

    conditions = []
    seen = set()

    for value in values:
        condition = _clean_text(value)
        if condition is None or condition in seen:
            continue

        seen.add(condition)
        conditions.append(condition)

    return conditions


def _normalize_conditions_display(
    conditions: list[str],
    condition_scores: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    total = len(conditions)
    scores = condition_scores or {}

    return [
        {
            "code": condition,
            "display_name": _condition_display_name(condition),
            "level": _condition_level(
                scores.get(condition, _condition_probability_fallback(index, total))
            ),
            "probability": scores.get(condition, _condition_probability_fallback(index, total)),
            "icon_key": "check" if condition == "SALUDABLE" else "activity",
        }
        for index, condition in enumerate(conditions)
    ]


def _normalize_recommendations(values: Any, condition_scores: dict[str, float] | None = None) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []

    recommendations = []
    seen = set()

    for item in values:
        if isinstance(item, dict):
            component_id = _clean_text(item.get("component_id"))
            name = _clean_text(item.get("name") or item.get("nombre") or component_id)
            condition = _clean_text(item.get("condition") or item.get("condicion"))
            rec_type = _clean_text(item.get("type") or item.get("tipo"))
            score = _clean_float(_first_present(item.get("score"), item.get("score_gnn")))
        elif isinstance(item, (list, tuple)):
            component_id = _clean_text(item[3]) if len(item) > 3 else None
            name = _clean_text(item[0] if item else component_id)
            condition = _clean_text(item[1]) if len(item) > 1 else None
            rec_type = _clean_text(item[4]) if len(item) > 4 else None
            score = _clean_float(item[2]) if len(item) > 2 else None
        else:
            continue

        if name is None:
            continue

        dedupe_key = component_id or name.lower()
        if dedupe_key in seen:
            continue

        condition_score = (condition_scores or {}).get(condition) if condition else None
        seen.add(dedupe_key)
        recommendations.append({
            "component_id": component_id,
            "name": name,
            "display_name": name,
            "condition": condition,
            "condition_display": _condition_display_name(condition),
            "score": score,
            "type": rec_type,
            "type_display": _type_display_name(rec_type),
            "reason": _recommendation_reason_with_score(condition, condition_score, rec_type),
            "dosage_hint": _dosage_hint(name, rec_type),
            "priority": "principal" if rec_type == "semilla_directa" else "complementaria",
            "icon_key": _component_icon_key(name),
        })

    return recommendations


def _normalize_relation(item: Any) -> dict[str, str] | None:
    if isinstance(item, dict):
        component_a = _clean_text(
            item.get("component_a")
            or item.get("nombre_a")
            or item.get("name_a")
            or item.get("a")
        )
        component_b = _clean_text(
            item.get("component_b")
            or item.get("nombre_b")
            or item.get("name_b")
            or item.get("b")
        )
        relation_type = _clean_text(
            item.get("type")
            or item.get("tipo")
            or item.get("relationship_type")
            or item.get("relationship_subclass")
        )
    elif isinstance(item, (list, tuple)) and len(item) >= 3:
        component_a = _clean_text(item[0])
        component_b = _clean_text(item[1])
        relation_type = _clean_text(item[2])
    else:
        return None

    if component_a is None or component_b is None or relation_type is None:
        return None

    return {
        "component_a": component_a,
        "component_b": component_b,
        "type": relation_type,
    }


def _normalize_relations(values: Any) -> list[dict[str, str]]:
    if not isinstance(values, list):
        return []

    relations = []
    seen = set()

    for item in values:
        relation = _normalize_relation(item)
        if relation is None:
            continue

        dedupe_key = (
            relation["component_a"].lower(),
            relation["component_b"].lower(),
            relation["type"].lower(),
        )
        if dedupe_key in seen:
            continue

        seen.add(dedupe_key)
        relations.append(relation)

    return relations


def _normalize_pack_components(pack: dict[str, Any]) -> list[dict[str, str | None]]:
    raw_components = pack.get("components")

    if isinstance(raw_components, list):
        components = []
        for component in raw_components:
            if isinstance(component, dict):
                component_id = _clean_text(component.get("component_id") or component.get("id"))
                name = _clean_text(component.get("name") or component.get("nombre") or component_id)
            else:
                component_id = None
                name = _clean_text(component)

            if name is not None:
                components.append({
                    "component_id": component_id,
                    "name": name,
                    "display_name": name,
                    "icon_key": _component_icon_key(name),
                })

        if components:
            return components

    component_ids = pack.get("component_ids") or []
    component_names = pack.get("component_names") or []

    if not isinstance(component_ids, list):
        component_ids = []

    if not isinstance(component_names, list):
        component_names = []

    total = max(len(component_ids), len(component_names))
    components = []

    for index in range(total):
        component_id = _clean_text(component_ids[index]) if index < len(component_ids) else None
        name = _clean_text(component_names[index]) if index < len(component_names) else component_id

        if name is not None:
            components.append({
                "component_id": component_id,
                "name": name,
                "display_name": name,
                "icon_key": _component_icon_key(name),
            })

    return components


def _normalize_packs(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []

    packs = []

    for index, item in enumerate(values, start=1):
        if not isinstance(item, dict):
            continue

        components = _normalize_pack_components(item)
        component_ids = [
            component["component_id"]
            for component in components
            if component.get("component_id") is not None
        ]
        component_names = [component["name"] for component in components]
        score_final = _clean_float(_first_present(item.get("score_final"), item.get("score")))

        packs.append({
            "pack_id": _clean_text(item.get("pack_id")) or f"pack_{index}",
            "rank": _clean_int(item.get("rank"), index),
            "title": " + ".join(component_names),
            "subtitle": f"{len(component_names)} suplemento(s) priorizados para tu perfil",
            "components": components,
            "component_ids": component_ids,
            "component_names": component_names,
            "score": score_final,
            "score_final": score_final,
            "score_gnn": _clean_float(item.get("score_gnn")),
            "score_coverage": _clean_float(item.get("score_coverage")),
            "score_feedback": _clean_float(item.get("score_feedback")),
            "feedback_count": _clean_int(item.get("feedback_count")),
            "cta_label": "Ver detalle del pack",
        })

    return packs


def _attach_products_to_recommendations(
    recommendations: list[dict[str, Any]],
    product_catalog: ProductCatalogService,
) -> list[dict[str, Any]]:
    for recommendation in recommendations:
        recommendation["products"] = product_catalog.products_for_component(
            recommendation.get("component_id")
        )

    return recommendations


def _attach_products_to_packs(
    packs: list[dict[str, Any]],
    product_catalog: ProductCatalogService,
) -> list[dict[str, Any]]:
    for pack in packs:
        component_ids = [
            str(component_id)
            for component_id in pack.get("component_ids", [])
            if component_id
        ]
        pack["selected_products"] = product_catalog.select_products_for_pack(component_ids)

    return packs


class RecommendationService:
    def __init__(self, models: dict, db: Session | None = None):
        self.models = models
        self.db = db
        self.feature_builder = FeatureBuilder()
        self.product_catalog = ProductCatalogService()

    def recommend(self, encuesta: EncuestaInput) -> dict:
        pipeline = self.models.get("pipeline_vitaminas")

        if pipeline is None:
            raise ModelNotLoadedError()

        try:
            payload = self.feature_builder.build_pipeline_payload(encuesta)
            resultado = pipeline(payload, verbose=False)
            resultado = _to_builtin(resultado)
        except (FileNotFoundError, ModuleNotFoundError, ImportError, OSError) as exc:
            raise RecommendationGenerationError() from exc
        except Exception as exc:
            raise RecommendationGenerationError() from exc

        condition_scores = _to_builtin(resultado.get("condition_scores", {}))
        explainability   = _to_builtin(resultado.get("explainability", []))

        conditions = _normalize_conditions(
            _first_present(resultado.get("condiciones"), resultado.get("conditions"), [])
        )
        recommendations = _normalize_recommendations(
            _first_present(resultado.get("recomendaciones"), resultado.get("recommendations"), []),
            condition_scores=condition_scores,
        )
        packs_ranked = _normalize_packs(resultado.get("packs_ranked", []))
        recommendations = _attach_products_to_recommendations(
            recommendations,
            self.product_catalog,
        )
        packs_ranked = _attach_products_to_packs(
            packs_ranked,
            self.product_catalog,
        )

        session_id = f"ses_{uuid4().hex}"
        recommendation_id = _clean_text(resultado.get("recommendation_id")) or f"rec_{uuid4().hex}"
        model_versions = {
            "model1": "modelo1_pipeline.pkl",
            "model2": "modelo2_artifacts.pkl",
            "reranker": "feedback_reranker.py",
        }

        response = {
            "session_id": session_id,
            "recommendation_id": recommendation_id,
            "conditions": conditions,
            "conditions_display": _normalize_conditions_display(conditions, condition_scores),
            "explainability": explainability,
            "recommendations": recommendations,
            "packs_ranked": packs_ranked,
            "sinergias": _normalize_relations(resultado.get("sinergias", [])),
            "alertas": _normalize_relations(resultado.get("alertas", [])),
            "combo_seguro": resultado.get("combo_seguro", True),
            "mensaje": resultado.get("mensaje", "OK"),
            "disclaimer": DISCLAIMER,
            "model_versions": model_versions,
        }

        if self.db is not None:
            RecommendationRepository(self.db).save_response(
                recommendation_id=recommendation_id,
                session_id=session_id,
                input_payload=encuesta.model_dump(),
                conditions=conditions,
                model_versions=model_versions,
                recommendations=recommendations,
                packs_ranked=packs_ranked,
            )

        return response
