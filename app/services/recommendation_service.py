from __future__ import annotations

import math
from uuid import uuid4
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.schemas.encuesta import EncuestaInput
from app.db.models import User
from app.ml.feature_builder import FeatureBuilder
from app.core.errors import ModelNotLoadedError, RecommendationGenerationError
from app.core.observability import log_event
from app.repositories.recommendation_metrics_repository import RecommendationMetricsRepository
from app.repositories.recommendation_repository import RecommendationRepository
from app.repositories.user_repository import UserRepository
from app.services.lab_analysis_service import LabAnalysisService
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
    "DEFICIT_B12": "Déficit de vitamina B12",
    "DEFICIT_HIERRO": "Déficit de hierro",
    "DEFICIT_MAGNESIO": "Déficit de magnesio",
    "BAJA_INMUNIDAD": "Baja inmunidad",
    "FATIGA": "Fatiga o baja energía",
    "FATIGA_CRONICA": "Fatiga crónica",
    "ESTRES": "Estrés elevado",
    "PROBLEMAS_SUENO": "Problemas de sueño",
    "RENDIMIENTO_DEPORTIVO": "Rendimiento deportivo",
    "SALUD_OSEA": "Salud ósea",
    "SALUD_COGNITIVA": "Salud cognitiva",
    "SALUD_CAPILAR": "Salud capilar y piel",
}

TYPE_LABELS = {
    "semilla_directa": "Recomendación principal",
    "candidato_gnn": "Soporte complementario",
    "soporte_funcional": "Soporte funcional",
    "INTERACCION_RIESGOSA": "Interacción riesgosa",
}

COMPONENT_NAME_ES: dict[str, str] = {
    "vitamin b12": "Vitamina B12",
    "vitamin b6": "Vitamina B6",
    "vitamin b1": "Vitamina B1",
    "vitamin b2": "Vitamina B2",
    "vitamin c": "Vitamina C",
    "vitamin d": "Vitamina D",
    "vitamin d3": "Vitamina D3",
    "vitamin e": "Vitamina E",
    "vitamin k": "Vitamina K",
    "vitamin k2": "Vitamina K2",
    "vitamin a": "Vitamina A",
    "folic acid": "Ácido fólico",
    "folate": "Folato",
    "niacin": "Niacina",
    "choline": "Colina",
    "pantothenic acid": "Ácido pantoténico",
    "biotin": "Biotina",
    "calcium": "Calcio",
    "magnesium": "Magnesio",
    "magnesium glycinate": "Glicinato de magnesio",
    "magnesium citrate": "Citrato de magnesio",
    "zinc": "Zinc",
    "iron": "Hierro",
    "iodine": "Yodo",
    "selenium": "Selenio",
    "copper": "Cobre",
    "manganese": "Manganeso",
    "chromium": "Cromo",
    "potassium": "Potasio",
    "omega-3": "Omega-3",
    "omega 3": "Omega-3",
    "fish oil": "Aceite de pescado",
    "collagen": "Colágeno",
    "coenzyme q10": "Coenzima Q10",
    "coq10": "CoQ10",
    "ashwagandha": "Ashwagandha",
    "melatonin": "Melatonina",
    "probiotics": "Probióticos",
    "l-carnitine": "L-Carnitina",
    "carnitine": "Carnitina",
    "creatine": "Creatina",
    "glutamine": "Glutamina",
    "spirulina": "Espirulina",
    "turmeric": "Cúrcuma",
    "curcumin": "Curcumina",
    "ginger": "Jengibre",
    "garlic": "Ajo",
    "green tea extract": "Extracto de té verde",
    "caffeine": "Cafeína",
    "rhodiola": "Rhodiola",
    "ginkgo biloba": "Ginkgo biloba",
    "valerian": "Valeriana",
    "passionflower": "Pasiflora",
    "chamomile": "Manzanilla",
    "evening primrose oil": "Aceite de onagra",
}


def _translate_component_name(name: str) -> str:
    return COMPONENT_NAME_ES.get(name.lower(), name)


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

CURRENT_SUPPLEMENT_KEYWORDS = {
    "vitamina_d": ("vitamin d", "vitamina d", "d3"),
    "calcio": ("calcium", "calcio"),
    "magnesio": ("magnesium", "magnesio"),
    "zinc": ("zinc",),
    "vitamina_c": ("vitamin c", "vitamina c", "ascorb"),
    "hierro": ("iron", "hierro"),
    "omega_3": ("omega", "epa", "dha"),
    "multivitaminico": ("multi",),
    "proteina": ("protein", "proteina"),
}

SECURITY_WARNING_LABELS = {
    "embarazo_lactancia": "Embarazo o lactancia: validar cualquier suplemento con un profesional de salud.",
    "enfermedad_renal": "Enfermedad renal: evitar suplementación sin evaluación médica.",
    "enfermedad_hepatica": "Enfermedad hepática: revisar seguridad y dosis con un profesional.",
    "anticoagulantes": "Uso de anticoagulantes: revisar interacciones antes de tomar suplementos.",
    "medicacion_cronica": "Medicación crónica: confirmar posibles interacciones antes de iniciar suplementos.",
}

