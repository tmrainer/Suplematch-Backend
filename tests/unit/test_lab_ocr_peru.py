"""
Tests del parser OCR para formatos de laboratorios peruanos.

Cubre: Roe, Suiza Lab, Reference Lab y formatos hospitalarios.
Formatos típicos:
  - Tabla 3 columnas: Examen | Resultado | Valores de Referencia
  - Tabla 4 columnas: Examen | Resultado | Unidad | VN
  - Texto con < N  y > N como rangos de referencia
  - Abreviaciones con puntos (T.G.O., T.G.P.)
  - Decimales con coma (12,5)
"""

import pytest

from app.services.lab_analysis_service import (
    _extract_reference_range,
    _normalize_ocr_text,
    parse_lab_text,
)


# ---------------------------------------------------------------------------
# Formato Roe / tabla 4 columnas
# ---------------------------------------------------------------------------

ROE_STYLE = """
EXAMEN                          RESULTADO    UNIDAD    VALORES DE REFERENCIA
Glucosa en Ayunas               95           mg/dL     70 - 100
Hemoglobina                     11.8         g/dL      12.0 - 16.0
Hematocrito                     34           %         36 - 47
Ferritina Serica                14           ng/mL     13 - 150
Vitamina D 25-OH                18.3         ng/mL     30 - 100
Vitamina B12                    210          pg/mL     200 - 900
Creatinina Serica               0.89         mg/dL     0.57 - 1.11
TSH                             0.32         mUI/L     0.4 - 4.0
"""


def test_roe_style_parses_main_biomarkers():
    results = parse_lab_text(ROE_STYLE)
    codes = {r["code"] for r in results}
    assert "glucose" in codes
    assert "hemoglobin" in codes
    assert "hematocrit" in codes
    assert "ferritin" in codes
    assert "vitamin_d" in codes
    assert "b12" in codes
    assert "creatinine" in codes
    assert "tsh" in codes


def test_roe_style_glucose_value_and_range():
    results = parse_lab_text(ROE_STYLE)
    glucose = next(r for r in results if r["code"] == "glucose")
    assert glucose["value"] == 95.0
    assert glucose["reference_low"] == 70.0
    assert glucose["reference_high"] == 100.0
    assert glucose["status"] == "normal"


def test_roe_style_vitamin_d_low():
    results = parse_lab_text(ROE_STYLE)
    vd = next(r for r in results if r["code"] == "vitamin_d")
    assert vd["value"] == pytest.approx(18.3)
    assert vd["reference_low"] == 30.0
    assert vd["status"] == "low"


def test_roe_style_tsh_low():
    results = parse_lab_text(ROE_STYLE)
    tsh = next(r for r in results if r["code"] == "tsh")
    assert tsh["value"] == 0.32
    assert tsh["status"] == "low"


# ---------------------------------------------------------------------------
# Formato Suiza Lab / tabla con VN
# ---------------------------------------------------------------------------

SUIZA_LAB_STYLE = """
ANALISIS                  RESULTADO   U.M.    VN
GLUCOSA                   89.5        mg/dL   74 - 106
HEMOGLOBINA               14.2        g/dL    12 - 16
TRIGLICERIDOS             185         mg/dL   < 150
COLESTEROL TOTAL          215         mg/dL   < 200
COLESTEROL HDL            38          mg/dL   > 40
COLESTEROL LDL            140         mg/dL   < 130
ACIDO URICO               8.2         mg/dL   3.5 - 7.0
PROTEINA C REACTIVA       6.5         mg/L    < 3.0
"""


def test_suiza_lab_parses_lipid_panel():
    results = parse_lab_text(SUIZA_LAB_STYLE)
    codes = {r["code"] for r in results}
    assert "triglycerides" in codes
    assert "total_cholesterol" in codes
    assert "hdl" in codes
    assert "ldl" in codes


def test_suiza_lab_upper_bound_range():
    results = parse_lab_text(SUIZA_LAB_STYLE)
    chol = next(r for r in results if r["code"] == "total_cholesterol")
    assert chol["value"] == 215.0
    assert chol["status"] == "high"
    assert chol["reference_high"] == 200.0


def test_suiza_lab_lower_bound_range_hdl():
    results = parse_lab_text(SUIZA_LAB_STYLE)
    hdl = next(r for r in results if r["code"] == "hdl")
    assert hdl["value"] == 38.0
    assert hdl["status"] == "low"
    assert hdl["reference_low"] == 40.0


def test_suiza_lab_uric_acid():
    results = parse_lab_text(SUIZA_LAB_STYLE)
    ua = next(r for r in results if r["code"] == "uric_acid")
    assert ua["value"] == 8.2
    assert ua["status"] == "high"


def test_suiza_lab_crp_critical():
    results = parse_lab_text(SUIZA_LAB_STYLE)
    crp = next(r for r in results if r["code"] == "crp")
    assert crp["value"] == 6.5
    assert crp["status"] == "high"


# ---------------------------------------------------------------------------
# Abreviaciones con puntos (T.G.O., T.G.P.) — formato antiguo hospitalario
# ---------------------------------------------------------------------------

