from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class BiomarkerDefinition:
    code: str
    display_name: str
    aliases: tuple[str, ...]
    unit: str
    low: float | None = None
    high: float | None = None
    critical_low: float | None = None
    critical_high: float | None = None
    supplement_component_id: str | None = None
    supplement_name: str | None = None
    medical_condition: str | None = None
    safety_condition: str | None = None


BIOMARKERS: dict[str, BiomarkerDefinition] = {
    "vitamin_d": BiomarkerDefinition(
        "vitamin_d",
        "Vitamina D 25-OH",
        (
            # Full names (longest → tried first; avoids capturing "25" as the value)
            "vitamina d 25-oh-d3", "vitamina d (25-oh-d3)", "vitamina d 25-oh",
            "vitamina d 25 oh", "vit d 25-oh", "vit d 25 oh",
            "25 oh vitamina d", "25-hidroxivitamina d", "25 hidroxivitamina d",
            "vitamin d 25 hydroxy", "vitamina d 25 hidroxi",
            # Medium specificity
            "vitamina d3", "vitamina d", "vitamin d",
            "calcidiol", "colecalciferol",
            # Short aliases with word-boundary (≤5 chars, regex-protected)
            "vit d", "25-oh", "25 oh",
        ),
        "ng/mL",
        low=30,
        high=100,
        critical_low=10,
        critical_high=150,
        supplement_component_id="COMP_94DFE28A9A5C",
        supplement_name="Vitamina D",
    ),
    "b12": BiomarkerDefinition(
        "b12",
        "Vitamina B12",
        (
            "vitamina b12", "vit b12", "vit. b12", "vitamina b 12",
            "b 12", "b12", "b-12", "cobalamina", "cobalamin",
            "cianocobalamina", "cbl",
        ),
        "pg/mL",
        low=200,
        high=900,
        critical_low=150,
        supplement_name="Vitamina B12",
    ),
    "ferritin": BiomarkerDefinition(
        "ferritin",
        "Ferritina",
        (
            "ferritina", "ferritin", "ferritina serica", "ferritina sérica",
            "ferritina sr", "ferrt", "ferritina s",
        ),
        "ng/mL",
        low=30,
        high=300,
        critical_low=12,
        supplement_name="Hierro",
    ),
    "hemoglobin": BiomarkerDefinition(
        "hemoglobin",
        "Hemoglobina",
        ("hemoglobina", "hemoglobin", "hb", "hgb", "haemoglobin"),
        "g/dL",
        low=12,
        high=17.5,
        critical_low=8,
        critical_high=20,
        medical_condition="possible_anemia_pattern",
    ),
    "hematocrit": BiomarkerDefinition(
        "hematocrit",
        "Hematocrito",
        ("hematocrito", "hematocrit", "hto", "hcto", "hct"),
        "%",
        low=36,
        high=52,
        critical_low=25,
        critical_high=60,
        medical_condition="possible_anemia_pattern",
    ),
    "iron": BiomarkerDefinition(
        "iron",
        "Hierro Sérico",
        (
            "hierro serico", "hierro sérico", "hierro s", "fierro serico",
            "fe serico", "fe sérico", "hierro en sangre", "sideremia",
        ),
        "ug/dL",
        low=60,
        high=170,
        critical_low=30,
        supplement_name="Hierro",
    ),
    "folate": BiomarkerDefinition(
        "folate",
        "Ácido Fólico / Folato",
        (
            "folato", "acido folico", "ácido fólico", "folate",
            "vitamina b9", "vit b9", "folic acid", "folato serico",
            "folato sérico",
        ),
        "ng/mL",
        low=3.0,
        high=20.0,
        critical_low=2.0,
        supplement_name="Ácido Fólico",
    ),
    "calcium": BiomarkerDefinition(
        "calcium",
        "Calcio sérico",
        ("calcio", "calcio serico", "calcio sérico", "calcium", "ca serico"),
        "mg/dL",
        low=8.6,
        high=10.2,
        critical_low=7.5,
        critical_high=12,
        supplement_name="Calcio",
    ),
    "magnesium": BiomarkerDefinition(
        "magnesium",
        "Magnesio",
        ("magnesio", "magnesio serico", "magnesio sérico", "magnesium", "mg serico"),
        "mg/dL",
        low=1.7,
        high=2.4,
        critical_low=1.2,
        critical_high=3.0,
        supplement_name="Magnesio",
    ),
    "potassium": BiomarkerDefinition(
        "potassium",
        "Potasio",
        (
            "potasio", "potasio serico", "potasio sérico", "potassium",
            "k serico", "k sérico", "k+", "kalium",
        ),
        "mmol/L",
        low=3.5,
        high=5.1,
        critical_low=2.8,
        critical_high=6.0,
        safety_condition="enfermedad_renal",
    ),
    "zinc": BiomarkerDefinition(
        "zinc",
        "Zinc",
        ("zinc", "zinc serico", "zinc sérico"),
        "ug/dL",
        low=70,
        high=120,
        critical_low=50,
        critical_high=180,
        supplement_name="Zinc",
    ),
    "creatinine": BiomarkerDefinition(
        "creatinine",
        "Creatinina",
        (
            "creatinina", "creatinine", "creatinina serica", "creatinina sérica",
            "creatinina sr", "creat",
        ),
        "mg/dL",
        high=1.3,
        critical_high=2.0,
        safety_condition="enfermedad_renal",
    ),
    "egfr": BiomarkerDefinition(
        "egfr",
        "TFG/eGFR",
        (
            "egfr", "tfg", "filtrado glomerular", "tfg-e",
            "tasa de filtrado glomerular", "tasa filtrado glomerular",
            "clearance creatinina", "depuracion creatinina",
        ),
        "mL/min/1.73m2",
        low=90,
        critical_low=60,
        safety_condition="enfermedad_renal",
    ),
    "alt": BiomarkerDefinition(
        "alt",
        "ALT/TGP",
        (
            "alt", "tgp", "alanina aminotransferasa", "alanino aminotransferasa",
            "alat", "alt/tgp", "tgp/alt",
            "transaminasa glutamico piruvica", "transaminasa gp",
        ),
        "U/L",
        high=40,
        critical_high=200,
        safety_condition="enfermedad_hepatica",
    ),
    "ast": BiomarkerDefinition(
        "ast",
        "AST/TGO",
        (
            "ast", "tgo", "aspartato aminotransferasa",
            "asat", "ast/tgo", "tgo/ast",
            "transaminasa glutamico oxalacetica", "transaminasa go",
        ),
        "U/L",
        high=40,
        critical_high=200,
        safety_condition="enfermedad_hepatica",
    ),
    "glucose": BiomarkerDefinition(
        "glucose",
        "Glucosa",
        (
            "glucosa", "glucose", "glicemia", "glucemia",
            "glucosa basal", "glucosa en ayunas", "glucosa en sangre",
            "glucosa capilar", "azucar en sangre",
        ),
        "mg/dL",
        low=70,
        high=100,
        critical_low=50,
        critical_high=250,
    ),
    "hba1c": BiomarkerDefinition(
        "hba1c",
        "Hemoglobina glicosilada HbA1c",
        (
            "hba1c", "hb a1c", "hemoglobina glicosilada", "hemoglobina glucosilada",
            "glicosilada hemoglobina", "glikozile hemoglobin", "%hba1c",
        ),
        "%",
        low=4.0,
        high=5.7,
        critical_high=6.5,
        medical_condition="glycemic_risk_pattern",
    ),
    "tsh": BiomarkerDefinition(
        "tsh",
        "TSH Tirotropina",
        (
            "tsh", "tirotropina", "hormona tirotropa",
            "hormona estimulante del tiroides", "tirotropina ultrasensible",
            "tsh ultrasensible", "tsh us",
        ),
        "mUI/L",
        low=0.4,
        high=4.0,
        critical_low=0.1,
        critical_high=10.0,
        safety_condition="disfuncion_tiroidea",
    ),
    "t4": BiomarkerDefinition(
        "t4",
        "T4 total Tiroxina",
        (
            "t4 total", "tiroxina total", "t4", "tiroxina", "thyroxine",
        ),
        "ug/dL",
        low=5.1,
        high=14.1,
        critical_low=2.0,
        critical_high=25.0,
        safety_condition="disfuncion_tiroidea",
    ),
    "free_t4": BiomarkerDefinition(
        "free_t4",
        "T4 libre",
        (
            "t4 libre", "free t4", "serbest t4", "ft4", "t4l",
            "tiroxina libre",
        ),
        "ng/dL",
        low=0.87,
        high=1.70,
        critical_low=0.4,
        critical_high=4.0,
        safety_condition="disfuncion_tiroidea",
    ),
    "t3": BiomarkerDefinition(
        "t3",
        "T3 total Triyodotironina",
        (
            "t3 total", "triyodotironina total", "t3", "triyodotironina",
            "triiodotironina", "triiodothyronine",
        ),
        "ng/mL",
        low=0.8,
        high=2.0,
        critical_low=0.3,
        critical_high=5.0,
        safety_condition="disfuncion_tiroidea",
    ),
    "total_cholesterol": BiomarkerDefinition(
        "total_cholesterol",
        "Colesterol Total",
        (
            # Always use full name to avoid matching "Colesterol HDL" / "Colesterol LDL"
            "colesterol total", "cholesterol total", "col total",
            "colesterol t",
        ),
        "mg/dL",
        high=200,
        critical_high=240,
    ),
    "ldl": BiomarkerDefinition(
        "ldl",
        "Colesterol LDL",
        (
            "ldl", "colesterol ldl", "ldl colesterol", "ldl-c", "c-ldl",
            "colesterol de baja densidad", "col ldl",
        ),
        "mg/dL",
        high=130,
        critical_high=190,
    ),
    "hdl": BiomarkerDefinition(
        "hdl",
        "Colesterol HDL",
        (
            "hdl", "colesterol hdl", "hdl colesterol", "hdl-c", "c-hdl",
            "colesterol de alta densidad", "col hdl",
        ),
        "mg/dL",
        low=40,
        critical_low=35,
    ),
    "triglycerides": BiomarkerDefinition(
        "triglycerides",
        "Triglicéridos",
        (
            "trigliceridos", "triglicéridos", "triglycerides",
            "trigliceridos sericos", "triglicéridos séricos",
        ),
        "mg/dL",
        high=150,
        critical_high=500,
    ),
    "uric_acid": BiomarkerDefinition(
        "uric_acid",
        "Ácido Úrico",
        (
            "acido urico", "ácido úrico", "uric acid",
            "acido urico serico", "ácido úrico sérico",
        ),
        "mg/dL",
        high=7.0,
        critical_high=9.0,
    ),
    "crp": BiomarkerDefinition(
        "crp",
        "Proteína C Reactiva",
        (
            "proteina c reactiva", "proteína c reactiva",
            "pcr", "crp", "pcr ultrasensible", "pcr us",
            "proteina c reactiva ultrasensible", "hs-crp",
        ),
        "mg/L",
        high=3.0,
        critical_high=10.0,
    ),
}
