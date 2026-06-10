from __future__ import annotations

from typing import Any


SURVEY_CONTRACT_VERSION = "2026-06-08.2"

SURVEY_ENUMS: dict[str, list[str]] = {
    "edad_rango": ["menos_18", "18_30", "31_50", "mas_50"],
    "sexo": ["femenino", "masculino", "prefiero_no_decir"],
    "peso_rango": ["menos_50", "50_65", "66_80", "mas_80"],
    "talla_rango": ["menos_155", "155_165", "166_175", "mas_175"],
    "tipo_dieta": ["omnivoro", "pescetariano", "vegetariano", "vegano"],
    "dieta": ["poco_variada", "regular", "bastante_variada", "muy_balanceada"],
    "exposicion_solar": ["menos_15min", "15_30min", "30_60min", "mas_1h"],
    "frecuencia_ejercicio": ["casi_nunca", "1_2_semana", "3_4_semana", "diario"],
    "fatiga": ["casi_nunca", "a_veces", "a_menudo", "siempre"],
    "horas_sueno": ["menos_5h", "5_7h", "7_9h", "mas_9h"],
    "frecuencia_enfermedad": ["casi_nunca", "1_2_anio", "3_4_anio", "muy_seguido"],
    "estres": ["bajo", "moderado", "alto", "muy_alto"],
    "sintomas": [
        "ninguno",
        "dolor_muscular",
        "dolor_articular",
        "niebla_mental",
        "caida_cabello",
        "piel_seca",
        "unas_quebradizas",
        "calambres",
    ],
    "objetivos": ["energia", "inmunidad", "suenio", "rendimiento", "salud_osea", "cabello_piel_unas", "estres"],
    "alcohol": ["nunca", "raro", "ocasional", "frecuente"],
    "toma_suplementos": ["no", "si"],
    "suplementos_actuales": [
        "vitamina_d",
        "calcio",
        "magnesio",
        "zinc",
        "vitamina_c",
        "hierro",
        "omega_3",
        "multivitaminico",
        "proteina",
        "otro",
    ],
    "restricciones": [
        "sin_restricciones",
        "alergia_lacteos",
        "alergia_soya",
        "alergia_pescado_mariscos",
        "evita_gelatina",
        "sin_gluten",
    ],
    "condiciones_seguridad": [
        "ninguna",
        "embarazo_lactancia",
        "enfermedad_renal",
        "enfermedad_hepatica",
        "anticoagulantes",
        "medicacion_cronica",
    ],
}

SURVEY_RULES: dict[str, Any] = {
    "max_objetivos": 4,
    "toma_suplementos_si_requires_suplementos_actuales": True,
    "toma_suplementos_no_requires_empty_suplementos_actuales": True,
    "exclusive_values": {
        "restricciones": "sin_restricciones",
        "condiciones_seguridad": "ninguna",
    },
    "incompatible_values": [
        {
            "field": "condiciones_seguridad",
            "value": "embarazo_lactancia",
            "when": {"sexo": "masculino"},
        }
    ],
    "hard_safety_values": {
        "edad_rango": ["menos_18"],
        "condiciones_seguridad": [
            "embarazo_lactancia",
            "enfermedad_renal",
            "enfermedad_hepatica",
            "anticoagulantes",
            "medicacion_cronica",
        ],
    },
}


def survey_contract() -> dict[str, Any]:
    return {
        "version": SURVEY_CONTRACT_VERSION,
        "enums": SURVEY_ENUMS,
        "rules": SURVEY_RULES,
    }
