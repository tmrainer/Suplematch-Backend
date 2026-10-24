"""Contrato de features compartido entre entrenamiento y runtime del Modelo 1 (condition_mvp).

Este modulo es la UNICA definicion de las columnas que consume el clasificador y de las
transformaciones deterministas que las derivan (senales blandas, metadatos de dieta y
laboratorio, relleno de faltantes). Lo importan:

- ``scripts/training/entrenar_modelo_condiciones.py`` (genera el dataset y entrena).
- ``app/ml/runtime/condition_mvp_inference.py`` (prepara el payload real antes de ``predict_proba``).
- ``tests/unit/test_features_contract.py`` (test de paridad estricto).

Si una columna cambia aqui, hay que subir ``FEATURE_CONTRACT_VERSION`` y reentrenar; el runtime
loguea un warning cuando el ``.pkl`` fue entrenado con otra version del contrato.

Este modulo no depende de ``app.core.config`` ni de scikit-learn para que el script de
entrenamiento pueda importarlo sin cargar la configuracion de la API.

Decisiones de paridad (ver docs/plan_fiabilidad.md Fase 3 y docs/condition_mvp_pipeline.md):

- Prevalece la version del RUNTIME porque es la que recibe los datos reales que produce
  ``FeatureBuilder``: 12 sintomas (incluye ``digestive_discomfort``), 8 cantidades de dieta
  (incluye ``fermented_foods_week`` y ``water_intake_l_day``) y 10 senales blandas.
- ``hair_skin_nails_cluster`` NO cuenta ``benchmark_diet_zinc_status`` (version runtime). El
  cluster agrega meta/sintomas autodeclarados mas laboratorios observados; el estatus dietario
  de zinc ya es feature propia y regla directa de DEFICIT_ZINC, y ``FeatureBuilder`` lo marca
  "low" para cualquier vegetariano con menos de 3 porciones de legumbres, asi que sumarlo al
  cluster lo haria alcanzar la regla ``gte 3`` solo con dieta declarada (doble conteo).
- Categoria faltante unica: ``MISSING_CATEGORY = "missing"``. El runtime usaba "unknown" para
  las categoricas de perfil, valor que el modelo nunca vio en entrenamiento.
"""

from __future__ import annotations

from typing import Any


# Fecha de la ultima modificacion incompatible del contrato. Se persiste en el .pkl como
# ``feature_contract_version``.
FEATURE_CONTRACT_VERSION = "2026-10-24.1"

MISSING_CATEGORY = "missing"


# ---------------------------------------------------------------------------------------------
# Columnas categoricas
# ---------------------------------------------------------------------------------------------

LAB_STATUS_COLS = [
    "lab_vitamin_d_status",
    "lab_b12_status",
    "lab_ferritin_status",
    "lab_hemoglobin_status",
    "lab_magnesium_status",
    "lab_zinc_status",
    "lab_calcium_status",
    "lab_folate_status",
    "lab_glucose_status",
    "lab_total_cholesterol_status",
    "lab_ldl_status",
    "lab_hdl_status",
    "lab_triglycerides_status",
    "lab_creatinine_status",
    "lab_egfr_status",
    "lab_alt_status",
    "lab_ast_status",
    "lab_tsh_status",
]

LAB_BASES = [col.removeprefix("lab_").removesuffix("_status") for col in LAB_STATUS_COLS]

BENCHMARK_STATUS_COLS = [
    "benchmark_lab_vitamin_c_status",
    "benchmark_diet_b12_status",
    "benchmark_diet_vitamin_c_status",
    "benchmark_diet_zinc_status",
    "benchmark_diet_magnesium_status",
    "benchmark_diet_calcium_status",
    "benchmark_diet_folate_status",
    "benchmark_diet_protein_status",
    "benchmark_diet_omega3_status",
]

DIET_STATUS_COLS = [col for col in BENCHMARK_STATUS_COLS if col.startswith("benchmark_diet_")]
LAB_BENCHMARK_STATUS_COLS = [col for col in BENCHMARK_STATUS_COLS if col.startswith("benchmark_lab_")]

