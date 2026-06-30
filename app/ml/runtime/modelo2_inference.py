"""
Modelo 2 — INFERENCIA (importar en producción)
Carga artefactos pre-entrenados. Sin re-entrenamiento.
Requiere: modelo2_artifacts.pkl (generado por modelo2_train.py)
"""

from functools import lru_cache
import re
import unicodedata

import numpy as np
import pandas as pd
import joblib

from app.core.config import BASE_DIR, settings

_artifacts = None
_ARTIFACTS_PATH = settings.MODEL_DIR / "modelo2_artifacts.pkl"
_CONDITION_COMPONENT_LINKS_PATH = BASE_DIR / "data/knowledge/condition_component_links.csv"
_COMPONENT_EVIDENCE_PROFILES_PATH = BASE_DIR / "data/knowledge/component_evidence_profiles.csv"
_COMPONENT_LIFE_STAGE_GUIDANCE_PATH = BASE_DIR / "data/knowledge/component_life_stage_guidance.csv"
_COMPONENT_INTERACTION_RULES_PATH = BASE_DIR / "data/knowledge/component_interaction_rules.csv"
_COMPONENT_CLAIM_EVIDENCE_PATH = BASE_DIR / "data/knowledge/component_claim_evidence.csv"
_TORCH_CPU_FALLBACK_REGISTERED = False

RANKER_VERSION = "component_ranker_v2"

WELLNESS_CONTEXT_CONDITIONS = {
    "BAJA_INMUNIDAD",
    "FATIGA",
    "FATIGA_CRONICA",
    "ESTRES_SUENO",
    "PROBLEMAS_SUENO",
    "RENDIMIENTO_DEPORTIVO",
    "SALUD_COGNITIVA",
    "SALUD_VISUAL",
    "SALUD_DIGESTIVA",
    "FATIGA_NUTRICIONAL",
    "HIDRATACION_ELECTROLITOS",
    "SALUD_CARDIOVASCULAR_CONTEXTUAL",
    "RIESGO_CABELLO_PIEL_UNAS",
    "SALUD_CAPILAR",
}

NON_COMMERCIAL_CONTEXT_CONDITIONS = WELLNESS_CONTEXT_CONDITIONS | {
    "RIESGO_METABOLICO_GLUCOSA",
    "RIESGO_DISLIPIDEMIA",
    "SAFETY_RENAL",
    "SAFETY_HEPATICA",
    "SAFETY_TIROIDEA",
}

EVIDENCE_WEIGHTS = {
    "high": 1.0,
    "strong": 1.0,
    "strong_with_lab": 0.96,
    "moderate": 0.82,
    "low_moderate": 0.72,
    "contextual": 0.66,
}

SOURCE_QUALITY_WEIGHTS = {
    "official_fact_sheet": 1.0,
    "official_consumer_fact_sheet": 0.92,
    "official_health_resource": 0.90,
    "medical_reference": 0.86,
    "internal_rules": 0.70,
}

ROLE_WEIGHTS = {
    "primary": 1.0,
    "primary_with_lab": 0.96,
    "supportive": 0.74,
    "supportive_with_lab": 0.68,
    "safety_context": 0.22,
}

LAB_REQUIREMENT_WEIGHTS = {
    "no": 1.0,
    "optional": 0.95,
    "preferred": 0.90,
    "required": 0.72,
}

RISK_LEVEL_PENALTIES = {
    "low": 0.0,
    "low_moderate": 0.03,
    "moderate": 0.07,
    "moderate_high": 0.14,
    "high": 0.25,
}

COMPONENT_ALIASES = {
    "acido folico": ("Folate", "Folic Acid"),
    "acido pantotenico": ("Pantothenic Acid",),
    "ashwagandha": ("Withania somnifera",),
    "biotina": ("Biotin",),
    "cafeina": ("Caffeine",),
    "calcio": ("Calcium",),
    "carnitina": ("L-Carnitine", "Carnitine"),
    "coenzima q10": ("Coenzyme Q10", "CoQ10"),
    "colageno": ("Collagen", "Collagen Hydrolyzed", "Hydrolyzed Collagen"),
    "colina": ("Choline",),
    "cobre": ("Copper",),
    "creatina": ("Creatina monohidrato", "Creatine monohydrate", "Creatine"),
    "cromo": ("Chromium", "Chromium Picolinate"),
    "dha": ("Docosahexaenoic Acid", "DHA"),
    "epa": ("Eicosapentaenoic Acid", "EPA"),
    "hierro": ("Iron",),
    "l teanina": ("L-Theanine", "Theanine"),
    "luteina": ("Lutein",),
    "magnesio": ("Magnesium",),
    "manganeso": ("Manganese",),
    "melatonina": ("Melatonin",),
    "niacina": ("Niacin", "Vitamin B3", "Nicotinamide", "Niacinamide"),
    "omega 3": ("Omega-3 Fatty Acids", "Omega-3", "Fish Oil"),
    "potasio": ("Potassium",),
    "probioticos": ("Probiotics", "Lactobacillus acidophilus", "Lactobacillus"),
    "proteina": ("whey protein", "soy protein isolate", "pea protein", "Protein"),
    "riboflavina": ("Riboflavin", "Vitamin B2"),
    "selenio": ("Selenium",),
    "sodio": ("Sodium chloride", "Sodium"),
    "taurina": ("L-Taurine", "Taurine"),
    "te verde": ("Green Tea",),
    "tiamina": ("Thiamin", "Thiamine", "Vitamin B1"),
    "valeriana": ("Valerian",),
    "vitamina a": ("Vitamin A", "Retinol", "Beta-Carotene"),
    "vitamina b12": ("Vitamin B12",),
    "vitamina b6": ("Vitamin B6", "Pyridoxine"),
    "vitamina c": ("Vitamin C (ascorbic acid)", "Vitamin C"),
    "vitamina d": ("Vitamin D (cholecalciferol)", "Vitamin D"),
    "vitamina e": ("Vitamin E",),
    "vitamina k": ("Vitamin K",),
    "yodo": ("Iodine",),
    "zeaxantina": ("Zeaxanthin",),
    "zinc": ("Zinc",),
    "inositol": ("Inositol",),
    "bacillus coagulans": ("Bacillus coagulans",),
    "bifidobacterium longum": ("Bifidobacterium longum",),
}

