"""Definiciones de biomarcadores de laboratorio.

Fuente unica de umbrales: `data/knowledge/biomarkers.csv` (NIH ODS, OMS, MedlinePlus; ver `source_ids`).
Este modulo solo aporta los alias de texto usados por el OCR y la logica de seleccion por sexo/edad/embarazo
y de conversion de unidades. Antes los umbrales estaban duplicados aqui y en el CSV con valores distintos.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parents[3] / "data" / "knowledge"
BIOMARKERS_CSV = KNOWLEDGE_DIR / "biomarkers.csv"


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
    borderline: float | None = None
    supplement_component_id: str | None = None
    supplement_name: str | None = None
    medical_condition: str | None = None
    safety_condition: str | None = None
    condition_code: str | None = None
    sex: str = "any"
    pregnant: str = "any"
    age_min: float | None = None
    age_max: float | None = None
    unit_conversions: dict[str, float] = field(default_factory=dict, compare=False, hash=False)
    source_ids: tuple[str, ...] = ()
    note: str = ""

    @property
    def reference_group(self) -> str:
        parts = []
        if self.sex != "any":
            parts.append(self.sex)
        if self.pregnant == "yes":
            parts.append("pregnant")
        if self.age_min is not None or self.age_max is not None:
            lo = int(self.age_min) if self.age_min is not None else 0
            parts.append(f"{lo}-{int(self.age_max)}" if self.age_max is not None else f"{lo}+")
        return "_".join(parts) or "default"

    def matches(self, *, sex: str | None, age: float | None, pregnant: bool | None) -> bool:
        if self.sex != "any" and sex != self.sex:
            return False
        if self.pregnant == "yes" and pregnant is not True:
            return False
        if self.pregnant == "no" and pregnant is True:
            return False
        if self.age_min is not None and (age is None or age < self.age_min):
            return False
        if self.age_max is not None and (age is None or age > self.age_max):
            return False
        return True

    @property
    def specificity(self) -> int:
        return int(self.sex != "any") + int(self.pregnant != "any") + int(self.age_min is not None or self.age_max is not None)


# Alias de texto (OCR / entrada manual). Los umbrales NO viven aqui.
BIOMARKER_ALIASES: dict[str, tuple[str, ...]] = {
    "vitamin_d": (
        "vitamina d 25-oh-d3", "vitamina d (25-oh-d3)", "vitamina d 25-oh",
        "vitamina d 25 oh", "vit d 25-oh", "vit d 25 oh",
        "25 oh vitamina d", "25-hidroxivitamina d", "25 hidroxivitamina d",
        "vitamin d 25 hydroxy", "vitamina d 25 hidroxi",
        "vitamina d3", "vitamina d", "vitamin d",
        "calcidiol", "colecalciferol",
        "vit d", "25-oh", "25 oh",
    ),
    "b12": (
        "vitamina b12", "vit b12", "vit. b12", "vitamina b 12",
        "b 12", "b12", "b-12", "cobalamina", "cobalamin",
        "cianocobalamina", "cbl",
    ),
    "ferritin": (
        "ferritina", "ferritin", "ferritina serica", "ferritina sérica",
        "ferritina sr", "ferrt", "ferritina s",
    ),
    "hemoglobin": ("hemoglobina", "hemoglobin", "hb", "hgb", "haemoglobin"),
    "hematocrit": ("hematocrito", "hematocrit", "hto", "hcto", "hct"),
    "iron": (
        "hierro serico", "hierro sérico", "hierro s", "fierro serico",
        "fe serico", "fe sérico", "hierro en sangre", "sideremia",
    ),
    "folate": (
        "folato", "acido folico", "ácido fólico", "folate",
        "vitamina b9", "vit b9", "folic acid", "folato serico",
        "folato sérico",
    ),
    "calcium": ("calcio", "calcio serico", "calcio sérico", "calcium", "ca serico"),
    "magnesium": ("magnesio", "magnesio serico", "magnesio sérico", "magnesium", "mg serico"),
    "potassium": (
        "potasio", "potasio serico", "potasio sérico", "potassium",
        "k serico", "k sérico", "k+", "kalium",
    ),
    "zinc": ("zinc", "zinc serico", "zinc sérico"),
    "creatinine": (
        "creatinina", "creatinine", "creatinina serica", "creatinina sérica",
        "creatinina sr", "creat",
    ),
    "egfr": (
        "egfr", "tfg", "filtrado glomerular", "tfg-e",
        "tasa de filtrado glomerular", "tasa filtrado glomerular",
        "clearance creatinina", "depuracion creatinina",
    ),
    "alt": (
        "alt", "tgp", "alanina aminotransferasa", "alanino aminotransferasa",
        "alat", "alt/tgp", "tgp/alt",
        "transaminasa glutamico piruvica", "transaminasa gp",
    ),
    "ast": (
        "ast", "tgo", "aspartato aminotransferasa",
        "asat", "ast/tgo", "tgo/ast",
        "transaminasa glutamico oxalacetica", "transaminasa go",
    ),
    "glucose": (
        "glucosa", "glucose", "glicemia", "glucemia",
        "glucosa basal", "glucosa en ayunas", "glucosa en sangre",
        "glucosa capilar", "azucar en sangre",
    ),
    "hba1c": (
        "hba1c", "hb a1c", "hemoglobina glicosilada", "hemoglobina glucosilada",
        "glicosilada hemoglobina", "glikozile hemoglobin", "%hba1c",
    ),
    "tsh": (
        "tsh", "tirotropina", "hormona tirotropa",
        "hormona estimulante del tiroides", "tirotropina ultrasensible",
        "tsh ultrasensible", "tsh us",
    ),
    "t4": ("t4 total", "tiroxina total", "t4", "tiroxina", "thyroxine"),
    "free_t4": ("t4 libre", "free t4", "serbest t4", "ft4", "t4l", "tiroxina libre"),
    "t3": (
        "t3 total", "triyodotironina total", "t3", "triyodotironina",
        "triiodotironina", "triiodothyronine",
    ),
    "total_cholesterol": ("colesterol total", "cholesterol total", "col total", "colesterol t"),
    "ldl": (
        "ldl", "colesterol ldl", "ldl colesterol", "ldl-c", "c-ldl",
        "colesterol de baja densidad", "col ldl",
    ),
    "hdl": (
        "hdl", "colesterol hdl", "hdl colesterol", "hdl-c", "c-hdl",
        "colesterol de alta densidad", "col hdl",
    ),
    "triglycerides": (
        "trigliceridos", "triglicéridos", "triglycerides",
        "trigliceridos sericos", "triglicéridos séricos",
    ),
    "uric_acid": (
        "acido urico", "ácido úrico", "uric acid",
        "acido urico serico", "ácido úrico sérico",
    ),
    "crp": (
        "proteina c reactiva", "proteína c reactiva",
        "pcr", "crp", "pcr ultrasensible", "pcr us",
        "proteina c reactiva ultrasensible", "hs-crp",
    ),
}

# Nombres de display con tilde para la UI (el CSV se mantiene sin tildes por simplicidad).
DISPLAY_OVERRIDES: dict[str, str] = {
    "iron": "Hierro Sérico",
    "folate": "Ácido Fólico / Folato",
    "calcium": "Calcio sérico",
    "uric_acid": "Ácido Úrico",
    "crp": "Proteína C Reactiva",
    "triglycerides": "Triglicéridos",
    "total_cholesterol": "Colesterol Total",
    "t4": "T4 total Tiroxina",
    "hba1c": "Hemoglobina glicosilada HbA1c",
    "tsh": "TSH Tirotropina",
}


def normalize_unit_key(unit: str | None) -> str:
    """Clave comparable de una unidad: minusculas, mu -> u, sin espacios."""
    if not unit:
        return ""
    text = str(unit).strip().replace("µ", "u").replace("μ", "u").replace(" ", "")
    return text.lower()


def _float(value: str | None) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    return float(text)


def _parse_conversions(value: str | None) -> dict[str, float]:
    out: dict[str, float] = {}
    for item in (value or "").split("|"):
        if ":" not in item:
            continue
        unit, factor = item.split(":", 1)
        out[normalize_unit_key(unit)] = float(factor)
    return out


def _load_definitions(path: Path = BIOMARKERS_CSV) -> tuple[dict[str, BiomarkerDefinition], dict[str, list[BiomarkerDefinition]]]:
    defaults: dict[str, BiomarkerDefinition] = {}
    variants: dict[str, list[BiomarkerDefinition]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            code = row["biomarker_code"].strip()
            definition = BiomarkerDefinition(
                code=code,
                display_name=DISPLAY_OVERRIDES.get(code, row["display_name"].strip()),
                aliases=BIOMARKER_ALIASES.get(code, (code,)),
                unit=row["unit"].strip(),
                low=_float(row.get("low")),
                high=_float(row.get("high")),
                critical_low=_float(row.get("critical_low")),
                critical_high=_float(row.get("critical_high")),
                borderline=_float(row.get("borderline")),
                supplement_component_id=(row.get("supplement_component_id") or "").strip() or None,
                supplement_name=(row.get("supplement_name") or "").strip() or None,
                medical_condition=(row.get("medical_condition") or "").strip() or None,
                safety_condition=(row.get("safety_condition") or "").strip() or None,
                condition_code=(row.get("condition_code") or "").strip() or None,
                sex=(row.get("sex") or "any").strip() or "any",
                pregnant=(row.get("pregnant") or "any").strip() or "any",
                age_min=_float(row.get("age_min")),
                age_max=_float(row.get("age_max")),
                unit_conversions=_parse_conversions(row.get("alt_units")),
                source_ids=tuple(s for s in (row.get("source_ids") or "").split("|") if s),
                note=(row.get("note") or "").strip(),
            )
            variants.setdefault(code, []).append(definition)
            if definition.specificity == 0 and code not in defaults:
                defaults[code] = definition
    for code, items in variants.items():
        defaults.setdefault(code, items[0])
    return defaults, variants


BIOMARKERS, BIOMARKER_VARIANTS = _load_definitions()


def definition_for(
    code: str,
    *,
    sex: str | None = None,
    age: float | None = None,
    pregnant: bool | None = None,
) -> BiomarkerDefinition | None:
    """Definicion mas especifica que aplica al contexto del paciente; por defecto la fila generica."""
    candidates = BIOMARKER_VARIANTS.get(code)
    if not candidates:
        return None
    sex_key = {"femenino": "female", "masculino": "male", "f": "female", "m": "male"}.get(str(sex or "").lower(), str(sex or "").lower() or None)
    matching = [d for d in candidates if d.matches(sex=sex_key, age=age, pregnant=pregnant)]
    if not matching:
        return BIOMARKERS.get(code)
    return max(matching, key=lambda d: d.specificity)


def convert_to_canonical(code: str, value: float, unit: str | None) -> tuple[float, float] | None:
    """Convierte `value` expresado en `unit` a la unidad canonica del biomarcador.

    Devuelve (valor_convertido, factor) o None si la unidad ya es la canonica o no se conoce.
    """
    definition = BIOMARKERS.get(code)
    if definition is None or not unit:
        return None
    key = normalize_unit_key(unit)
    if key == normalize_unit_key(definition.unit):
        return None
    factor = definition.unit_conversions.get(key)
    if factor is None:
        return None
    return value * factor, factor


def known_units(code: str) -> set[str]:
    definition = BIOMARKERS.get(code)
    if definition is None:
        return set()
    return {normalize_unit_key(definition.unit), *definition.unit_conversions.keys()}