# Laboratorios cuya alteracion dispara reglas SAFETY_* o contexto medico sensible.
MEDICAL_SAFETY_COLS = {
    "lab_creatinine_status",
    "lab_egfr_status",
    "lab_alt_status",
    "lab_ast_status",
    "lab_tsh_status",
    "lab_glucose_status",
    "lab_total_cholesterol_status",
    "lab_ldl_status",
    "lab_hdl_status",
    "lab_triglycerides_status",
}

PROFILE_CATEGORICAL_COLS = [
    "sexo",
    "tipo_dieta",
    "exposicion_solar",
    "nivel_actividad",
    "lab_panel_source",
]

CAT_COLS = PROFILE_CATEGORICAL_COLS + LAB_STATUS_COLS + BENCHMARK_STATUS_COLS


# ---------------------------------------------------------------------------------------------
# Columnas numericas
# ---------------------------------------------------------------------------------------------

ANTHROPOMETRIC_COLS = ["edad", "peso_kg", "altura_cm", "bmi"]

# Sintomas ordinales 1..5. ``digestive_discomfort`` viene de FeatureBuilder (encuesta ampliada).
SYMPTOM_COLS = [
    "fatiga_general",
    "dolor_muscular",
    "dolor_articular",
    "niebla_mental",
    "problemas_sueno",
    "caida_cabello",
    "piel_seca",
    "unas_quebradizas",
    "enfermedad_frecuente",
    "calambres",
    "irritabilidad",
    "digestive_discomfort",
]

SYMPTOM_AGGREGATE_COLS = ["symptom_burden_score", "high_symptom_count"]

# Banderas binarias de contexto. Desde 2026-10-24 los objetivos elegidos por la persona NO entran en las
# ``meta_*`` (solo sintomas, habitos y edad); los objetivos se usan para ordenar resultados. Las cuatro
# ultimas alimentan las senales blandas de bienestar (visual, digestiva, hidratacion, cardiovascular).
GOAL_CONTEXT_COLS = [
    "dieta_deficiente",
    "estres_alto",
    "meta_energia",
    "meta_inmunidad",
    "meta_belleza",
    "meta_rendimiento",
    "meta_salud_osea",
    "meta_cognitivo",
    "meta_visual",
    "meta_digestiva",
    "meta_hidratacion",
    "meta_cardiovascular",
]

# Cantidades de contexto con sentinela -1 cuando no se reportan (sin columna ``_reported``).
CONTEXT_QUANTITY_COLS = [
    "screen_hours_day",
    "heavy_sweat_days_week",
]

# Factores de riesgo declarados (contrato de encuesta 2026-10-24.1). Conteo de factores presentes; -1 si la
# persona no respondio ninguna de las preguntas del grupo. Ver FeatureBuilder.build_pipeline_payload.
RISK_FACTOR_COLS = [
    "iron_loss_risk",  # menstruacion abundante, parto en el ultimo año, donar sangre 2+ veces/año
    "vitamin_d_sun_barrier",  # protector solar siempre, solo cara y manos al sol
    "b12_absorption_risk",  # metformina, antiacidos/IBP, dieta vegetal >3 años sin B12
]

# Cantidades dietarias declaradas; -1 cuando no se reportan, con su bandera ``<col>_reported``.
DIET_QUANTITY_COLS = [
    "fish_servings_week",
    "dairy_servings_day",
    "legume_servings_week",
    "meat_servings_week",
    "fruit_veg_servings_day",
    "protein_g_day_estimate",
    "fermented_foods_week",
    "water_intake_l_day",
]

DIET_META_COLS = [f"{col}_reported" for col in DIET_QUANTITY_COLS] + ["diet_quantity_missing_count"]