# Prefer IDs that are present in the commercial catalog when a generic graph node
# has fewer/no products. These IDs still represent components, not products.
COMPONENT_ID_OVERRIDES = {
    "acido folico": "COMP_A9136ADF22F7",
    "acido pantotenico": "COMP_CCEF1C481D8D",
    "ashwagandha": "COMP_AE7EE271FD2C",
    "biotina": "COMP_641FDABDC956",
    "cafeina": "COMP_4F582819D2E9",
    "calcio": "COMP_275450118D60",
    "carnitina": "COMP_0987F386BB65",
    "coenzima q10": "COMP_8BB25B9A3BE5",
    "colageno": "COMP_2671E7AB4CBB",
    "colina": "COMP_A204C673A9A2",
    "cobre": "COMP_9C5C72058DB1",
    "creatina": "COMP_7B47CDB437E8",
    "cromo": "COMP_3F24EA59D864",
    "dha": "COMP_F71DD4665D9C",
    "epa": "COMP_F3C5987AA984",
    "hierro": "COMP_B6A8F8958154",
    "l teanina": "COMP_E3D7A2D1C909",
    "luteina": "COMP_C873A4B5C00A",
    "magnesio": "COMP_83336712C554",
    "manganeso": "COMP_5FCBE278ABF3",
    "melatonina": "COMP_74AC5BE900AC",
    "niacina": "COMP_7A51909809FD",
    "omega 3": "COMP_447F5E523CED",
    "potasio": "COMP_BB2F708BF799",
    "probioticos": "COMP_C5CD8E1D6AAE",
    "proteina": "COMP_927AAC8EA873",
    "riboflavina": "COMP_586F3B3DE0F3",
    "selenio": "COMP_781B4EA1D853",
    "sodio": "COMP_AFF3B61AB344",
    "taurina": "COMP_0D2B15E9F9EE",
    "te verde": "COMP_8F63E852ED34",
    "tiamina": "COMP_4F4F134A6B55",
    "valeriana": "COMP_D691B9C2718F",
    "vitamina a": "COMP_90C4121BAE0C",
    "vitamina b12": "COMP_06B36D3A8FF3",
    "vitamina b6": "COMP_FB0BFF3E6E21",
    "vitamina c": "COMP_67B16EEFC42F",
    "vitamina d": "COMP_94DFE28A9A5C",
    "vitamina e": "COMP_D4790F9775EF",
    "vitamina k": "COMP_64DE5343502D",
    "yodo": "COMP_22DA46FADFFD",
    "zeaxantina": "COMP_D02C918DB476",
    "zinc": "COMP_723DBC80CC4E",
    "inositol": "COMP_430EB7DE720D",
    "bacillus coagulans": "COMP_5FA5A40B1A56",
    "bifidobacterium longum": "COMP_43BE32DB2D1B",
}

COMPONENT_DISPLAY_BY_ID = {
    "COMP_A9136ADF22F7": "Ácido fólico",
    "COMP_CCEF1C481D8D": "Ácido pantoténico",
    "COMP_AE7EE271FD2C": "Ashwagandha",
    "COMP_641FDABDC956": "Biotina",
    "COMP_4F582819D2E9": "Cafeína",
    "COMP_275450118D60": "Calcio",
    "COMP_0987F386BB65": "Carnitina",
    "COMP_8BB25B9A3BE5": "Coenzima Q10",
    "COMP_2671E7AB4CBB": "Colágeno",
    "COMP_A204C673A9A2": "Colina",
    "COMP_9C5C72058DB1": "Cobre",
    "COMP_7B47CDB437E8": "Creatina",
    "COMP_3F24EA59D864": "Cromo",
    "COMP_F71DD4665D9C": "DHA",
    "COMP_F3C5987AA984": "EPA",
    "COMP_B6A8F8958154": "Hierro",
    "COMP_E3D7A2D1C909": "L-teanina",
    "COMP_C873A4B5C00A": "Luteína",
    "COMP_83336712C554": "Magnesio",
    "COMP_5FCBE278ABF3": "Manganeso",
    "COMP_74AC5BE900AC": "Melatonina",
    "COMP_7A51909809FD": "Niacina",
    "COMP_447F5E523CED": "Omega 3",
    "COMP_BB2F708BF799": "Potasio",
    "COMP_C5CD8E1D6AAE": "Probióticos",
    "COMP_927AAC8EA873": "Proteína",
    "COMP_586F3B3DE0F3": "Riboflavina",
    "COMP_781B4EA1D853": "Selenio",
    "COMP_AFF3B61AB344": "Sodio",
    "COMP_0D2B15E9F9EE": "Taurina",
    "COMP_8F63E852ED34": "Té verde",
    "COMP_4F4F134A6B55": "Tiamina",
    "COMP_D691B9C2718F": "Valeriana",
    "COMP_90C4121BAE0C": "Vitamina A",
    "COMP_06B36D3A8FF3": "Vitamina B12",
    "COMP_FB0BFF3E6E21": "Vitamina B6",
    "COMP_67B16EEFC42F": "Vitamina C",
    "COMP_94DFE28A9A5C": "Vitamina D",
    "COMP_D4790F9775EF": "Vitamina E",
    "COMP_64DE5343502D": "Vitamina K",
    "COMP_22DA46FADFFD": "Yodo",
    "COMP_D02C918DB476": "Zeaxantina",
    "COMP_723DBC80CC4E": "Zinc",
    "COMP_430EB7DE720D": "Inositol",
    "COMP_5FA5A40B1A56": "Bacillus coagulans",
    "COMP_43BE32DB2D1B": "Bifidobacterium longum",
}


