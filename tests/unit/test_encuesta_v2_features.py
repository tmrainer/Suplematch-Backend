"""Cambios de encuesta del contrato 2026-10-24.1: objetivos fuera de la deteccion, faltante != cero, factores
protectores y de riesgo, seguimiento de fatiga y orden por objetivos."""

from __future__ import annotations

from app.domains.survey.esquemas_encuesta import EncuestaInput
from app.ml.feature_builder import FeatureBuilder
from app.ml.features_contract import GOAL_CONTEXT_COLS, RISK_FACTOR_COLS

FULL_FOOD = {
    "red_meat_servings_week": 3,
    "poultry_servings_week": 7,
    "fish_servings_week": 1,
    "eggs_servings_week": 5,
    "legume_servings_week": 3,
    "dairy_servings_week": 7,
}


def _build(**overrides) -> dict:
    data = {
        "edad_rango": "31_50",
        "horas_sueno": "7_9h",
        "frecuencia_ejercicio": "1_2_semana",
        "dieta": "regular",
        "fatiga": "a_veces",
        "exposicion_solar": "15_30min",
        "frecuencia_enfermedad": "1_2_anio",
        "estres": "moderado",
        "alcohol": "nunca",
        "weight_kg": 70,
    }
    data.update(overrides)
    return FeatureBuilder().build_pipeline_payload(EncuestaInput(**data))


def test_goals_do_not_change_any_detection_feature() -> None:
    plain = _build()
    with_goals = _build(objetivos=["energia", "rendimiento", "salud_osea", "salud_visual"], objetivo_principal="energia")
    assert plain == with_goals
    assert all(plain[col] == with_goals[col] for col in GOAL_CONTEXT_COLS)


def test_partial_food_block_is_missing_not_zero() -> None:
    partial = _build(fish_servings_week=1, poultry_servings_week=7)
    assert partial["protein_g_day_estimate"] == -1.0
    assert partial["benchmark_diet_protein_status"] == "missing"
    assert partial["meat_servings_week"] == -1.0  # carne roja sin responder: no se suma como 0
    assert partial["benchmark_diet_zinc_status"] == "missing"


def test_full_food_block_estimates_protein_with_staples_base() -> None:
    features = _build(**FULL_FOOD)
    # (3*25 + 7*25 + 1*22 + 5*6 + 3*12 + 7*8) / 7 + 15 g de cereales/tuberculos
    expected = round((75 + 175 + 22 + 30 + 36 + 56) / 7 + FeatureBuilder.BASE_PROTEIN_OTHER_FOODS_G, 2)
    assert features["protein_g_day_estimate"] == expected
    assert features["benchmark_diet_protein_status"] == "normal"


def test_diet_type_implies_zero_for_excluded_groups() -> None:
    vegan = _build(tipo_dieta="vegano", legume_servings_week=7)
    assert vegan["protein_g_day_estimate"] > 0  # carnes, pescado, huevos y lacteos se toman como 0
    omnivore = _build(legume_servings_week=7)
    assert omnivore["protein_g_day_estimate"] == -1.0


def test_two_daily_dairy_servings_are_not_low_calcium() -> None:
    # La escala nueva llega a 14/semana (2+ al dia); con el tope anterior (7) el calcio siempre salia bajo.
    assert _build(dairy_servings_week=14)["benchmark_diet_calcium_status"] == "normal"
    assert _build(dairy_servings_week=7)["benchmark_diet_calcium_status"] in {"low", "critical_low"}


def test_regular_diet_alone_is_not_deficient() -> None:
    assert _build(dieta="regular")["dieta_deficiente"] == 0
    assert _build(dieta="poco_variada")["dieta_deficiente"] == 1
    assert _build(dieta="bastante_variada", tipo_dieta="vegetariano")["dieta_deficiente"] == 0


def test_protein_supplement_adds_to_estimate_only_when_food_known() -> None:
    base = _build(**FULL_FOOD)["protein_g_day_estimate"]
    with_shake = _build(**FULL_FOOD, toma_suplementos="si", suplementos_actuales=["proteina"])
    assert with_shake["protein_g_day_estimate"] == round(base + FeatureBuilder.PROTEIN_SUPPLEMENT_DEFAULT_G, 2)
    no_food = _build(toma_suplementos="si", suplementos_actuales=["proteina"])
    assert no_food["protein_g_day_estimate"] == -1.0