# Senales derivadas por ``attach_soft_signal_features``; son deterministas a partir del resto.
SOFT_SIGNAL_COLS = [
    "vitamin_c_diet_signal",
    "protein_insufficient_signal",
    "protein_gap_g_day",
    "hair_skin_nails_cluster",
    "visual_strain_signal",
    "digestive_support_signal",
    "hydration_electrolyte_signal",
    "fatigue_nutrition_signal",
    "cardiovascular_context_signal",
    "cognitive_context_signal",
]

LAB_COUNT_COLS = ["observed_lab_count", "missing_lab_count"]

LAB_META_COLS = [
    item
    for base in LAB_BASES
    for item in (
        f"lab_{base}_observed",
        f"lab_{base}_age_days",
        f"lab_{base}_unit_known",
        f"lab_{base}_range_known",
    )
]

NUM_COLS = (
    ANTHROPOMETRIC_COLS
    + SYMPTOM_COLS
    + GOAL_CONTEXT_COLS
    + CONTEXT_QUANTITY_COLS
    + RISK_FACTOR_COLS
    + SYMPTOM_AGGREGATE_COLS
    + LAB_COUNT_COLS
    + DIET_QUANTITY_COLS
    + DIET_META_COLS
    + SOFT_SIGNAL_COLS
    + LAB_META_COLS
)

MODEL_FEATURE_COLS = CAT_COLS + NUM_COLS

# Agrupaciones usadas por el runtime para etiquetar la procedencia de cada regla coincidente.
PROFILE_CONTEXT_COLS = {"sexo", *ANTHROPOMETRIC_COLS}
SURVEY_CONTEXT_COLS = {
    "tipo_dieta",
    "exposicion_solar",
    "nivel_actividad",
    *GOAL_CONTEXT_COLS,
    *CONTEXT_QUANTITY_COLS,
    *RISK_FACTOR_COLS,
}

# Claves que ``FeatureBuilder.build_pipeline_payload`` emite pero que NO son features del
# modelo. Son insumos crudos que el builder ya pliega en otra feature del contrato; se mantienen
# en el payload por trazabilidad/explicabilidad. El test de paridad exige que el conjunto de
# claves fuera de contrato sea exactamente este.
BUILDER_ONLY_KEYS = frozenset(
    {
        "red_meat_servings_week",  # -> meat_servings_week y protein_g_day_estimate
        "poultry_servings_week",  # -> meat_servings_week y protein_g_day_estimate
        "eggs_servings_week",  # -> protein_g_day_estimate
        "headache_days_week",  # -> meta_hidratacion
        "fatigue_days_week",  # -> fatiga_general
        "alcohol_drinks_week",  # -> enfermedad_frecuente / meta_inmunidad
        "caffeine_servings_day",  # -> irritabilidad / problemas_sueno
        "exercise_days_week",  # -> nivel_actividad
    }
)


# ---------------------------------------------------------------------------------------------
# Valores por defecto del runtime cuando el payload no trae una feature
# ---------------------------------------------------------------------------------------------

def default_feature_values() -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "sexo": "F",
        "tipo_dieta": "omnivoro",
        "exposicion_solar": "media",
        "nivel_actividad": "moderado",
        "lab_panel_source": "none",
        "edad": 30,
        "peso_kg": 70.0,
        "altura_cm": 165.0,
        "bmi": 25.7,
    }
    for col in SYMPTOM_COLS:
        defaults[col] = 1
    for col in GOAL_CONTEXT_COLS:
        defaults[col] = 0
    for col in DIET_QUANTITY_COLS:
        defaults[col] = -1.0
    defaults["screen_hours_day"] = -1.0
    defaults["heavy_sweat_days_week"] = -1
    for col in RISK_FACTOR_COLS:
        defaults[col] = -1
    for col in LAB_STATUS_COLS + BENCHMARK_STATUS_COLS:
        defaults[col] = MISSING_CATEGORY
    return defaults


# ---------------------------------------------------------------------------------------------
# Reglas
# ---------------------------------------------------------------------------------------------