def _register_torch_cpu_fallback() -> None:
    """Allow artifacts saved on Apple MPS to load in Linux CPU containers."""
    global _TORCH_CPU_FALLBACK_REGISTERED
    if _TORCH_CPU_FALLBACK_REGISTERED:
        return

    try:
        import torch
    except ImportError:
        return

    def _deserialize_to_cpu(storage, location):
        if isinstance(location, str) and location.startswith("mps"):
            return storage.cpu()
        return None

    torch.serialization.register_package(
        priority=0,
        tagger=lambda _storage: None,
        deserializer=_deserialize_to_cpu,
    )
    _TORCH_CPU_FALLBACK_REGISTERED = True


def _load():
    global _artifacts
    if _artifacts is None:
        _register_torch_cpu_fallback()
        _artifacts = joblib.load(_ARTIFACTS_PATH)


def _normalize_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text.lower()).strip()
    return re.sub(r"\s+", " ", text)


def _clean_csv_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


@lru_cache(maxsize=1)
def _condition_component_links() -> list[dict]:
    if not _CONDITION_COMPONENT_LINKS_PATH.exists():
        return []

    df = pd.read_csv(_CONDITION_COMPONENT_LINKS_PATH)
    links = []
    for row in df.to_dict("records"):
        condition = str(row.get("condition_code") or "").strip()
        component = str(row.get("component") or "").strip()
        if not condition or not component:
            continue

        links.append(
            {
                "version": str(row.get("version") or "").strip(),
                "condition": condition,
                "component": component,
                "component_key": _normalize_text(component),
                "evidence_strength": str(row.get("evidence_strength") or "contextual").strip(),
                "evidence_type": str(row.get("evidence_type") or "unspecified").strip(),
                "recommendation_role": str(row.get("recommendation_role") or "supportive").strip(),
                "requires_lab": str(row.get("requires_lab") or "no").strip(),
                "risk_level": str(row.get("risk_level") or "low_moderate").strip(),
                "source_quality": str(row.get("source_quality") or "internal_rules").strip(),
                "missing_data_penalty": _safe_float(row.get("missing_data_penalty"), default=0.0),
                "source_ids": [
                    source.strip()
                    for source in str(row.get("source_ids") or "").split("|")
                    if source.strip()
                ],
                "rationale": str(row.get("rationale") or "").strip(),
            }
        )

    return links


@lru_cache(maxsize=1)
def _component_evidence_profiles() -> dict[str, dict]:
    if not _COMPONENT_EVIDENCE_PROFILES_PATH.exists():
        return {}

    df = pd.read_csv(_COMPONENT_EVIDENCE_PROFILES_PATH)
    profiles = {}
    for row in df.to_dict("records"):
        component = str(row.get("component") or "").strip()
        if not component:
            continue
        profile = {
            "component_profile_role": _clean_csv_text(row.get("profile_role")),
            "adult_upper_limit": _clean_csv_text(row.get("adult_upper_limit")),
            "upper_limit_unit": _clean_csv_text(row.get("upper_limit_unit")),
            "upper_limit_note": _clean_csv_text(row.get("upper_limit_note")),
            "dose_guidance": _clean_csv_text(row.get("dose_guidance")),
            "age_sex_note": _clean_csv_text(row.get("age_sex_note")),
            "pregnancy_lactation_note": _clean_csv_text(row.get("pregnancy_lactation_note")),
            "contraindications": [
                item.strip()
                for item in _clean_csv_text(row.get("contraindications")).split("|")
                if item.strip()
            ],
            "interaction_notes": _clean_csv_text(row.get("interaction_notes")),
            "component_safety_level": _clean_csv_text(row.get("safety_level")),
            "component_profile_source_ids": [
                item.strip()
                for item in _clean_csv_text(row.get("source_ids")).split("|")
                if item.strip()
            ],
            "component_profile_rationale": _clean_csv_text(row.get("rationale")),
        }
        profiles[_normalize_text(component)] = profile
    return profiles


def _component_profile(component: str) -> dict:
    return _component_evidence_profiles().get(_normalize_text(component), {})


