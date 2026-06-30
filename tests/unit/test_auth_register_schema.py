import pytest
from pydantic import ValidationError

from app.domains.auth.esquemas import RegisterInput


@pytest.mark.parametrize(
    ("value", "unit", "expected_unit", "expected_kg"),
    [
        (70, "kg", "kg", 70.0),
        (70000, "g", "g", 70.0),
        (154, "lb", "lb", 69.8532),
        (2469.18, "oz", "oz", 69.9999),
        (11, "stone", "st", 69.8532),
        (70, "kilogramos", "kg", 70.0),
        (154, "libras", "lb", 69.8532),
    ],
)
def test_register_input_normalizes_weight_units(value, unit, expected_unit, expected_kg):
    data = RegisterInput(
        email="schema-test@suplematch.test",
        password="Initial123",
        first_name="Ana",
        last_name="Lopez",
        age=25,
        weight_value=value,
        weight_unit=unit,
        height_value=170,
        height_unit="cm",
    )

    assert data.weight_unit == expected_unit
    assert data.weight_kg == pytest.approx(expected_kg, abs=0.001)


def test_register_input_rejects_unknown_weight_unit():
    with pytest.raises(ValidationError):
        RegisterInput(
            email="schema-test@suplematch.test",
            password="Initial123",
            first_name="Ana",
            last_name="Lopez",
            age=25,
            weight_value=70,
            weight_unit="arroba",
            height_value=170,
            height_unit="cm",
        )


def test_register_input_normalizes_height_units():
    data = RegisterInput(
        email="schema-test@suplematch.test",
        password="Initial123",
        first_name="Ana",
        last_name="Lopez",
        age=25,
        weight_value=70,
        weight_unit="kg",
        height_value=1.7,
        height_unit="m",
    )

    assert data.height_unit == "m"
    assert data.height_cm == 170


def test_register_input_rejects_unknown_height_unit():
    with pytest.raises(ValidationError):
        RegisterInput(
            email="schema-test@suplematch.test",
            password="Initial123",
            first_name="Ana",
            last_name="Lopez",
            age=25,
            weight_value=70,
            weight_unit="kg",
            height_value=170,
            height_unit="varas",
        )
