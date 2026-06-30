from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IngredientSafetyRuleData:
    name: str
    ingredient_pattern: str
    restriction_code: str | None
    safety_condition_code: str | None
    action: str
    severity: str
    message: str
    active: bool = True
    source: str = "system_seed"


DEFAULT_INGREDIENT_SAFETY_RULES: tuple[IngredientSafetyRuleData, ...] = (
    IngredientSafetyRuleData(
        name="fish_shellfish_allergy_block",
        ingredient_pattern=r"\b(fish|pescado|mariscos?|shellfish|marino|aceite de pescado)\b",
        restriction_code="alergia_pescado_mariscos",
        safety_condition_code=None,
        action="block",
        severity="high",
        message="Bloqueado por posible pescado/mariscos para una alergia declarada.",
    ),
    IngredientSafetyRuleData(
        name="dairy_allergy_block",
        ingredient_pattern=r"\b(lacteo|lácteo|leche|whey|suero de leche|caseina|caseína|lactosa)\b",
        restriction_code="alergia_lacteos",
        safety_condition_code=None,
        action="block",
        severity="high",
        message="Bloqueado por posible lácteo/lactosa para una alergia declarada.",
    ),
    IngredientSafetyRuleData(
        name="soy_allergy_block",
        ingredient_pattern=r"\b(soya|soy|lecitina de soya)\b",
        restriction_code="alergia_soya",
        safety_condition_code=None,
        action="block",
        severity="high",
        message="Bloqueado por posible soya para una alergia declarada.",
    ),
    IngredientSafetyRuleData(
        name="gelatin_warning",
        ingredient_pattern=r"\b(gelatina|softgel|c[aá]psulas? blandas?)\b",
        restriction_code="evita_gelatina",
        safety_condition_code=None,
        action="penalize",
        severity="medium",
        message="Puede contener cápsula blanda o gelatina; revisar etiqueta.",
    ),
    IngredientSafetyRuleData(
        name="gluten_traceability_warning",
        ingredient_pattern=r"\b(gluten|trigo|wheat|cebada|barley|centeno|rye)\b",
        restriction_code="sin_gluten",
        safety_condition_code=None,
        action="penalize",
        severity="medium",
        message="Puede no ser apto sin gluten; priorizar productos con etiqueta verificada.",
    ),
    IngredientSafetyRuleData(
        name="vitamin_k_anticoagulants_block",
        ingredient_pattern=r"\b(vitamin[a]?\s*k|vitamina\s*k|k2|menaquinona|phytonadione|fitonadiona)\b",
        restriction_code=None,
        safety_condition_code="anticoagulantes",
        action="block",
        severity="high",
        message="Bloqueado por posible interacción con anticoagulantes.",
    ),
    IngredientSafetyRuleData(
        name="omega3_anticoagulants_warning",
        ingredient_pattern=r"\b(omega\s*-?\s*3|epa|dha|fish oil|aceite de pescado|krill)\b",
        restriction_code=None,
        safety_condition_code="anticoagulantes",
        action="penalize",
        severity="medium",
        message="Revisar omega 3 con anticoagulantes antes de comprar o consumir.",
    ),
    IngredientSafetyRuleData(
        name="herbal_anticoagulants_warning",
        ingredient_pattern=r"\b(ginkgo|garlic|ajo|curcuma|cúrcuma|turmeric|ashwagandha|valeriana|ginseng)\b",
        restriction_code=None,
        safety_condition_code="anticoagulantes",
        action="penalize",
        severity="medium",
        message="Revisar fórmulas herbales con anticoagulantes antes de comprar o consumir.",
    ),
    IngredientSafetyRuleData(
        name="iodine_thyroid_block",
        ingredient_pattern=r"\b(yodo|iodine|kelp|algas?|seaweed|fucus)\b",
        restriction_code=None,
        safety_condition_code="problema_tiroideo",
        action="block",
        severity="high",
        message="Bloqueado por problema tiroideo declarado; revisar yodo o algas con profesional.",
    ),
    IngredientSafetyRuleData(
        name="creatine_kidney_block",
        ingredient_pattern=r"\b(creatine|creatina)\b",
        restriction_code=None,
        safety_condition_code="enfermedad_renal",
        action="block",
        severity="high",
        message="Bloqueado por enfermedad renal declarada.",
    ),
    IngredientSafetyRuleData(
        name="retinol_pregnancy_block",
        ingredient_pattern=r"\b(retinol|vitamin[a]?\s*a|vitamina\s*a|palmitato de retinilo)\b",
        restriction_code=None,
        safety_condition_code="embarazo_lactancia",
        action="block",
        severity="high",
        message="Bloqueado por embarazo/lactancia declarada.",
    ),
    IngredientSafetyRuleData(
        name="hepatic_extract_warning",
        ingredient_pattern=r"\b(kava|extracto de t[eé] verde|green tea extract|garcinia|ashwagandha)\b",
        restriction_code=None,
        safety_condition_code="enfermedad_hepatica",
        action="block",
        severity="high",
        message="Bloqueado por enfermedad hepática declarada.",
    ),
)


def product_text(payload: dict[str, Any]) -> str:
    return " ".join(
        str(payload.get(key) or "")
        for key in (
            "commercial_name",
            "formal_name",
            "digemid_producto",
            "ingredient",
            "brand",
            "regulatory_status",
            "url",
        )
    ).lower()