@lru_cache(maxsize=1)
def _component_life_stage_guidance() -> dict[str, list[dict]]:
    if not _COMPONENT_LIFE_STAGE_GUIDANCE_PATH.exists():
        return {}

    df = pd.read_csv(_COMPONENT_LIFE_STAGE_GUIDANCE_PATH)
    grouped: dict[str, list[dict]] = {}
    for row in df.to_dict("records"):
        component = _clean_csv_text(row.get("component"))
        if not component:
            continue
        item = {
            "age_min": int(_safe_float(row.get("age_min"), default=0)),
            "age_max": int(_safe_float(row.get("age_max"), default=120)),
            "sex": _clean_csv_text(row.get("sex")),
            "pregnancy": _clean_csv_text(row.get("pregnancy")),
            "lactation": _clean_csv_text(row.get("lactation")),
            "reference_intake": _clean_csv_text(row.get("reference_intake")),
            "reference_unit": _clean_csv_text(row.get("reference_unit")),
            "reference_type": _clean_csv_text(row.get("reference_type")),
            "upper_limit": _clean_csv_text(row.get("upper_limit")),
            "upper_limit_unit": _clean_csv_text(row.get("upper_limit_unit")),
            "guidance_note": _clean_csv_text(row.get("guidance_note")),
            "source_ids": [
                source.strip()
                for source in _clean_csv_text(row.get("source_ids")).split("|")
                if source.strip()
            ],
        }
        grouped.setdefault(_normalize_text(component), []).append(item)
    return grouped


@lru_cache(maxsize=1)
def _component_interaction_rules() -> dict[str, list[dict]]:
    if not _COMPONENT_INTERACTION_RULES_PATH.exists():
        return {}

    df = pd.read_csv(_COMPONENT_INTERACTION_RULES_PATH)
    grouped: dict[str, list[dict]] = {}
    for row in df.to_dict("records"):
        component = _clean_csv_text(row.get("component"))
        if not component:
            continue
        item = {
            "interaction_type": _clean_csv_text(row.get("interaction_type")),
            "trigger_field": _clean_csv_text(row.get("trigger_field")),
            "trigger_value": _clean_csv_text(row.get("trigger_value")),
            "severity": _clean_csv_text(row.get("severity")),
            "action": _clean_csv_text(row.get("action")),
            "message": _clean_csv_text(row.get("message")),
            "source_ids": [
                source.strip()
                for source in _clean_csv_text(row.get("source_ids")).split("|")
                if source.strip()
            ],
        }
        grouped.setdefault(_normalize_text(component), []).append(item)
    return grouped


@lru_cache(maxsize=1)
def _component_claim_evidence() -> dict[str, list[dict]]:
    if not _COMPONENT_CLAIM_EVIDENCE_PATH.exists():
        return {}

    df = pd.read_csv(_COMPONENT_CLAIM_EVIDENCE_PATH)
    grouped: dict[str, list[dict]] = {}
    for row in df.to_dict("records"):
        component = _clean_csv_text(row.get("component"))
        if not component:
            continue
        item = {
            "claim_code": _clean_csv_text(row.get("claim_code")),
            "claim": _clean_csv_text(row.get("claim")),
            "evidence_level": _clean_csv_text(row.get("evidence_level")),
            "claim_type": _clean_csv_text(row.get("claim_type")),
            "source_ids": [
                source.strip()
                for source in _clean_csv_text(row.get("source_ids")).split("|")
                if source.strip()
            ],
            "display_note": _clean_csv_text(row.get("display_note")),
        }
        grouped.setdefault(_normalize_text(component), []).append(item)
    return grouped


def _context_age(user_context: dict | None) -> int | None:
    if not user_context:
        return None
    for key in ("age_years", "edad"):
        value = user_context.get(key)
        if value is None:
            continue
        try:
            return int(float(value))
        except (TypeError, ValueError):
            continue
    return None


def _context_sex(user_context: dict | None) -> str:
    if not user_context:
        return "any"
    value = _normalize_text(str(user_context.get("sexo") or user_context.get("sex") or ""))
    if value in {"femenino", "f"}:
        return "female"
    if value in {"masculino", "m"}:
        return "male"
    return "any"


def _context_security_conditions(user_context: dict | None) -> set[str]:
    if not user_context:
        return set()
    values = user_context.get("condiciones_seguridad") or user_context.get("safety_conditions") or []
    if not isinstance(values, list):
        return set()
    return {str(value) for value in values}


def _context_restrictions(user_context: dict | None) -> set[str]:
    if not user_context:
        return set()
    values = (
        user_context.get("restricciones_alergias")
        or user_context.get("allergies_restrictions")
        or user_context.get("restrictions")
        or []
    )
    if not isinstance(values, list):
        return set()
    normalized = {str(value) for value in values}
    aliases = {
        "alergia_pescado_mariscos": "pescado_mariscos",
        "alergia_lacteos": "lacteos",
        "alergia_soya": "soya",
    }
    for value in list(normalized):
        alias = aliases.get(value)
        if alias:
            normalized.add(alias)
    return normalized


