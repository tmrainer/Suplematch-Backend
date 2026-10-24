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
    # Reglas sensibles a dosis: si la composición declara la dosis del
    # ingrediente y esta es <= dose_limit_mcg, la regla no bloquea (solo
    # advierte). Sin dosis declarada se mantiene la acción original
    # (conservador). `ui_to_mcg` convierte UI a mcg para ese ingrediente.
    dose_limit_mcg: float | None = None
    ui_to_mcg: float | None = None


# Límite superior tolerable (UL) de vitamina A preformada en embarazo: 3,000 mcg RAE/día
# (NIH ODS, Vitamin A and Carotenoids Health Professional Fact Sheet). 1 UI = 0.3 mcg retinol.
VITAMIN_A_PREGNANCY_UL_MCG = 3000.0
VITAMIN_A_UI_TO_MCG = 0.3


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
        ingredient_pattern=r"\b(yodo|yoduro|iodo|ioduro|iodine|iodide|kelp|algas?|seaweed|fucus)\b",
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
        ingredient_pattern=(
            r"\b(retinol|vitamin[a]?\s*a|vitamina\s*a|palmitato de retin[io]l[o]?|acetato de retin[io]l[o]?"
            r"|palmitato de vitamina a|retinyl)\b"
        ),
        restriction_code=None,
        safety_condition_code="embarazo_lactancia",
        action="block",
        severity="high",
        message="Bloqueado por embarazo/lactancia declarada.",
        dose_limit_mcg=VITAMIN_A_PREGNANCY_UL_MCG,
        ui_to_mcg=VITAMIN_A_UI_TO_MCG,
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


def _joined(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return " ".join(str(item or "") for item in value)
    return str(value or "")


def product_text(payload: dict[str, Any]) -> str:
    """Texto sobre el que se evalúan reglas de seguridad y flags.

    Incluye la composición DIGEMID completa del producto (`digemid_composicion`)
    y la lista de ingredientes de todas sus filas (`product_ingredients`), no
    solo el ingrediente de la fila por la que el producto fue elegido: un
    multivitamínico seleccionado por su zinc debe evaluarse también por su
    vitamina A o su yodo.
    """
    return " ".join(
        _joined(payload.get(key))
        for key in (
            "commercial_name",
            "formal_name",
            "digemid_producto",
            "ingredient",
            "product_ingredients",
            "digemid_composicion",
            "brand",
            "regulatory_status",
            "url",
        )
    ).lower()


def composition_text(payload: dict[str, Any]) -> str:
    """Solo la composición declarada (DIGEMID + ingredientes), para extraer dosis."""
    return " ".join(
        _joined(payload.get(key))
        for key in ("digemid_composicion", "product_ingredients", "ingredient")
    ).lower()


_DOSE_AFTER_INGREDIENT = re.compile(
    r"(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)\s*(mcg|µg|ug|mg|g|ui|iu)(?![a-z])",
    flags=re.IGNORECASE,
)


def _dose_number(value: str) -> float | None:
    text = value.strip()
    if "," in text and "." in text:
        text = text.replace(",", "") if text.rfind(",") < text.rfind(".") else text.replace(".", "").replace(",", ".")
    elif "," in text:
        parts = text.split(",")
        text = "".join(parts) if all(len(part) == 3 for part in parts[1:]) else text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def declared_dose_mcg(
    text: str,
    ingredient_pattern: str,
    *,
    ui_to_mcg: float | None = None,
    window: int = 60,
) -> float | None:
    """Mayor dosis (en mcg) declarada para un ingrediente dentro de `text`.

    Busca cada coincidencia del patrón y toma el primer "número + unidad" que
    aparece en los siguientes `window` caracteres. Devuelve None si el
    ingrediente no aparece con dosis (por ejemplo, solo en el nombre comercial).
    """
    if not text:
        return None
    best: float | None = None
    for match in re.finditer(ingredient_pattern, text, flags=re.IGNORECASE):
        snippet = text[match.end(): match.end() + window]
        dose = _DOSE_AFTER_INGREDIENT.search(snippet)
        if not dose:
            continue
        amount = _dose_number(dose.group(1))
        if amount is None:
            continue
        unit = dose.group(2).lower()
        if unit in {"mcg", "µg", "ug"}:
            mcg = amount
        elif unit == "mg":
            mcg = amount * 1000.0
        elif unit == "g":
            mcg = amount * 1_000_000.0
        elif ui_to_mcg is not None:
            mcg = amount * ui_to_mcg
        else:
            continue
        best = mcg if best is None else max(best, mcg)
    return best


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
        dose_limit_mcg=getattr(rule, "dose_limit_mcg", None),
        ui_to_mcg=getattr(rule, "ui_to_mcg", None),
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

        action = rule.action
        message = rule.message
        declared_mcg: float | None = None
        if rule.dose_limit_mcg is not None:
            declared_mcg = declared_dose_mcg(
                composition_text(payload),
                rule.ingredient_pattern,
                ui_to_mcg=rule.ui_to_mcg,
            )
            if declared_mcg is not None and declared_mcg < rule.dose_limit_mcg and action == "block":
                # Dosis declarada por debajo del límite superior: advertir, no bloquear.
                action = "penalize"
                message = (
                    f"Contiene un ingrediente restringido para la condición declarada en dosis "
                    f"declarada de {declared_mcg:g} mcg, por debajo del límite superior "
                    f"({rule.dose_limit_mcg:g} mcg); confirmar con profesional."
                )

        hit = {
            "name": rule.name,
            "action": action,
            "severity": rule.severity,
            "message": message,
            "restriction_code": rule.restriction_code,
            "safety_condition_code": rule.safety_condition_code,
            "source": rule.source,
        }
        if declared_mcg is not None:
            hit["declared_dose_mcg"] = round(declared_mcg, 3)
        hits.append(hit)
        if message and message not in warnings:
            warnings.append(message)
        if action == "block":
            blocked = True
        elif action == "penalize":
            penalty += 0.25 if rule.severity == "high" else 0.12
        elif action == "warn":
            penalty += 0.05

    return {
        "blocked": blocked,
        "penalty": min(0.8, penalty),
        "warnings": warnings,
        "rules": hits,
    }