RESTRICTION_WARNING_LABELS = {
    "alergia_lacteos": "Alergia a lácteos: revisar excipientes y origen del producto.",
    "alergia_soya": "Alergia a soya: revisar excipientes del producto.",
    "alergia_pescado_mariscos": "Alergia a pescado o mariscos: cuidado con omega 3 de origen marino.",
    "evita_gelatina": "Evita gelatina: revisar cápsulas blandas o de origen animal.",
    "sin_gluten": "Sin gluten: verificar declaración del fabricante.",
}

HARD_SAFETY_CONDITIONS = {
    "embarazo_lactancia",
    "enfermedad_renal",
    "enfermedad_hepatica",
    "anticoagulantes",
    "medicacion_cronica",
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


def _current_supplement_match(name: str | None, current_supplements: list[str]) -> bool:
    clean = (name or "").lower()
    for supplement in current_supplements:
        if any(keyword in clean for keyword in CURRENT_SUPPLEMENT_KEYWORDS.get(supplement, ())):
            return True
    return False


def _profile_warnings(encuesta: EncuestaInput) -> list[str]:
    warnings = []
    current_supplements = getattr(encuesta, "suplementos_actuales", []) or []
    if current_supplements:
        warnings.append("Ya consumes suplementos: evita duplicar dosis sin revisar etiqueta y dosis total diaria.")

    for item in getattr(encuesta, "condiciones_seguridad", []) or []:
        warning = SECURITY_WARNING_LABELS.get(item)
        if warning and warning not in warnings:
            warnings.append(warning)

    for item in getattr(encuesta, "restricciones", []) or []:
        warning = RESTRICTION_WARNING_LABELS.get(item)
        if warning and warning not in warnings:
            warnings.append(warning)

    if getattr(encuesta, "edad_rango", None) == "menos_18":
        warnings.append("Menor de edad: las recomendaciones requieren supervisión de un adulto y profesional de salud.")

    return warnings


def _safety_level(encuesta: EncuestaInput) -> str:
    if getattr(encuesta, "edad_rango", None) == "menos_18":
        return "medical_review_required"

    conditions = set(getattr(encuesta, "condiciones_seguridad", []) or [])
    if conditions.intersection(HARD_SAFETY_CONDITIONS):
        return "medical_review_required"

    if getattr(encuesta, "restricciones", None) or getattr(encuesta, "suplementos_actuales", None):
        return "caution"

    return "normal"


def _safety_actions(encuesta: EncuestaInput) -> list[str]:
    level = _safety_level(encuesta)
    if level == "normal":
        return []

    actions = [
        "No iniciar ni combinar suplementos solo con esta recomendación.",
        "Revisar etiqueta, dosis total diaria y posibles interacciones.",
    ]

    if level == "medical_review_required":
        actions.insert(0, "Validar el plan con un profesional de salud antes de comprar o consumir.")

    return actions


def _lab_analysis_for_survey(encuesta: EncuestaInput) -> dict[str, Any] | None:
    lab_results = getattr(encuesta, "lab_results", []) or []
    if not lab_results:
        return None
    return LabAnalysisService().analyze_manual(lab_results, persist=False, source_note="survey_lab_results")


def _combine_safety_level(survey_level: str, lab_analysis: dict[str, Any] | None) -> str:
    if lab_analysis and lab_analysis.get("safety_level") == "medical_review_required":
        return "medical_review_required"
    if survey_level == "medical_review_required":
        return survey_level
    if lab_analysis and lab_analysis.get("safety_level") == "caution":
        return "caution"
    return survey_level


def _merge_lab_supplement_signals(
    recommendations: list[dict[str, Any]],
    lab_analysis: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not lab_analysis:
        return recommendations

    existing_names = {
        str(item.get("name") or item.get("display_name") or "").strip().lower()
        for item in recommendations
    }
    merged = list(recommendations)
    for signal in lab_analysis.get("supplement_signals", []):
        supplement = str(signal.get("supplement") or "").strip()
        if not supplement or supplement.lower() in existing_names:
            continue
        component_id = str(signal.get("component_id") or f"lab_{signal.get('biomarker_code') or supplement.lower()}")
        merged.append(
            {
                "component_id": component_id,
                "name": supplement,
                "display_name": _translate_component_name(supplement),
                "condition": "LAB_RESULT",
                "condition_display": "Resultado de laboratorio",
                "score": 0.88,
                "type": "lab_signal",
                "type_display": "Señal por examen",
                "reason": signal.get("reason") or "Señal detectada en examen cargado.",
                "dosage_hint": "Validar dosis y necesidad con profesional de salud.",
                "priority": "lab_signal",
                "icon_key": _component_icon_key(supplement),
                "products": [],
                "already_taking": False,
                "safety_note": "Basado en examen cargado; no es diagnóstico.",
            }
        )
    return merged


def _survey_profile_values(encuesta: EncuestaInput) -> dict[str, Any]:
    return {
        "sex": getattr(encuesta, "sexo", None),
        "diet_type": getattr(encuesta, "tipo_dieta", None),
        "activity_level": getattr(encuesta, "frecuencia_ejercicio", None),
        "health_goals": {
            "objetivos": getattr(encuesta, "objetivos", []) or [],
            "presupuesto_min": getattr(encuesta, "presupuesto_min", None),
            "presupuesto_max": getattr(encuesta, "presupuesto_max", None),
            "toma_suplementos": getattr(encuesta, "toma_suplementos", "no"),
            "suplementos_actuales": getattr(encuesta, "suplementos_actuales", []) or [],
            "edad_rango": getattr(encuesta, "edad_rango", None),
            "peso_rango": getattr(encuesta, "peso_rango", None),
            "talla_rango": getattr(encuesta, "talla_rango", None),
        },
        "allergies": {
            "restricciones": getattr(encuesta, "restricciones", []) or [],
        },
        "medical_warnings": {
            "condiciones_seguridad": getattr(encuesta, "condiciones_seguridad", []) or [],
        },
    }


def _annotate_current_supplements(recommendations: list[dict[str, Any]], encuesta: EncuestaInput) -> list[dict[str, Any]]:
    current_supplements = getattr(encuesta, "suplementos_actuales", []) or []
    if not current_supplements:
        return recommendations

    for recommendation in recommendations:
        already_taking = _current_supplement_match(
            recommendation.get("name") or recommendation.get("display_name"),
            current_supplements,
        )
        recommendation["already_taking"] = already_taking
        if already_taking:
            recommendation["safety_note"] = "Indicas que ya consumes algo similar; revisar dosis y evitar duplicar."
    return recommendations


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
            "display_name": _translate_component_name(name),
            "condition": condition,
            "condition_display": _condition_display_name(condition),
            "score": score,
            "type": rec_type,
            "type_display": _type_display_name(rec_type),
            "reason": _recommendation_reason(condition, rec_type),
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
                    "display_name": _translate_component_name(name),
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
                "display_name": _translate_component_name(name),
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
        self.product_catalog = ProductCatalogService(db=db)

    def recommend(self, encuesta: EncuestaInput, user: User | None = None) -> dict:
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
        lab_analysis = _lab_analysis_for_survey(encuesta)
        recommendations = _merge_lab_supplement_signals(recommendations, lab_analysis)
        self.product_catalog.budget_min = getattr(encuesta, "presupuesto_min", None)
        self.product_catalog.budget_max = getattr(encuesta, "presupuesto_max", None)
        self.product_catalog.restrictions = getattr(encuesta, "restricciones", []) or []
        self.product_catalog.safety_conditions = getattr(encuesta, "condiciones_seguridad", []) or []
        safety_level = _combine_safety_level(_safety_level(encuesta), lab_analysis)
        commercial_recommendations_blocked = False
        recommendations = _attach_products_to_recommendations(
            recommendations,
            self.product_catalog,
        )
        recommendations = _annotate_current_supplements(recommendations, encuesta)
        packs_ranked = _attach_products_to_packs(
            packs_ranked,
            self.product_catalog,
        )
        if self.db is not None:
            packs_ranked = RecommendationMetricsRepository(self.db).apply_metrics_to_packs(packs_ranked)

        session_id = f"ses_{uuid4().hex}"
        recommendation_id = _clean_text(resultado.get("recommendation_id")) or f"rec_{uuid4().hex}"
        model_versions = {
            "model1": "modelo1_pipeline.pkl",
            "model2": "modelo2_artifacts.pkl",
            "reranker": "feedback_reranker.py",
        }
        profile_warnings = _profile_warnings(encuesta)
        if lab_analysis:
            for warning in lab_analysis.get("warnings", []):
                if warning not in profile_warnings:
                    profile_warnings.append(warning)
        safety_actions = _safety_actions(encuesta)
        if lab_analysis:
            for action in lab_analysis.get("safety_actions", []):
                if action not in safety_actions:
                    safety_actions.append(action)

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
            "profile_warnings": profile_warnings,
            "safety_level": safety_level,
            "safety_actions": safety_actions,
            "commercial_recommendations_blocked": commercial_recommendations_blocked,
            "lab_analysis": lab_analysis,
            "model_versions": model_versions,
        }

        log_event(
            "recommendation_generated",
            recommendation_id=recommendation_id,
            user_id=str(user.id) if user else None,
            conditions=conditions,
            recommendation_count=len(recommendations),
            pack_count=len(packs_ranked),
            safety_level=safety_level,
            commercial_recommendations_blocked=commercial_recommendations_blocked,
        )

        if self.db is not None:
            if user is not None:
                UserRepository(self.db).update_profile(user, _survey_profile_values(encuesta))

            RecommendationRepository(self.db).save_response(
                recommendation_id=recommendation_id,
                session_id=session_id,
                input_payload=encuesta.model_dump(),
                conditions=conditions,
                model_versions=model_versions,
                profile_warnings=profile_warnings,
                recommendations=recommendations,
                packs_ranked=packs_ranked,
                user_id=user.id if user else None,
            )

        return response