def rule_matches(features: dict[str, Any], rule: dict[str, Any]) -> bool:
    """Evalua una regla ``{field, operator, value}`` sobre un payload de features.

    Los sentinelas negativos (cantidad no reportada) nunca cumplen comparaciones numericas.
    """
    value = features.get(rule["field"])
    expected = rule.get("value")
    operator = rule["operator"]
    if operator == "eq":
        return value == expected
    if operator == "in":
        return value in set(expected)
    if operator == "contains":
        return isinstance(value, list) and expected in value
    if value is None:
        return False
    numeric_value = float(value)
    if numeric_value < 0:
        return False
    if operator == "gte":
        return numeric_value >= float(expected)
    if operator == "lte":
        return numeric_value <= float(expected)
    if operator == "lt":
        return numeric_value < float(expected)
    raise ValueError(f"Operador no soportado: {operator}")


# ---------------------------------------------------------------------------------------------
# Agregacion de reglas por familia de evidencia (2026-10-24)
# ---------------------------------------------------------------------------------------------

# Cada dato crudo usado en reglas pertenece a UNA familia de evidencia. Varias reglas de una condicion sobre la misma
# familia describen el mismo hecho (p. ej. ``fruit_veg_servings_day <= 2`` y ``benchmark_diet_vitamin_c_status`` salen
# de "frutas y verduras"); con la suma simple ese hecho contaba varias veces. En modo "family" cada familia aporta UNA
# vez: el maximo entre sus campos. Las reglas sobre el MISMO campo si se suman (escalones disenados como
# ``iron_loss_risk >= 1`` y ``>= 2``, o valores excluyentes ``low`` / ``critical_low``). Los pesos no cambian.
RULE_FAMILIES: dict[str, str] = {
    # Perfil
    "edad": "age",
    "sexo": "sex",
    "bmi": "body_size",
    # Habitos
    "exposicion_solar": "sun",
    "vitamin_d_sun_barrier": "sun_barrier",
    "nivel_actividad": "activity",
    "screen_hours_day": "screen",
    "water_intake_l_day": "water_intake",
    "heavy_sweat_days_week": "sweat",
    # Alimentacion por grupo (cantidad declarada y estados que se calculan de ella)
    "fruit_veg_servings_day": "fruit_veg",
    "benchmark_diet_vitamin_c_status": "fruit_veg",
    "protein_g_day_estimate": "protein_intake",
    "protein_gap_g_day": "protein_intake",
    "protein_insufficient_signal": "protein_intake",
    "benchmark_diet_protein_status": "protein_intake",
    "fish_servings_week": "fish",
    "benchmark_diet_omega3_status": "fish",
    "dairy_servings_day": "dairy",
    "benchmark_diet_calcium_status": "dairy",
    "legume_servings_week": "legumes",
    "benchmark_diet_magnesium_status": "legumes",
    "benchmark_diet_folate_status": "legumes",
    "tipo_dieta": "animal_foods",
    "meat_servings_week": "animal_foods",
    "benchmark_diet_b12_status": "animal_foods",
    "benchmark_diet_zinc_status": "animal_foods",
    "fermented_foods_week": "fermented",
    # Sintomas
    "fatiga_general": "fatigue",
    "problemas_sueno": "sleep",
    "irritabilidad": "stress",
    "estres_alto": "stress",
    "niebla_mental": "brain_fog",
    "enfermedad_frecuente": "illness",
    "caida_cabello": "hair",
    "piel_seca": "skin",
    "unas_quebradizas": "nails",
    "dolor_muscular": "muscle",
    "calambres": "cramps",
    "digestive_discomfort": "digestive",
    # Factores de riesgo declarados
    "iron_loss_risk": "iron_loss",
    "b12_absorption_risk": "b12_absorption",
}

DIET_FAMILIES = frozenset({"fruit_veg", "protein_intake", "fish", "dairy", "legumes", "animal_foods"})