def _matches_life_stage(row: dict, user_context: dict | None) -> bool:
    age = _context_age(user_context)
    sex = _context_sex(user_context)
    conditions = _context_security_conditions(user_context)
    pregnant = "embarazo_lactancia" in conditions
    lactating = "embarazo_lactancia" in conditions

    if age is not None and not (int(row["age_min"]) <= age <= int(row["age_max"])):
        return False

    row_sex = row.get("sex") or "any"
    if row_sex not in {"any", sex}:
        return False

    pregnancy = row.get("pregnancy") or "any"
    if pregnancy == "yes" and not pregnant:
        return False
    if pregnancy == "no" and pregnant:
        return False

    lactation = row.get("lactation") or "any"
    if lactation == "yes" and not lactating:
        return False
    if lactation == "no" and lactating:
        return False

    return True


def _component_life_stage_for_context(component: str, user_context: dict | None) -> list[dict]:
    rows = _component_life_stage_guidance().get(_normalize_text(component), [])
    matched = [row for row in rows if _matches_life_stage(row, user_context)]
    if matched:
        return matched[:3]
    return rows[:3]


def _interaction_applies(rule: dict, user_context: dict | None) -> bool:
    trigger_field = rule.get("trigger_field")
    trigger_value = rule.get("trigger_value")
    if trigger_value in {"", "any"}:
        return True
    if trigger_field == "requires_lab":
        return True
    if trigger_field == "lab_results":
        return bool(user_context and user_context.get("lab_results"))
    if trigger_field == "condiciones_seguridad":
        return trigger_value in _context_security_conditions(user_context)
    if trigger_field == "restricciones_alergias":
        return trigger_value in _context_restrictions(user_context)
    return False


def _component_interactions_for_context(component: str, user_context: dict | None) -> list[dict]:
    rows = _component_interaction_rules().get(_normalize_text(component), [])
    return [row for row in rows if _interaction_applies(row, user_context)]


def _component_claims(component: str) -> list[dict]:
    return _component_claim_evidence().get(_normalize_text(component), [])


def _component_display_name(component_id: str | None, fallback: str) -> str:
    if component_id and component_id in COMPONENT_DISPLAY_BY_ID:
        return COMPONENT_DISPLAY_BY_ID[component_id]
    return fallback


def _component_lookup_candidates(component_id: str | None, component_name: str) -> list[str]:
    candidates = []

    if component_id and component_id in COMPONENT_DISPLAY_BY_ID:
        candidates.append(COMPONENT_DISPLAY_BY_ID[component_id])
    if component_name:
        candidates.append(component_name)

    normalized_inputs = {_normalize_text(value) for value in candidates if value}
    for canonical_key, aliases in COMPONENT_ALIASES.items():
        normalized_aliases = {_normalize_text(alias) for alias in aliases}
        if canonical_key in normalized_inputs or normalized_inputs.intersection(normalized_aliases):
            candidates.append(canonical_key)
            continue
        if any(
            alias and any(alias in value or value in alias for value in normalized_inputs)
            for alias in normalized_aliases
        ):
            candidates.append(canonical_key)

    deduped = []
    seen = set()
    for candidate in candidates:
        key = _normalize_text(candidate)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _first_component_profile(candidates: list[str]) -> dict:
    for candidate in candidates:
        profile = _component_profile(candidate)
        if profile:
            return profile
    return {}


def _first_component_life_stage(candidates: list[str], user_context: dict | None) -> list[dict]:
    for candidate in candidates:
        guidance = _component_life_stage_for_context(candidate, user_context)
        if guidance:
            return guidance
    return []


def _first_component_interactions(candidates: list[str], user_context: dict | None) -> list[dict]:
    for candidate in candidates:
        interactions = _component_interactions_for_context(candidate, user_context)
        if interactions:
            return interactions
    return []


def _first_component_claims(candidates: list[str]) -> list[dict]:
    for candidate in candidates:
        claims = _component_claims(candidate)
        if claims:
            return claims
    return []


def _component_enrichment(component_id: str | None, component_name: str, user_context: dict | None) -> dict:
    display_name = _component_display_name(component_id, component_name)
    lookup_candidates = _component_lookup_candidates(component_id, component_name)
    return {
        **_first_component_profile(lookup_candidates),
        "component_lookup_candidates": [_normalize_text(candidate) for candidate in lookup_candidates],
        "life_stage_guidance": _first_component_life_stage(lookup_candidates, user_context),
        "interaction_rules": _first_component_interactions(lookup_candidates, user_context),
        "claim_evidence": _first_component_claims(lookup_candidates),
    }


def _blocking_interaction(interactions: list[dict]) -> dict | None:
    for interaction in interactions:
        if not isinstance(interaction, dict):
            continue
        if interaction.get("severity") != "high":
            continue
        if interaction.get("action") in {"block", "block_commercial", "block_or_warn"}:
            return interaction
        if interaction.get("action") == "warn_or_block":
            return interaction
    return None


def _commercial_decision(
    recommendation_role: str | None,
    interactions: list[dict],
    condition: str | None = None,
    *,
    allow_context_commercial: bool = True,
) -> tuple[bool, str]:
    blocking = _blocking_interaction(interactions)
    if blocking:
        return False, str(blocking.get("message") or "Interacción de seguridad alta.")

    if recommendation_role == "safety_context":
        return False, "Componente mostrado solo como contexto de seguridad."

    if condition in WELLNESS_CONTEXT_CONDITIONS:
        return (
            False,
            "Prioridad blanda de bienestar: se muestra como contexto, no como producto comercial directo.",
        )

    if condition in NON_COMMERCIAL_CONTEXT_CONDITIONS:
        return (
            False,
            "Señal contextual o biomédica: requiere evaluación profesional antes de productos comerciales.",
        )

    if not allow_context_commercial:
        return (
            False,
            "No hay una condición nutricional fuerte que respalde una recomendación comercial.",
        )

    return True, ""