def infer_restriction_flags(payload: dict[str, Any]) -> list[str]:
    text = product_text(payload)
    flags = set()

    if any(keyword in text for keyword in ("fish", "pescado", "marino", "aceite de pescado")):
        flags.add("contains_fish_or_shellfish")
    if any(
        keyword in text
        for keyword in ("gelatina", "softgel", "cápsula blanda", "capsula blanda", "cápsulas blandas", "capsulas blandas")
    ):
        flags.add("may_contain_gelatin")
    if any(keyword in text for keyword in ("lacteo", "lácteo", "leche", "whey", "suero de leche", "caseina", "caseína")):
        flags.add("may_contain_dairy")
    if any(keyword in text for keyword in ("soya", "soy", "lecitina de soya")):
        flags.add("may_contain_soy")

    gluten_free_claim = any(keyword in text for keyword in ("sin gluten", "gluten free", "libre de gluten"))
    if gluten_free_claim:
        flags.add("gluten_free_claim")

    return sorted(flags)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "si", "sí", "y", "verified"}


def verified_restriction_flags(payload: dict[str, Any]) -> list[str]:
    raw_flags = payload.get("restriction_flags_verified")
    if isinstance(raw_flags, list):
        return sorted({str(flag) for flag in raw_flags if str(flag).strip()})

    flags = set()
    if _truthy(payload.get("contains_fish")) or _truthy(payload.get("contains_shellfish")):
        flags.add("contains_fish_or_shellfish")
    if _truthy(payload.get("contains_gelatin")) or _truthy(payload.get("softgel_verified")):
        flags.add("may_contain_gelatin")
    if _truthy(payload.get("contains_dairy")) or _truthy(payload.get("contains_lactose")):
        flags.add("may_contain_dairy")
    if _truthy(payload.get("contains_soy")) or _truthy(payload.get("contains_soya")):
        flags.add("may_contain_soy")
    if _truthy(payload.get("gluten_free_verified")):
        flags.add("gluten_free_claim")

    return sorted(flags)


def product_restriction_flags(payload: dict[str, Any]) -> list[str]:
    verified = verified_restriction_flags(payload)
    if verified:
        return verified
    return infer_restriction_flags(payload)


def catalog_verification_status(payload: dict[str, Any]) -> dict[str, Any]:
    registro = str(payload.get("registro_sanitario") or "").strip()
    regulatory_status = str(payload.get("regulatory_status") or payload.get("component_traceable") or "").lower()
    verified_flags = verified_restriction_flags(payload)
    inferred_flags = infer_restriction_flags(payload)
    label_source = str(payload.get("label_verification_source") or "").strip()
    label_verified_at = str(payload.get("label_verified_at") or "").strip()

    warnings = []
    if not registro:
        warnings.append("Registro sanitario no informado")
    if not ("digemid" in regulatory_status or "match" in regulatory_status):
        warnings.append("Componente o registro sin match verificable")
    if inferred_flags and not verified_flags:
        warnings.append("Restricciones inferidas por texto, no verificadas por etiqueta")
    if not label_source:
        warnings.append("Fuente de verificación de etiqueta no registrada")

    if registro and ("digemid" in regulatory_status or "match" in regulatory_status) and verified_flags and label_source:
        status = "verified"
    elif registro and ("digemid" in regulatory_status or "match" in regulatory_status):
        status = "partially_verified"
    else:
        status = "needs_review"

    return {
        "verification_status": status,
        "verification_warnings": warnings,
        "restriction_flags_verified": verified_flags,
        "restriction_flags_inferred": inferred_flags,
        "label_verified_at": label_verified_at or None,
        "label_verification_source": label_source or None,
    }


def _rule_from_any(rule: Any) -> IngredientSafetyRuleData | None:
    if isinstance(rule, IngredientSafetyRuleData):
        return rule
    if not getattr(rule, "active", True):
        return None
    return IngredientSafetyRuleData(
        name=str(getattr(rule, "name", "")),
        ingredient_pattern=str(getattr(rule, "ingredient_pattern", "")),
        restriction_code=getattr(rule, "restriction_code", None),
        safety_condition_code=getattr(rule, "safety_condition_code", None),
        action=str(getattr(rule, "action", "warn")),
        severity=str(getattr(rule, "severity", "medium")),
        message=str(getattr(rule, "message", "")),
        active=bool(getattr(rule, "active", True)),
        source=str(getattr(rule, "source", "database")),
    )


def evaluate_ingredient_safety(
    payload: dict[str, Any],
    *,
    restrictions: list[str] | None = None,
    safety_conditions: list[str] | None = None,
    rules: list[Any] | tuple[Any, ...] | None = None,
) -> dict[str, Any]:
    text = product_text(payload)
    active_restrictions = set(restrictions or [])
    active_conditions = set(safety_conditions or [])
    selected_rules = tuple(rules) if rules is not None else DEFAULT_INGREDIENT_SAFETY_RULES

    hits: list[dict[str, str | None]] = []
    blocked = False
    penalty = 0.0
    warnings: list[str] = []

    for raw_rule in selected_rules:
        rule = _rule_from_any(raw_rule)
        if rule is None or not rule.ingredient_pattern:
            continue
        if rule.restriction_code and rule.restriction_code not in active_restrictions:
            continue
        if rule.safety_condition_code and rule.safety_condition_code not in active_conditions:
            continue
        if not re.search(rule.ingredient_pattern, text, flags=re.IGNORECASE):
            continue

        hit = {
            "name": rule.name,
            "action": rule.action,
            "severity": rule.severity,
            "message": rule.message,
            "restriction_code": rule.restriction_code,
            "safety_condition_code": rule.safety_condition_code,
            "source": rule.source,
        }
        hits.append(hit)
        if rule.message and rule.message not in warnings:
            warnings.append(rule.message)
        if rule.action == "block":
            blocked = True
        elif rule.action == "penalize":
            penalty += 0.25 if rule.severity == "high" else 0.12
        elif rule.action == "warn":
            penalty += 0.05

    return {
        "blocked": blocked,
        "penalty": min(0.8, penalty),
        "warnings": warnings,
        "rules": hits,
    }