# Señales derivadas que son un "O" (o un "Y") de datos crudos: p. ej. ``meta_cognitivo`` = estres alto O sueño corto.
# Son proxies: solo cuentan si NINGUNA de sus familias componentes ya conto por un dato crudo en esa condicion, y al
# contar reclaman sus componentes (otro proxy que se solape ya no suma). Asi dormir poco no suma tres veces via
# ``problemas_sueno``, ``meta_cognitivo`` y ``cognitive_context_signal``.
PROXY_COMPONENTS: dict[str, frozenset[str]] = {
    "dieta_deficiente": DIET_FAMILIES | {"diet_general"},
    "meta_energia": frozenset({"fatigue", "sleep"}) | DIET_FAMILIES,
    "meta_inmunidad": frozenset({"illness"}),
    "meta_belleza": frozenset({"hair", "skin", "nails"}),
    "meta_rendimiento": frozenset({"activity"}),
    "meta_salud_osea": frozenset({"sun", "age"}) | DIET_FAMILIES,
    "meta_cognitivo": frozenset({"sleep", "stress"}),
    "meta_visual": frozenset({"screen"}),
    "meta_digestiva": frozenset({"digestive"}),
    "meta_hidratacion": frozenset({"cramps", "sweat", "headache"}),  # calambres, cefalea frecuente o sudor intenso
    "meta_cardiovascular": frozenset({"age"}),
    "vitamin_c_diet_signal": frozenset({"fruit_veg", "illness"}) | DIET_FAMILIES,
    "hair_skin_nails_cluster": frozenset({"hair", "skin", "nails", "lab_zinc_status", "lab_ferritin_status"}),
    "visual_strain_signal": frozenset({"screen", "fruit_veg"}),
    "digestive_support_signal": frozenset({"digestive", "fermented"}) | DIET_FAMILIES,
    "hydration_electrolyte_signal": frozenset({"water_intake", "sweat", "cramps", "headache"}),
    "fatigue_nutrition_signal": frozenset({"fatigue"}) | DIET_FAMILIES,
    "cardiovascular_context_signal": frozenset({"age", "fish", "lab_total_cholesterol_status", "lab_ldl_status"}),
    "cognitive_context_signal": frozenset({"sleep", "stress", "brain_fog", "fatigue"}),
}

RULE_AGGREGATION_MODES = ("family", "sum")


def rule_family(field: str) -> str:
    """Familia de un campo. Cada laboratorio es su propia familia (medicion directa); los proxies se reportan aparte."""
    if field.startswith("lab_") or field.startswith("benchmark_lab_"):
        return field
    if field in PROXY_COMPONENTS:
        return f"proxy:{field}"
    return RULE_FAMILIES.get(field, field)


def is_observed_lab_family(family: str) -> bool:
    return family.startswith("lab_") or family.startswith("benchmark_lab_")


def aggregate_rule_score(matched_rules: list[dict[str, Any]], mode: str = "family") -> tuple[float, dict[str, float]]:
    """Puntaje de reglas coincidentes y aporte por familia.

    ``mode="sum"`` reproduce el comportamiento anterior (suma de todas las reglas). ``mode="family"`` suma una vez
    por familia cruda y agrega proxies solo si no repiten una familia ya contada.
    """
    if mode not in RULE_AGGREGATION_MODES:
        raise ValueError(f"Modo de agregacion no soportado: {mode}")
    raw: dict[str, dict[str, float]] = {}
    proxies: dict[str, float] = {}
    for rule in matched_rules:
        field = str(rule["field"])
        weight = float(rule.get("weight", 0.0))
        if field in PROXY_COMPONENTS:
            proxies[field] = proxies.get(field, 0.0) + weight
        else:
            fields = raw.setdefault(rule_family(field), {})
            fields[field] = fields.get(field, 0.0) + weight
    if mode == "sum":
        total = sum(sum(fields.values()) for fields in raw.values()) + sum(proxies.values())
        families = {family: sum(fields.values()) for family, fields in raw.items()}
        families.update({f"proxy:{field}": weight for field, weight in proxies.items()})
        return round(total, 4), families

    families = {family: max(fields.values()) for family, fields in raw.items()}
    claimed = set(families)
    for field, weight in sorted(proxies.items(), key=lambda item: -item[1]):
        components = PROXY_COMPONENTS[field]
        if components & claimed:
            continue
        families[f"proxy:{field}"] = weight
        claimed |= components
    return round(sum(families.values()), 4), families


