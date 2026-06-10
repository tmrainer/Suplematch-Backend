from app.services.product_safety import (
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