def _recommendation_preference_key(item: dict) -> tuple[int, float, float]:
    condition = str(item.get("condicion") or "")
    commercial_priority = 0 if condition in NON_COMMERCIAL_CONTEXT_CONDITIONS else 1
    role_priority = 0 if item.get("recommendation_role") == "safety_context" else 1
    return (
        commercial_priority,
        role_priority,
        float(item.get("score") or 0.0),
    )


def _find_ids(query: str, master_names: pd.DataFrame) -> list[str]:
    clean_query = _normalize_text(query)
    if not clean_query:
        return []

    normalized_names = master_names["canonical_name"].map(_normalize_text)
    exact = master_names.loc[normalized_names == clean_query, "component_id"].tolist()
    if exact:
        return exact

    contains = master_names.loc[normalized_names.str.contains(re.escape(clean_query), na=False), "component_id"].tolist()
    if contains:
        return contains

    tokens = [token for token in clean_query.split() if len(token) >= 3]
    if tokens:
        mask = normalized_names.map(lambda value: all(token in value for token in tokens))
        return master_names.loc[mask, "component_id"].tolist()

    return []


def _resolve_component_id(component: str, artifacts: dict) -> tuple[str | None, str]:
    component_key = _normalize_text(component)
    comp_to_name = artifacts["comp_to_name"]
    master_names = artifacts["master_names"]

    override_id = COMPONENT_ID_OVERRIDES.get(component_key)
    if override_id:
        return override_id, component

    for alias in (component, *COMPONENT_ALIASES.get(component_key, ())):
        ids = _find_ids(alias, master_names)
        if ids:
            component_id = ids[0]
            return component_id, comp_to_name.get(component_id, alias)

    return None, component


def _evidence_weight(evidence_strength: str | None) -> float:
    return EVIDENCE_WEIGHTS.get(str(evidence_strength or "").strip().lower(), 0.55)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if np.isnan(number):
        return default
    return number


def _mapping_weight(mapping: dict[str, float], value: str | None, default: float) -> float:
    return mapping.get(str(value or "").strip().lower(), default)


def _evidence_score(link: dict, *, has_condition_scores: bool) -> tuple[float, dict[str, float]]:
    evidence_weight = _evidence_weight(link["evidence_strength"])
    role_weight = _mapping_weight(ROLE_WEIGHTS, link.get("recommendation_role"), 0.70)
    source_quality_weight = _mapping_weight(SOURCE_QUALITY_WEIGHTS, link.get("source_quality"), 0.70)
    lab_requirement_weight = _mapping_weight(LAB_REQUIREMENT_WEIGHTS, link.get("requires_lab"), 0.90)
    risk_penalty = _mapping_weight(RISK_LEVEL_PENALTIES, link.get("risk_level"), 0.08)
    missing_data_penalty = float(link.get("missing_data_penalty") or 0.0) if has_condition_scores else 0.0

    score = (
        evidence_weight * 0.36
        + role_weight * 0.22
        + source_quality_weight * 0.18
        + lab_requirement_weight * 0.14
        + (1.0 - risk_penalty) * 0.10
    )
    score = max(0.05, score - missing_data_penalty)

    return score, {
        "evidence_weight": evidence_weight,
        "role_weight": role_weight,
        "source_quality_weight": source_quality_weight,
        "lab_requirement_weight": lab_requirement_weight,
        "risk_penalty": risk_penalty,
        "missing_data_penalty": missing_data_penalty,
    }


def _condition_probability(condition: str, condition_scores: dict[str, float] | None) -> float:
    if not condition_scores:
        return 0.65

    try:
        value = float(condition_scores.get(condition, 0.0))
    except (TypeError, ValueError):
        return 0.0

    return max(0.0, min(1.0, value))


def _condition_rank_weight(condition: str, conditions: list[str], condition_scores: dict[str, float] | None) -> float:
    probability = _condition_probability(condition, condition_scores)
    if probability > 0:
        return probability
    return 0.60 if condition in conditions else 0.0