def max_survey_score(rules: list[dict[str, Any]], mode: str = "family") -> float:
    """Puntaje maximo que puede alcanzar una condicion solo con encuesta (sin laboratorios).

    Supone todas las reglas de encuesta activas a la vez, salvo valores excluyentes de un mismo campo (se toma el
    de mayor peso); los escalones ``gte`` de un mismo campo se acumulan.
    """
    best: dict[tuple[str, str], Any] = {}
    for rule in rules:
        field = str(rule["field"])
        if rule_family(field).startswith(("lab_", "benchmark_lab_")):
            continue
        if rule.get("operator") == "gte":
            best.setdefault(("ladder", field), []).append(rule)
            continue
        key = ("single", field)
        if key not in best or float(best[key]["weight"]) < float(rule["weight"]):
            best[key] = rule
    chosen: list[dict[str, Any]] = []
    for value in best.values():
        chosen.extend(value if isinstance(value, list) else [value])
    return aggregate_rule_score(chosen, mode)[0]


def _top_two_raw_families(rules: list[dict[str, Any]]) -> float | None:
    """Suma de las dos familias crudas de encuesta con mayor peso (sin proxies ni laboratorios)."""
    by_family: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for rule in rules:
        field = str(rule["field"])
        family = rule_family(field)
        if field in PROXY_COMPONENTS or family.startswith(("lab_", "benchmark_lab_")):
            continue
        by_family.setdefault(family, {}).setdefault(field, []).append(rule)
    values = []
    for fields in by_family.values():
        best = 0.0
        for items in fields.values():
            if all(item.get("operator") == "gte" for item in items):
                value = sum(float(item["weight"]) for item in items)  # escalones acumulables
            else:
                value = max(float(item["weight"]) for item in items)  # valores excluyentes
            best = max(best, value)
        values.append(best)
    values.sort(reverse=True)
    return round(sum(values[:2]), 4) if len(values) >= 2 else None


def family_rule_threshold(rules: list[dict[str, Any]], threshold: float) -> float:
    """Umbral de reglas para el modo "family".

    Los umbrales de conditions.csv se calibraron con la suma simple. Si una condicion solo llegaba a su umbral con
    encuesta gracias al doble conteo (max con suma >= umbral > max por familia), su umbral pasa a ser la suma de sus
    dos señales independientes mas fuertes: con ellas basta, coherente con la confirmacion cruzada. El resto conserva
    el umbral original, incluidas las que solo se detectan con laboratorio.
    """
    family_max = max_survey_score(rules, "family")
    sum_max = max_survey_score(rules, "sum")
    if family_max >= threshold or sum_max < threshold:
        return threshold
    top_two = _top_two_raw_families(rules)
    return threshold if top_two is None else min(threshold, top_two)


def rule_thresholds(
    condition_rules: dict[str, list[dict[str, Any]]], thresholds: dict[str, float], mode: str = "family",
) -> dict[str, float]:
    """Umbral de reglas por condicion segun el modo (``family_rule_threshold`` en "family"; el original en "sum")."""
    if mode == "sum":
        return dict(thresholds)
    return {code: family_rule_threshold(condition_rules.get(code, []), value) for code, value in thresholds.items()}


def is_corroborated(families: dict[str, float], mode: str = "family") -> bool:
    """Sin laboratorio, un positivo necesita al menos dos familias de evidencia independientes.

    Evita que un solo hecho (p. ej. dormir menos de 7 horas) marque una condicion. Con un laboratorio observado
    basta esa medicion. En modo "sum" no se exige (comportamiento anterior).
    """
    if mode == "sum":
        return True
    if any(is_observed_lab_family(family) for family in families):
        return True
    return len(families) >= 2