HOSPITAL_STYLE = """
T.G.O.          38     U/L     Hasta 40
T.G.P.          52     U/L     Hasta 40
Vit. D          12.5   ng/mL   30 - 100
Ferritina Sr.   18     ng/mL   13 - 150
Hierro Serico   45     ug/dL   60 - 170
Folato Serico   2.1    ng/mL   3.0 - 20.0
"""


def test_hospital_dotted_tgo_tgp():
    results = parse_lab_text(HOSPITAL_STYLE)
    codes = {r["code"] for r in results}
    assert "ast" in codes, "T.G.O. debe mapearse a ast"
    assert "alt" in codes, "T.G.P. debe mapearse a alt"


def test_hospital_alt_elevated():
    results = parse_lab_text(HOSPITAL_STYLE)
    alt = next(r for r in results if r["code"] == "alt")
    assert alt["value"] == 52.0
    assert alt["status"] == "high"


def test_hospital_vit_d_with_dot():
    results = parse_lab_text(HOSPITAL_STYLE)
    vd = next(r for r in results if r["code"] == "vitamin_d")
    assert vd["value"] == 12.5
    assert vd["status"] == "low"


def test_hospital_iron_low():
    results = parse_lab_text(HOSPITAL_STYLE)
    iron = next(r for r in results if r["code"] == "iron")
    assert iron["value"] == 45.0
    assert iron["status"] == "low"


def test_hospital_folate_low():
    results = parse_lab_text(HOSPITAL_STYLE)
    folate = next(r for r in results if r["code"] == "folate")
    assert folate["value"] == 2.1
    assert folate["status"] == "low"


# ---------------------------------------------------------------------------
# Decimales con coma (algunos labs peruanos usan coma europea)
# ---------------------------------------------------------------------------

COMMA_DECIMAL_STYLE = """
Vitamina D 25-OH    18,5    ng/mL    30 - 100
Ferritina           22,3    ng/mL    30 - 300
Glucosa             98,0    mg/dL    70 - 100
"""


def test_comma_decimal_vitamin_d():
    results = parse_lab_text(COMMA_DECIMAL_STYLE)
    vd = next(r for r in results if r["code"] == "vitamin_d")
    assert vd["value"] == pytest.approx(18.5)
    assert vd["status"] == "low"


def test_comma_decimal_ferritin():
    results = parse_lab_text(COMMA_DECIMAL_STYLE)
    ferritin = next(r for r in results if r["code"] == "ferritin")
    assert ferritin["value"] == pytest.approx(22.3)
    assert ferritin["status"] == "low"


# ---------------------------------------------------------------------------
# Formato Reference Lab — 25(OH)D3 como nombre de Vitamina D
# ---------------------------------------------------------------------------

REF_LAB_STYLE = """
Determinacion                      Resultado    Unidad    VN (Valores Normales)
Vitamina D (25-OH-D3)              22.0         ng/mL     30.0 - 100.0
Vitamina B12                       185          pg/mL     200 - 900
TSH Ultrasensible                  5.8          mUI/L     0.4 - 4.0
Colesterol Total                   198          mg/dL     < 200
"""


def test_ref_lab_25ohd3_alias():
    results = parse_lab_text(REF_LAB_STYLE)
    vd = next((r for r in results if r["code"] == "vitamin_d"), None)
    assert vd is not None, "25-OH-D3 debe mapearse a vitamin_d"
    assert vd["value"] == 22.0
    assert vd["status"] == "low"


def test_ref_lab_tsh_high():
    results = parse_lab_text(REF_LAB_STYLE)
    tsh = next(r for r in results if r["code"] == "tsh")
    assert tsh["value"] == 5.8
    assert tsh["status"] == "high"


def test_ref_lab_cholesterol_upper_bound():
    results = parse_lab_text(REF_LAB_STYLE)
    chol = next(r for r in results if r["code"] == "total_cholesterol")
    assert chol["value"] == 198.0
    assert chol["reference_high"] == 200.0
    assert chol["status"] == "normal"


# ---------------------------------------------------------------------------
# _normalize_ocr_text — verificar normalización de artefactos
# ---------------------------------------------------------------------------

def test_normalize_dotted_abbreviations():
    text = _normalize_ocr_text("T.G.O.: 38 U/L\nT.G.P.: 52 U/L")
    assert "TGO" in text
    assert "TGP" in text
    assert "T.G.O." not in text


def test_normalize_units_with_spaces():
    text = _normalize_ocr_text("Glucosa: 95 mg / dL\nFerritina: 18 ng / ml")
    assert "mg/dL" in text
    assert "ng/mL" in text


def test_normalize_mui_l_variants():
    text = _normalize_ocr_text("TSH: 1.5 mUI/mL\nTSH2: 1.5 mIU/L")
    assert text.count("mUI/L") == 2


# ---------------------------------------------------------------------------
# _extract_reference_range — verificar < N y > N
# ---------------------------------------------------------------------------

def test_extract_upper_bound_lt():
    low, high = _extract_reference_range("95 mg/dL < 100", 0)
    assert high == 100.0
    assert low is None


def test_extract_lower_bound_gt():
    low, high = _extract_reference_range("38 mg/dL > 40", 0)
    assert low == 40.0
    assert high is None


def test_extract_full_range_preferred_over_bounds():
    low, high = _extract_reference_range("95 mg/dL 70 - 100", 0)
    assert low == 70.0
    assert high == 100.0