def _build_structured_component_recommendations(
    conditions: list[str],
    condition_scores: dict[str, float] | None,
    artifacts: dict,
    user_context: dict | None,
) -> list[dict]:
    recommendations_by_component: dict[str, dict] = {}

    for link in _condition_component_links():
        condition = link["condition"]
        if condition not in conditions:
            continue

        component_id, component_name = _resolve_component_id(link["component"], artifacts)
        if component_id is None:
            continue

        condition_probability = _condition_probability(condition, condition_scores)
        evidence_score, evidence_factors = _evidence_score(link, has_condition_scores=condition_scores is not None)
        score = round(max(0.05, condition_probability or 0.60) * evidence_score, 4)
        enrichment = _component_enrichment(component_id, link["component"], user_context)
        commercial_eligible, commercial_block_reason = _commercial_decision(
            link["recommendation_role"],
            enrichment["interaction_rules"],
            condition,
        )

        item = {
            "nombre": _component_display_name(component_id, component_name),
            "condicion": condition,
            "score": score,
            "component_id": component_id,
            "tipo": (
                "contexto_seguridad"
                if link["recommendation_role"] == "safety_context"
                else "semilla_directa"
            ),
            "source": "official_condition_component_link",
            "model2_ranker": RANKER_VERSION,
            "model2_stage": "evidence_validated",
            "commercial_eligible": commercial_eligible,
            "commercial_block_reason": commercial_block_reason,
            "condition_probability": condition_probability if condition_scores else None,
            "evidence_strength": link["evidence_strength"],
            "evidence_type": link["evidence_type"],
            "evidence_weight": evidence_factors["evidence_weight"],
            "evidence_score": round(evidence_score, 4),
            "evidence_factors": evidence_factors,
            "recommendation_role": link["recommendation_role"],
            "requires_lab": link["requires_lab"],
            "risk_level": link["risk_level"],
            "source_quality": link["source_quality"],
            "missing_data_penalty": link["missing_data_penalty"],
            "source_ids": link["source_ids"],
            "rationale": link["rationale"],
            **enrichment,
            "ranking_reason": (
                f"{link['component']} priorizado para {condition}: evidencia "
                f"{link['evidence_strength']}, rol {link['recommendation_role']}, "
                f"laboratorio {link['requires_lab']} y probabilidad {condition_probability:.2f}."
            ),
        }

        existing = recommendations_by_component.get(component_id)
        if existing is None or _recommendation_preference_key(item) > _recommendation_preference_key(existing):
            recommendations_by_component[component_id] = item

    return sorted(
        recommendations_by_component.values(),
        key=lambda item: (
            -float(item.get("score") or 0.0),
            str(item.get("condicion") or ""),
            str(item.get("nombre") or ""),
        ),
    )


def _fallback_seed_recommendations(
    conditions: list[str],
    condition_scores: dict[str, float] | None,
    artifacts: dict,
    existing_component_ids: set[str],
    covered_conditions: set[str],
    user_context: dict | None,
) -> list[dict]:
    comp_to_name = artifacts["comp_to_name"]
    cond_seeds = artifacts["condition_seeds"]
    recommendations = []

    for condition in sorted(conditions, key=lambda value: -_condition_rank_weight(value, conditions, condition_scores)):
        if condition in covered_conditions:
            continue

        for seed in cond_seeds.get(condition, []):
            component_id, component_name = _resolve_component_id(seed, artifacts)
            if component_id is None or component_id in existing_component_ids:
                continue

            score = round((_condition_rank_weight(condition, conditions, condition_scores) or 0.55) * 0.58, 4)
            display_name = _component_display_name(component_id, comp_to_name.get(component_id, component_name))
            enrichment = _component_enrichment(component_id, display_name, user_context)
            commercial_eligible, commercial_block_reason = _commercial_decision(
                "artifact_seed",
                enrichment["interaction_rules"],
                condition,
            )
            recommendations.append(
                {
                    "nombre": display_name,
                    "condicion": condition,
                    "score": score,
                    "component_id": component_id,
                    "tipo": "semilla_directa",
                    "source": "model2_artifact_seed",
                    "model2_ranker": RANKER_VERSION,
                    "model2_stage": "artifact_seed_fallback",
                    "commercial_eligible": commercial_eligible,
                    "commercial_block_reason": commercial_block_reason,
                    "condition_probability": _condition_probability(condition, condition_scores) if condition_scores else None,
                    "evidence_strength": "artifact_seed",
                    "evidence_weight": 0.58,
                    "source_ids": [],
                    **enrichment,
                    "ranking_reason": f"{component_name} agregado como semilla del artefacto Modelo 2 para {condition}.",
                }
            )
            existing_component_ids.add(component_id)
            break

    return recommendations