# ---------------------------------------------------------------------------------------------
# Derivaciones deterministas
# ---------------------------------------------------------------------------------------------

def attach_soft_signal_features(row: dict[str, Any]) -> None:
    """Calcula ``SOFT_SIGNAL_COLS`` in place.

    Usa ``setdefault`` para respetar senales ya presentes (casos reales curados que las traen
    explicitas); en entrenamiento y en el payload de ``FeatureBuilder`` nunca vienen, asi que
    siempre se recalculan.
    """
    fruit_veg_reported = int(row.get("fruit_veg_servings_day_reported", 0))
    fruit_veg = float(row.get("fruit_veg_servings_day", -1))
    row.setdefault(
        "vitamin_c_diet_signal",
        int(
            bool(fruit_veg_reported)
            and fruit_veg <= 2
            and (
                int(row.get("dieta_deficiente", 0)) == 1
                or int(row.get("enfermedad_frecuente", 0)) >= 4
                or int(row.get("meta_inmunidad", 0)) == 1
            )
        ),
    )

    protein_reported = int(row.get("protein_g_day_estimate_reported", 0))
    protein = float(row.get("protein_g_day_estimate", -1))
    activity_multiplier = 1.2 if row.get("nivel_actividad") in {"activo", "muy_activo"} else 0.85
    protein_target = float(row.get("peso_kg", 70.0)) * activity_multiplier
    protein_gap = max(0.0, protein_target - protein) if protein_reported else -1.0
    row.setdefault("protein_gap_g_day", round(protein_gap, 2))
    row.setdefault(
        "protein_insufficient_signal",
        int(
            bool(protein_reported)
            and (
                protein < 55
                or protein_gap >= 20
                or (
                    row.get("nivel_actividad") in {"activo", "muy_activo"}
                    and protein_gap >= 12
                    and int(row.get("meta_rendimiento", 0)) == 1
                )
            )
        ),
    )

    # Ver docstring del modulo: benchmark_diet_zinc_status queda fuera a proposito.
    hair_skin_hits = [
        int(row.get("meta_belleza", 0)) == 1,
        int(row.get("caida_cabello", 0)) >= 4,
        int(row.get("piel_seca", 0)) >= 4,
        int(row.get("unas_quebradizas", 0)) >= 4,
        row.get("lab_zinc_status") in {"low", "critical_low"},
        row.get("lab_ferritin_status") in {"low", "critical_low"},
    ]
    row.setdefault("hair_skin_nails_cluster", sum(1 for hit in hair_skin_hits if hit))

    screen_hours = float(row.get("screen_hours_day", -1))
    screen_reported = screen_hours >= 0
    row.setdefault(
        "visual_strain_signal",
        int(
            (int(row.get("meta_visual", 0)) == 1 or (screen_reported and screen_hours >= 6))
            and (fruit_veg <= 2 if fruit_veg_reported else True)
        ),
    )

    fermented_foods = float(row.get("fermented_foods_week", -1))
    fermented_reported = fermented_foods >= 0
    digestive_discomfort = int(row.get("digestive_discomfort", 1))
    row.setdefault(
        "digestive_support_signal",
        int(
            int(row.get("meta_digestiva", 0)) == 1
            or digestive_discomfort >= 3
            or (fermented_reported and fermented_foods <= 1 and int(row.get("dieta_deficiente", 0)) == 1)
        ),
    )

    water_l_day = float(row.get("water_intake_l_day", -1))
    water_reported = water_l_day >= 0
    heavy_sweat_days = int(row.get("heavy_sweat_days_week", -1))
    row.setdefault(
        "hydration_electrolyte_signal",
        int(
            int(row.get("meta_hidratacion", 0)) == 1
            or (water_reported and water_l_day <= 1.2)
            or heavy_sweat_days >= 3
            or int(row.get("calambres", 1)) >= 3
        ),
    )

    row.setdefault(
        "fatigue_nutrition_signal",
        int(
            int(row.get("fatiga_general", 1)) >= 4
            and (
                int(row.get("dieta_deficiente", 0)) == 1
                or row.get("benchmark_diet_b12_status") in {"low", "critical_low"}
                or row.get("benchmark_diet_protein_status") in {"low", "critical_low"}
            )
        ),
    )

    fish = float(row.get("fish_servings_week", -1))
    row.setdefault(
        "cardiovascular_context_signal",
        int(
            int(row.get("meta_cardiovascular", 0)) == 1
            or row.get("lab_total_cholesterol_status") == "high"
            or row.get("lab_ldl_status") == "high"
            or (int(row.get("edad", 30)) >= 50 and 0 <= fish <= 1)
        ),
    )

    row.setdefault(
        "cognitive_context_signal",
        int(
            int(row.get("meta_cognitivo", 0)) == 1
            or int(row.get("niebla_mental", 1)) >= 3
            or (int(row.get("problemas_sueno", 1)) >= 4 and int(row.get("fatiga_general", 1)) >= 3)
        ),
    )