def test_b12_coverage_and_vegan_duration() -> None:
    assert _build(tipo_dieta="vegano")["benchmark_diet_b12_status"] == "critical_low"
    assert _build(tipo_dieta="vegano", alimentos_fortificados_b12="si")["benchmark_diet_b12_status"] == "normal"
    assert _build(tipo_dieta="vegano", toma_suplementos="si", suplementos_actuales=["vitamina_b12"])["benchmark_diet_b12_status"] == "normal"
    assert _build(tipo_dieta="vegano", anios_dieta_vegetal="menos_1")["benchmark_diet_b12_status"] == "low"


def test_risk_factor_counts_and_missing_sentinel() -> None:
    empty = _build()
    assert all(empty[col] == -1 for col in RISK_FACTOR_COLS)
    iron = _build(sexo="femenino", menstruacion_abundante="si", parto_ultimo_anio="no", dona_sangre="2_o_mas_al_anio")
    assert iron["iron_loss_risk"] == 2
    assert _build(dona_sangre="no")["iron_loss_risk"] == 0
    assert _build(protector_solar="siempre", piel_expuesta="cara_manos")["vitamin_d_sun_barrier"] == 1
    assert _build(protector_solar="siempre")["vitamin_d_sun_barrier"] == -1  # el protector solo ya no es barrera
    assert _build(medicamentos_b12=["metformina", "antiacidos_ibp"])["b12_absorption_risk"] == 2
    assert _build(tipo_dieta="vegano", anios_dieta_vegetal="mas_3")["b12_absorption_risk"] == 1
    assert _build(tipo_dieta="vegano", anios_dieta_vegetal="mas_3", alimentos_fortificados_b12="si")["b12_absorption_risk"] == 0


def test_fatigue_follow_up_caps_transient_or_sleep_explained_fatigue() -> None:
    assert _build(fatiga="siempre")["fatiga_general"] == 5
    assert _build(fatiga="siempre", fatiga_duracion="menos_2_semanas")["fatiga_general"] == 3
    assert _build(fatiga="siempre", horas_sueno="menos_5h", fatiga_mejora_descanso="si")["fatiga_general"] == 3
    # Si duerme bien, "mejora al descansar" no explica la fatiga: se mantiene.
    assert _build(fatiga="siempre", fatiga_mejora_descanso="si")["fatiga_general"] == 5


def test_male_cannot_declare_menstruation_or_recent_birth() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _build(sexo="masculino", menstruacion_abundante="si")
    assert _build(anios_dieta_vegetal="mas_3")["b12_absorption_risk"] == -1  # omnivoro: se ignora


def test_goals_only_reorder_conditions_and_recommendations() -> None:
    from app.domains.recommendations.servicio_recomendaciones import (
        _order_conditions_by_goals,
        _order_recommendations_by_goals,
    )

    conditions = ["DEFICIT_ZINC", "SAFETY_RENAL", "DEFICIT_VIT_D", "ESTRES_SUENO"]
    assert _order_conditions_by_goals(conditions, ["salud_osea"]) == ["SAFETY_RENAL", "DEFICIT_VIT_D", "DEFICIT_ZINC", "ESTRES_SUENO"]
    assert _order_conditions_by_goals(conditions, []) == conditions

    recs = [
        {"component_id": "a", "priority": "principal", "condition": "DEFICIT_ZINC"},
        {"component_id": "b", "priority": "principal", "condition": "ESTRES_SUENO"},
        {"component_id": "c", "priority": "complementaria", "condition": "ESTRES_SUENO"},
        {"component_id": "d", "priority": "complementaria", "condition": "DEFICIT_ZINC"},
    ]
    ordered = [item["component_id"] for item in _order_recommendations_by_goals(recs, ["suenio"])]
    # Sube lo que coincide con el objetivo dentro de su grupo; un complementario no pasa a un principal.
    assert ordered == ["b", "a", "c", "d"]