def recomendar_suplementos(
    conditions: list,
    condition_scores: dict[str, float] | None = None,
    user_context: dict | None = None,
    min_similarity: float = 0.3,
) -> dict:
    """
    Input : condiciones de Modelo 1  (ej: ['DEFICIT_VIT_D', 'BAJA_INMUNIDAD'])
    Output: dict con recomendaciones, sinergias, alertas, combo_seguro
    """
    _load()
    a = _artifacts

    if conditions == ["SALUDABLE"] or not conditions:
        return {
            "recomendaciones": [],
            "sinergias": [],
            "alertas": [],
            "combo_seguro": True,
            "mensaje": "Perfil saludable. Mantener dieta balanceada.",
        }

    conditions = [c for c in conditions if c != "SALUDABLE"]
    has_commercial_backing_condition = any(
        condition not in NON_COMMERCIAL_CONTEXT_CONDITIONS
        for condition in conditions
    )

    Z             = a["embeddings"]
    comp_to_idx   = a["comp_to_idx"]
    idx_to_comp   = a["idx_to_comp"]
    comp_to_name  = a["comp_to_name"]
    risky_pairs   = a["risky_pairs"]
    functional_pairs = a["functional_pairs"]
    cond_seeds    = a["condition_seeds"]
    master_names  = a["master_names"]
    edges_df      = a["edges_df_subset"]

    # ── Semillas directas ─────────────────────────────────────────────────────
    recomendaciones = _build_structured_component_recommendations(conditions, condition_scores, a, user_context)
    added_ids = {r["component_id"] for r in recomendaciones}
    covered_conditions = {str(r.get("condicion")) for r in recomendaciones if r.get("condicion")}
    recomendaciones.extend(
        _fallback_seed_recommendations(
            conditions,
            condition_scores,
            a,
            added_ids,
            covered_conditions,
            user_context,
        )
    )

    seed_valid = [r["component_id"] for r in recomendaciones if r.get("component_id") in comp_to_idx]

    if not seed_valid:
        return {"recomendaciones": [], "sinergias": [], "alertas": [],
                "combo_seguro": True, "mensaje": "Semillas no encontradas en grafo."}

    # ── Candidatos por similitud GNN ─────────────────────────────────────────
    seed_idxs = [comp_to_idx[sid] for sid in seed_valid]
    centroid  = Z[seed_idxs].mean(axis=0, keepdims=True)
    norms     = np.linalg.norm(Z, axis=1, keepdims=True) + 1e-8
    cos_sim   = (Z @ centroid.T).squeeze() / (norms.squeeze() * (np.linalg.norm(centroid) + 1e-8))

    seed_idx_set = set(seed_idxs)
    candidate_mask = np.ones(len(Z), dtype=bool)
    candidate_mask[list(seed_idx_set)] = False
    ranked = [i for i in np.argsort(-cos_sim)
              if candidate_mask[i] and cos_sim[i] >= min_similarity]

    for cand_idx in ranked[:20]:  # revisar top-20 candidatos GNN
        cand_id = idx_to_comp[cand_idx]
        if cand_id in added_ids:
            continue
        has_support = any(
            (cand_id, sid) in functional_pairs or (sid, cand_id) in functional_pairs
            for sid in seed_valid
        )
        if has_support:
            component_name = _component_display_name(cand_id, comp_to_name.get(cand_id, cand_id))
            enrichment = _component_enrichment(cand_id, component_name, user_context)
            commercial_eligible, commercial_block_reason = _commercial_decision(
                "graph_support",
                enrichment["interaction_rules"],
                "soporte_funcional",
                allow_context_commercial=has_commercial_backing_condition,
            )
            recomendaciones.append({
                "nombre":       component_name,
                "condicion":    "soporte_funcional",
                "score":        round(float(cos_sim[cand_idx]) * 0.45, 4),
                "component_id": cand_id,
                "tipo":         "candidato_gnn",
                "source":       "gnn_functional_similarity",
                "model2_ranker": RANKER_VERSION,
                "model2_stage":  "graph_support",
                "commercial_eligible": commercial_eligible,
                "commercial_block_reason": commercial_block_reason,
                "condition_probability": None,
                "evidence_strength": "supportive_graph",
                "evidence_weight": None,
                "graph_similarity": round(float(cos_sim[cand_idx]), 4),
                "source_ids": [],
                **enrichment,
                "ranking_reason": "Candidato complementario por similitud funcional con los componentes principales.",
            })
            added_ids.add(cand_id)
            if len([r for r in recomendaciones if r["tipo"] == "candidato_gnn"]) >= 3:
                break

    # Deduplicar
    seen, recs_dedup = set(), []
    for r in recomendaciones:
        if r["component_id"] not in seen:
            seen.add(r["component_id"])
            recs_dedup.append(r)

    rec_ids = [r["component_id"] for r in recs_dedup]

    # ── Sinergias ─────────────────────────────────────────────────────────────
    sinergias = []
    for i in range(len(rec_ids)):
        for j in range(i + 1, len(rec_ids)):
            a_id, b_id = rec_ids[i], rec_ids[j]
            if (a_id, b_id) in functional_pairs:
                rel = edges_df[
                    ((edges_df["component_id_a"] == a_id) & (edges_df["component_id_b"] == b_id)) |
                    ((edges_df["component_id_a"] == b_id) & (edges_df["component_id_b"] == a_id))
                ]["relationship_subclass"].values
                relation_type = rel[0] if len(rel) > 0 else "soporte_funcional"
                sinergias.append({
                    "component_a": _component_display_name(a_id, comp_to_name.get(a_id, a_id)),
                    "component_b": _component_display_name(b_id, comp_to_name.get(b_id, b_id)),
                    "component_a_id": a_id,
                    "component_b_id": b_id,
                    "type": relation_type,
                    "model2_stage": "graph_relationship",
                    "explanation": "Relación funcional del grafo usada como soporte, no como indicación médica.",
                })

    # ── Alertas ───────────────────────────────────────────────────────────────
    alertas = []
    for i in range(len(rec_ids)):
        for j in range(i + 1, len(rec_ids)):
            a_id, b_id = rec_ids[i], rec_ids[j]
            if (a_id, b_id) in risky_pairs or (b_id, a_id) in risky_pairs:
                alertas.append({
                    "component_a": _component_display_name(a_id, comp_to_name.get(a_id, a_id)),
                    "component_b": _component_display_name(b_id, comp_to_name.get(b_id, b_id)),
                    "component_a_id": a_id,
                    "component_b_id": b_id,
                    "type": "INTERACCION_RIESGOSA",
                    "model2_stage": "graph_safety_alert",
                    "explanation": "Relación riesgosa del grafo; requiere revisión antes de combinar componentes.",
                })

    combo_seguro = len(alertas) == 0
    return {
        "recomendaciones": recs_dedup,
        "sinergias":       sinergias,
        "alertas":         alertas,
        "combo_seguro":    combo_seguro,
        "mensaje":         "OK" if combo_seguro else f"{len(alertas)} interacción(es) riesgosa(s).",
        "model2_ranker_version": RANKER_VERSION,
    }