def prepare_features(features: dict[str, Any], cat_cols: list[str], num_cols: list[str]) -> dict[str, Any]:
    """Completa un payload parcial hasta tener todas las columnas que espera el pipeline.

    ``cat_cols``/``num_cols`` son las listas guardadas en el ``.pkl`` (normalmente iguales a
    ``CAT_COLS``/``NUM_COLS``). El resultado conserva las claves extra del payload
    (``BUILDER_ONLY_KEYS``); el runtime selecciona solo ``cat_cols + num_cols`` para predecir.
    """
    row_payload = {**default_feature_values(), **features}

    # Un None explicito en una categorica equivale a "no disponible". Se normaliza ANTES de
    # derivar metadatos para que lab_*_observed/observed_lab_count no cuenten como observado un
    # laboratorio cuyo estatus es None (bug detectado por test_features_contract).
    for col in cat_cols:
        if row_payload.get(col) is None:
            row_payload[col] = MISSING_CATEGORY

    diet_missing_count = 0
    for col in DIET_QUANTITY_COLS:
        reported = 1 if float(row_payload.get(col, -1)) >= 0 else 0
        diet_missing_count += 0 if reported else 1
        row_payload.setdefault(f"{col}_reported", reported)
    row_payload.setdefault("diet_quantity_missing_count", diet_missing_count)

    observed_lab_count = 0
    for status_col in LAB_STATUS_COLS:
        base = status_col.removeprefix("lab_").removesuffix("_status")
        observed = 0 if row_payload.get(status_col, MISSING_CATEGORY) == MISSING_CATEGORY else 1
        observed_lab_count += observed
        row_payload.setdefault(f"lab_{base}_observed", observed)
        row_payload.setdefault(f"lab_{base}_age_days", 999 if not observed else 30)
        row_payload.setdefault(f"lab_{base}_unit_known", observed)
        row_payload.setdefault(f"lab_{base}_range_known", observed)
    row_payload.setdefault("observed_lab_count", observed_lab_count)
    row_payload.setdefault("missing_lab_count", len(LAB_STATUS_COLS) - observed_lab_count)

    row_payload.setdefault(
        "symptom_burden_score",
        round(sum(float(row_payload[col]) for col in SYMPTOM_COLS) / len(SYMPTOM_COLS), 3),
    )
    row_payload.setdefault("high_symptom_count", sum(1 for col in SYMPTOM_COLS if int(row_payload[col]) >= 4))
    attach_soft_signal_features(row_payload)

    for col in cat_cols:
        row_payload[col] = str(row_payload.get(col, MISSING_CATEGORY))
    for col in num_cols:
        if row_payload.get(col) is None:
            row_payload[col] = 0
    return row_payload
