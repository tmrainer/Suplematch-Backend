import pytest
from pydantic import ValidationError

from app.ml.feature_builder import FeatureBuilder
from app.domains.survey.esquemas_encuesta import EncuestaInput


def _payload(**overrides):
    data = {
        "edad_rango": "31_50",
        "horas_sueno": "5_7h",
        "frecuencia_ejercicio": "1_2_semana",
        "dieta": "regular",
        "fatiga": "a_menudo",
        "exposicion_solar": "menos_15min",
        "frecuencia_enfermedad": "1_2_anio",
        "estres": "moderado",
        "alcohol": "ocasional",
    }
    data.update(overrides)
    return data


def test_current_supplements_are_required_when_user_takes_them():
    with pytest.raises(ValidationError):
        EncuestaInput(**_payload(toma_suplementos="si", suplementos_actuales=[]))


def test_current_supplements_are_rejected_when_user_says_no():
    with pytest.raises(ValidationError):
        EncuestaInput(**_payload(toma_suplementos="no", suplementos_actuales=["vitamina_d"]))


def test_exclusive_answers_cannot_be_combined():
    with pytest.raises(ValidationError):
        EncuestaInput(**_payload(restricciones=["sin_restricciones", "sin_gluten"]))

    with pytest.raises(ValidationError):
        EncuestaInput(**_payload(condiciones_seguridad=["ninguna", "medicacion_cronica"]))


def test_extended_survey_fields_feed_existing_model_features():
    encuesta = EncuestaInput(
        **_payload(
            sexo="masculino",
            tipo_dieta="vegano",
            dolor_muscular="frecuente",
            niebla_mental="severo",
            caida_cabello="moderado",
            objetivos=["energia", "cabello_piel_unas", "rendimiento"],
            toma_suplementos="si",
            suplementos_actuales=["vitamina_d"],
            restricciones=["sin_gluten"],
            condiciones_seguridad=["medicacion_cronica"],
            presupuesto="bajo",
        )
    )

    features = FeatureBuilder().build_pipeline_payload(encuesta)

    assert features["sexo"] == "M"
    assert features["tipo_dieta"] == "vegano"
    assert features["dolor_muscular"] == 4
    assert features["niebla_mental"] == 5
    assert features["caida_cabello"] == 3
    assert features["meta_energia"] == 1
    assert features["meta_belleza"] == 1
    assert features["meta_rendimiento"] == 1


def test_optimized_survey_fields_feed_diet_and_wellness_features():
    encuesta = EncuestaInput(
        **_payload(
            objetivo_principal="suenio_estres",
            tipo_dieta="vegetariano",
            fish_servings_week=0,
            dairy_servings_day=0.5,
            legume_servings_week=1,
            meat_servings_week=0,
            fruit_veg_servings_day=1,
            protein_g_day_estimate=50,
            weight_value=70,
            weight_unit="kg",
            sleep_quality="mala",
            night_wakeups="3_o_mas",
            caffeine_after_3pm="si",
            exercise_days_week=4,
            training_type="mixto",
            recovery_difficulty="alta",
        )
    )

    features = FeatureBuilder().build_pipeline_payload(encuesta)

    assert "suenio" in encuesta.objetivos
    assert "estres" in encuesta.objetivos
    assert features["tipo_dieta"] == "vegetariano"
    assert features["nivel_actividad"] == "activo"
    assert features["problemas_sueno"] == 5
    assert features["dolor_muscular"] == 5
    assert features["meta_cognitivo"] == 1
    assert features["benchmark_diet_b12_status"] == "low"
    assert features["benchmark_diet_omega3_status"] == "critical_low"
    assert features["benchmark_diet_vitamin_c_status"] == "critical_low"
    assert features["benchmark_diet_protein_status"] == "low"


def test_weekly_food_fields_are_normalized_and_estimate_protein():
    encuesta = EncuestaInput(
        **_payload(
            dairy_servings_week=1,
            red_meat_servings_week=1,
            poultry_servings_week=3,
            eggs_servings_week=4,
            fish_servings_week=1,
            legume_servings_week=2,
            no_meat=False,
            protein_g_day_estimate=None,
            iron_anemia_history="si",
            caffeine_sources=["cafe", "preworkout"],
            caffeine_servings_day=3,
            headache_days_week=3,
            fatigue_days_week=5,
            alcohol_drinks_week=5,
        )
    )

    features = FeatureBuilder().build_pipeline_payload(encuesta)

    assert encuesta.dairy_servings_day == pytest.approx(1 / 7, abs=0.0001)
    assert encuesta.meat_servings_week == 4
    assert features["red_meat_servings_week"] == 1
    assert features["poultry_servings_week"] == 3
    assert features["eggs_servings_week"] == 4
    assert features["protein_g_day_estimate"] > 0
    assert features["fatiga_general"] == 5
    assert features["meta_hidratacion"] == 1
    assert features["caffeine_servings_day"] == 3


def test_no_meat_clears_meat_servings():
    encuesta = EncuestaInput(
        **_payload(
            no_meat=True,
            red_meat_servings_week=2,
            poultry_servings_week=2,
        )
    )

    assert encuesta.red_meat_servings_week == 0
    assert encuesta.poultry_servings_week == 0
    assert encuesta.meat_servings_week == 0


def test_training_type_is_rejected_when_user_does_not_exercise():
    with pytest.raises(ValidationError):
        EncuestaInput(
            **_payload(
                exercise_days_week=0,
                training_type="fuerza",
            )
        )


def test_thyroid_condition_is_accepted_as_safety_condition():
    encuesta = EncuestaInput(
        **_payload(
            condiciones_seguridad=["problema_tiroideo"],
        )
    )

    assert encuesta.condiciones_seguridad == ["problema_tiroideo"]


def test_exact_anthropometrics_are_normalized_and_feed_model_features():
    encuesta = EncuestaInput(
        **_payload(
            age_years=17,
            weight_value=154,
            weight_unit="lb",
            height_value=1.7,
            height_unit="m",
        )
    )

    features = FeatureBuilder().build_pipeline_payload(encuesta)

    assert encuesta.edad_rango == "menos_18"
    assert encuesta.weight_unit == "lb"
    assert encuesta.weight_kg == pytest.approx(69.8532, abs=0.0001)
    assert encuesta.peso_rango == "66_80"
    assert encuesta.height_unit == "m"
    assert encuesta.height_cm == pytest.approx(170.0, abs=0.01)
    assert encuesta.talla_rango == "166_175"
    assert encuesta.bmi == pytest.approx(24.17, abs=0.01)
    assert features["edad"] == 17
    assert features["peso_kg"] == pytest.approx(69.8532, abs=0.0001)
    assert features["altura_cm"] == pytest.approx(170.0, abs=0.01)


def test_exact_anthropometrics_reject_unreasonable_values():
    with pytest.raises(ValidationError):
        EncuestaInput(**_payload(weight_value=1, weight_unit="kg"))

    with pytest.raises(ValidationError):
        EncuestaInput(**_payload(height_value=3.0, height_unit="m"))
