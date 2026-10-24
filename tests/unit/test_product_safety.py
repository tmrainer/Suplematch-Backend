from app.domains.catalog.seguridad_productos import (
    evaluate_ingredient_safety,
    infer_restriction_flags,
    product_restriction_flags,
    verified_restriction_flags,
)


def test_infer_restriction_flags_detects_common_allergens():
    flags = infer_restriction_flags(
        {
            "commercial_name": "Omega 3 aceite de pescado softgel",
            "ingredient": "EPA DHA",
        }
    )

    assert "contains_fish_or_shellfish" in flags
    assert "may_contain_gelatin" in flags


def test_infer_restriction_flags_detects_gluten_free_claim():
    flags = infer_restriction_flags({"commercial_name": "Magnesio sin gluten"})

    assert "gluten_free_claim" in flags


def test_verified_restriction_flags_take_priority():
    payload = {
        "commercial_name": "Omega 3 aceite de pescado",
        "gluten_free_verified": "true",
    }

    assert verified_restriction_flags(payload) == ["gluten_free_claim"]
    assert product_restriction_flags(payload) == ["gluten_free_claim"]


def test_ingredient_safety_blocks_declared_allergy():
    result = evaluate_ingredient_safety(
        {"commercial_name": "Omega 3 aceite de pescado", "ingredient": "EPA DHA"},
        restrictions=["alergia_pescado_mariscos"],
    )

    assert result["blocked"] is True
    assert result["rules"][0]["name"] == "fish_shellfish_allergy_block"


def test_ingredient_safety_does_not_block_algae_omega_for_fish_allergy():
    result = evaluate_ingredient_safety(
        {"commercial_name": "Omega 3 de algas", "ingredient": "DHA de algas"},
        restrictions=["alergia_pescado_mariscos"],
    )

    assert result["blocked"] is False


def test_product_text_includes_full_digemid_composition():
    from app.domains.catalog.seguridad_productos import product_text

    text = product_text(
        {
            "commercial_name": "Multivitaminico",
            "ingredient": "ZINC",
            "product_ingredients": ["ZINC", "VITAMINA A"],
            "digemid_composicion": "VITAMINA A 10,000.000000 UI ZINC 15.000000 mg",
        }
    )

    assert "vitamina a 10,000.000000 ui" in text
    assert "zinc" in text


def test_pregnancy_blocks_multivitamin_chosen_for_zinc_when_vitamin_a_dose_is_high():
    # El producto fue elegido por su fila de ZINC; la vitamina A solo está en la composición DIGEMID.
    result = evaluate_ingredient_safety(
        {
            "commercial_name": "Multivitaminico Completo",
            "ingredient": "ZINC",
            "digemid_composicion": "VITAMINA A 25,000.000000 UI ZINC 15.000000 mg ACIDO FOLICO 0.400000 mg",
        },
        safety_conditions=["embarazo_lactancia"],
    )

    assert result["blocked"] is True
    hit = next(rule for rule in result["rules"] if rule["name"] == "retinol_pregnancy_block")
    assert hit["action"] == "block"
    assert hit["declared_dose_mcg"] == 7500.0  # 25,000 UI x 0.3 mcg/UI


def test_pregnancy_only_warns_when_declared_vitamin_a_is_below_upper_limit():
    result = evaluate_ingredient_safety(
        {
            "commercial_name": "Prenatal",
            "ingredient": "ACIDO FOLICO",
            "digemid_composicion": "PALMITATO DE RETINOL 2,500.000000 UI ACIDO FOLICO 0.400000 mg",
        },
        safety_conditions=["embarazo_lactancia"],
    )

    assert result["blocked"] is False
    hit = next(rule for rule in result["rules"] if rule["name"] == "retinol_pregnancy_block")
    assert hit["action"] == "penalize"
    assert hit["declared_dose_mcg"] == 750.0
    assert result["penalty"] > 0
    assert any("límite superior" in warning for warning in result["warnings"])


def test_pregnancy_still_blocks_vitamin_a_without_declared_dose():
    result = evaluate_ingredient_safety(
        {"commercial_name": "Vitamina A Capsulas", "ingredient": "VITAMINA A"},
        safety_conditions=["embarazo_lactancia"],
    )

    assert result["blocked"] is True


def test_iodine_in_digemid_composition_blocks_for_thyroid_condition():
    result = evaluate_ingredient_safety(
        {
            "commercial_name": "Multivitaminico Mujer",
            "ingredient": "ZINC",
            "digemid_composicion": "YODURO DE POTASIO 0.196000 mg ZINC 15.000000 mg",
        },
        safety_conditions=["problema_tiroideo"],
    )

    assert result["blocked"] is True
    assert result["rules"][0]["name"] == "iodine_thyroid_block"

    plain_yodo = evaluate_ingredient_safety(
        {"commercial_name": "Multi", "ingredient": "ZINC", "digemid_composicion": "YODO 150.000000 MCG ZINC 15 mg"},
        safety_conditions=["problema_tiroideo"],
    )
    assert plain_yodo["blocked"] is True

    no_condition = evaluate_ingredient_safety(
        {"commercial_name": "Multi", "ingredient": "ZINC", "digemid_composicion": "YODURO DE POTASIO 0.196 mg"},
        safety_conditions=[],
    )
    assert no_condition["blocked"] is False
