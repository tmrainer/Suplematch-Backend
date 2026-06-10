from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.observability import log_event
from app.db.models import LabBiomarkerResult, LabReport, User, utcnow
from app.schemas.labs import LabBiomarkerInput


MAX_LAB_UPLOAD_BYTES = 8 * 1024 * 1024


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

ALIASES: dict[str, str] = {
    alias: code
    for code, definition in BIOMARKERS.items()
    for alias in definition.aliases
}


def normalize_biomarker_code(value: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return ALIASES.get(value.strip().lower(), clean)


def _clean_float(value: Any) -> float | None:
    try:
        number = float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _status_for_value(
    definition: BiomarkerDefinition,
    value: float,
    reference_low: float | None,
    reference_high: float | None,
) -> tuple[str, str]:
    low = reference_low if reference_low is not None else definition.low
    high = reference_high if reference_high is not None else definition.high

    if definition.critical_low is not None and value < definition.critical_low:
        return "critical_low", "critical"
    if definition.critical_high is not None and value > definition.critical_high:
        return "critical_high", "critical"
    if low is not None and value < low:
        return "low", "warning"
    if high is not None and value > high:
        return "high", "warning"
    return "normal", "normal"


def _biomarker_out(
    *,
    code: str,
    value: float,
    unit: str | None,
    reference_low: float | None = None,
    reference_high: float | None = None,
    confidence: float = 1.0,
    source_text: str | None = None,
) -> dict[str, Any] | None:
    definition = BIOMARKERS.get(normalize_biomarker_code(code))
    if definition is None:
        return None
    # If extracted range looks like a "deficit" category (high < definition.low),
    # ignore it and use built-in definition ranges instead
    if (
        reference_low is not None
        and reference_high is not None
        and definition.low is not None
        and reference_high <= definition.low
    ):
        reference_low, reference_high = None, None

    status_value, severity = _status_for_value(definition, value, reference_low, reference_high)
    return {
        "code": definition.code,
        "display_name": definition.display_name,
        "value": round(value, 4),
        "unit": unit or definition.unit,
        "reference_low": reference_low if reference_low is not None else definition.low,
        "reference_high": reference_high if reference_high is not None else definition.high,
        "status": status_value,
        "severity": severity,
        "confidence": confidence,
        "source_text": source_text,
    }


def _alias_matches(alias: str, line: str) -> bool:
    if len(alias) <= 5:
        return bool(re.search(r"(?<![a-z])" + re.escape(alias) + r"(?![a-z])", line))
    return alias in line


def parse_lab_text(raw_text: str) -> list[dict[str, Any]]:
    text = _normalize_ocr_text(raw_text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    results: dict[str, dict[str, Any]] = {}

    # Longest aliases first so "aspartato aminotransferasa" wins over "ast"
    sorted_aliases = sorted(ALIASES.items(), key=lambda x: len(x[0]), reverse=True)

    for i, line in enumerate(lines):
        normalized_line = line.lower()
        for alias, code in sorted_aliases:
            if code in results:
                continue
            if not _alias_matches(alias, normalized_line):
                continue

            # Try value on the same line first
            pattern = rf"{re.escape(alias)}[^\d,.-]{{0,70}}([-+]?\d+(?:[.,]\d+)?)\s*([a-zA-Z/%µμ./0-9]+)?"
            match = re.search(pattern, normalized_line)
            context_text = normalized_line

            if not match:
                # Biomarker name found but value is on a following line (multi-line format)
                next_text = " ".join(lines[i + 1:i + 4]).lower() if i + 1 < len(lines) else ""
                combined = normalized_line + " " + next_text
                value_match = re.search(r"([-+]?\d+(?:[.,]\d+)?)\s*([a-zA-Z/%µμ./0-9]+)?", next_text)
                if value_match:
                    match = value_match
                    context_text = combined
                else:
                    match = re.search(r"([-+]?\d+(?:[.,]\d+)?)\s*([a-zA-Z/%µμ./0-9]+)?", normalized_line)

            if not match:
                continue
            value = _clean_float(match.group(1))
            if value is None or value <= 0:
                continue
            unit = _normalize_unit(match.group(2) if len(match.groups()) >= 2 else None)
            reference_low, reference_high = _extract_reference_range(context_text, match.end())
            parsed = _biomarker_out(
                code=code,
                value=value,
                unit=unit,
                reference_low=reference_low,
                reference_high=reference_high,
                confidence=0.76,
                source_text=line[:500],
            )
            if parsed is not None:
                results[parsed["code"]] = parsed

    return list(results.values())


def _normalize_ocr_text(raw_text: str) -> str:
    text = raw_text.replace("\r", "\n")
    replacements = {
        "µ": "u",
        "μ": "u",
        "—": "-",
        "–": "-",
        "／": "/",
        "|": " ",
        "\t": " ",
        "º": "o",
        "°": "",  # degree sign
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    # Normalize dotted abbreviations common in Peruvian labs
    dotted = [
        ("T.G.O.", "TGO"), ("T.G.P.", "TGP"), ("T.G.O", "TGO"), ("T.G.P", "TGP"),
        ("H.T.O.", "HTO"), ("H.B.", "HB"), ("Vit.", "Vit"), ("VIT.", "VIT"),
        ("Prot.", "Prot"), ("Cre.", "Cre"),
    ]
    for old, new in dotted:
        text = text.replace(old, new)
        text = text.replace(old.lower(), new.lower())

    # Normalize units (handles spaces and case variations)
    text = re.sub(r"(?i)\bmg\s*/\s*dl\b", "mg/dL", text)
    text = re.sub(r"(?i)\bng\s*/\s*ml\b", "ng/mL", text)
    text = re.sub(r"(?i)\bpg\s*/\s*ml\b", "pg/mL", text)
    text = re.sub(r"(?i)\bg\s*/\s*dl\b", "g/dL", text)
    text = re.sub(r"(?i)\bu\s*/\s*l\b", "U/L", text)
    text = re.sub(r"(?i)\bui\s*/\s*l\b", "U/L", text)
    text = re.sub(r"(?i)\bug\s*/\s*dl\b", "ug/dL", text)
    text = re.sub(r"(?i)\bmg\s*/\s*l\b", "mg/L", text)
    text = re.sub(r"(?i)\bm(?:ui|iu)\s*/\s*m?l\b", "mUI/L", text)  # mUI/L, mUI/mL, mIU/L, mIU/mL
    # Collapse multiple spaces (but keep newlines)
    text = re.sub(r" {2,}", " ", text)
    return text


def _normalize_unit(unit: str | None) -> str | None:
    if not unit:
        return None
    # Strip temperature conditions like "a 37 °C" or "37c"
    unit = re.sub(r"\s+a\s+\d+.*$", "", unit.strip(), flags=re.IGNORECASE)
    unit = re.sub(r"\s*\d+\s*°?\s*[cC]$", "", unit.strip())
    clean = unit.strip(" .,:;()[]").replace("ul", "uL")
    aliases = {
        "mg/dl": "mg/dL",
        "ng/ml": "ng/mL",
        "pg/ml": "pg/mL",
        "g/dl": "g/dL",
        "u/l": "U/L",
        "ui/l": "U/L",
        "ug/dl": "ug/dL",
        "mg/l": "mg/L",
        "mui/l": "mUI/L",
        "mui/ml": "mUI/L",
        "miu/l": "mUI/L",
        "miu/ml": "mUI/L",
        "iu/l": "IU/L",
        "iu/ml": "IU/mL",
        "uiu/ml": "uIU/mL",  # TSH sometimes reported in uIU/mL
        "%": "%",
        "porciento": "%",
    }
    return aliases.get(clean.lower(), clean)


_RECOMMENDED_LABELS = re.compile(
    r"valores?\s+recomendados?|rango\s+normal|normal|referencia|adecuado|optimo|óptimo"
    r"|v\.?\s*n\.?|v\.?\s*r\.?|valores?\s+normales?|valores?\s+de\s+referencia"
    r"|rango\s+de\s+referencia|val\.\s*ref\.|vr\b",
    re.IGNORECASE,
)
_RANGE_PATTERN = re.compile(r"([-+]?\d+(?:[.,]\d+)?)\s*(?:-|a|hasta|--)\s*([-+]?\d+(?:[.,]\d+)?)")
_UPPER_BOUND_PATTERN = re.compile(r"[<≤]\s*([-+]?\d+(?:[.,]\d+)?)")
_LOWER_BOUND_PATTERN = re.compile(r"[>≥]\s*([-+]?\d+(?:[.,]\d+)?)")


def _extract_reference_range(line: str, start_index: int) -> tuple[float | None, float | None]:
    tail = line[start_index:start_index + 300]

    # Collect all full N1-N2 ranges in the tail with their positions
    candidates: list[tuple[int, float, float]] = []
    for m in _RANGE_PATTERN.finditer(tail):
        low = _clean_float(m.group(1))
        high = _clean_float(m.group(2))
        if low is not None and high is not None and low < high:
            candidates.append((m.start(), low, high))

    if candidates:
        # Prefer a range that has a "normal/recommended" label within 50 chars
        for pos, low, high in candidates:
            window_start = max(0, pos - 50)
            window_end = min(len(tail), pos + 80)
            window = tail[window_start:window_end]
            if _RECOMMENDED_LABELS.search(window):
                return low, high
        return candidates[0][1], candidates[0][2]

    # Fallback: handle "< N" (upper bound only) — common in Peruvian labs for
    # things like glucose (<100), cholesterol (<200), TSH, etc.
    upper_match = _UPPER_BOUND_PATTERN.search(tail)
    if upper_match:
        high = _clean_float(upper_match.group(1))
        if high is not None:
            return None, high

    # Fallback: handle "> N" (lower bound only) — e.g. HDL (>40)
    lower_match = _LOWER_BOUND_PATTERN.search(tail)
    if lower_match:
        low = _clean_float(lower_match.group(1))
        if low is not None:
            return low, None

    return None, None


def analyze_biomarkers(biomarkers: list[dict[str, Any]]) -> dict[str, Any]:
    warnings: list[str] = []
    safety_actions: list[str] = []
    supplement_signals: list[dict[str, Any]] = []
    recommendation_notes: list[str] = []
    commercial_blocked = False
    safety_level = "normal"

    by_code = {item["code"]: item for item in biomarkers}

    for item in biomarkers:
        definition = BIOMARKERS.get(item["code"])
        if definition is None:
            continue
        status_value = item["status"]
        if item["severity"] == "critical":
            commercial_blocked = True
            safety_level = "medical_review_required"
            warnings.append(f"{item['display_name']}: valor crítico reportado; requiere evaluación profesional.")
        elif status_value in {"low", "high"} and safety_level == "normal":
            safety_level = "caution"

        if definition.safety_condition and status_value != "normal":
            commercial_blocked = True
            safety_level = "medical_review_required"
            warnings.append(f"{item['display_name']}: puede implicar condición de seguridad ({definition.safety_condition}).")

        if definition.supplement_name and status_value == "low":
            supplement_signals.append(
                {
                    "biomarker_code": definition.code,
                    "component_id": definition.supplement_component_id or f"lab_{definition.code}",
                    "supplement": definition.supplement_name,
                    "reason": f"{definition.display_name} por debajo del rango de referencia.",
                    "requires_professional_review": definition.code in {"ferritin", "calcium"} or commercial_blocked,
                }
            )

    ferritin = by_code.get("ferritin")
    iron = by_code.get("iron")
    hemoglobin = by_code.get("hemoglobin")
    hematocrit = by_code.get("hematocrit")

    anemia_low = (
        (ferritin and ferritin["status"] in {"low", "critical_low"})
        or (iron and iron["status"] in {"low", "critical_low"})
    )
    hb_low = hemoglobin and hemoglobin["status"] in {"low", "critical_low"}
    hct_low = hematocrit and hematocrit["status"] in {"low", "critical_low"}

    if anemia_low and (hb_low or hct_low):
        commercial_blocked = True
        safety_level = "medical_review_required"
        warnings.append("Patrón compatible con posible deficiencia de hierro/anemia; no iniciar hierro sin evaluación profesional.")

    if commercial_blocked:
        safety_actions.insert(0, "No comprar ni iniciar suplementos usando solo este resultado.")
        safety_actions.append("Consultar con médico/nutricionista y validar unidades, rangos y contexto clínico.")
    elif safety_level == "caution":
        safety_actions.append("Usar estos resultados solo como apoyo; confirmar con profesional antes de suplementar.")

    if not biomarkers:
        warnings.append("No se detectaron biomarcadores soportados; revisar calidad del archivo o ingresar valores manualmente.")
        safety_level = "caution"

    recommendation_notes.extend(
        [
            "Los resultados de laboratorio no se interpretan como diagnóstico.",
            "Las unidades y rangos pueden variar entre laboratorios.",
        ]
    )

    return {
        "warnings": _dedupe(warnings),
        "safety_level": safety_level,
        "safety_actions": _dedupe(safety_actions),
        "commercial_recommendations_blocked": commercial_blocked,
        "supplement_signals": supplement_signals,
        "recommendation_notes": recommendation_notes,
    }


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


class LabAnalysisService:
    def __init__(self, db: Session | None = None):
        self.db = db

    def analyze_manual(
        self,
        values: list[LabBiomarkerInput],
        *,
        user: User | None = None,
        persist: bool = True,
        source_note: str | None = None,
    ) -> dict[str, Any]:
        biomarkers = []
        for value in values:
            parsed = _biomarker_out(
                code=value.code,
                value=value.value,
                unit=value.unit,
                reference_low=value.reference_low,
                reference_high=value.reference_high,
                confidence=1.0,
                source_text=source_note,
            )
            if parsed is not None:
                biomarkers.append(parsed)
        return self._build_response(
            biomarkers=biomarkers,
            source_type="manual",
            user=user,
            persist=persist,
            parsed_payload={"source_note": source_note},
            raw_text=None,
            ocr_engine=None,
        )

    def analyze_text(
        self,
        raw_text: str,
        *,
        source_type: str = "text",
        user: User | None = None,
        persist: bool = True,
        file_name: str | None = None,
        file_mime_type: str | None = None,
        ocr_engine: str | None = None,
    ) -> dict[str, Any]:
        biomarkers = parse_lab_text(raw_text)
        return self._build_response(
            biomarkers=biomarkers,
            source_type=source_type,
            user=user,
            persist=persist,
            parsed_payload={"file_name": file_name, "file_mime_type": file_mime_type},
            raw_text=raw_text[:20000],
            file_name=file_name,
            file_mime_type=file_mime_type,
            ocr_engine=ocr_engine,
        )

    async def analyze_upload(
        self,
        upload: UploadFile,
        *,
        user: User | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        content = await upload.read()
        if len(content) > MAX_LAB_UPLOAD_BYTES:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Archivo demasiado grande.")

        mime = upload.content_type or "application/octet-stream"
        file_name = upload.filename or "lab_report"
        raw_text, source_type, engine = extract_text_from_upload(content, file_name=file_name, mime_type=mime)
        return self.analyze_text(
            raw_text,
            source_type=source_type,
            user=user,
            persist=persist,
            file_name=file_name,
            file_mime_type=mime,
            ocr_engine=engine,
        )

    def history(self, user: User, limit: int = 20) -> list[dict[str, Any]]:
        if self.db is None:
            return []
        rows = list(
            self.db.scalars(
                select(LabReport)
                .where(LabReport.user_id == user.id, LabReport.deleted_at.is_(None))
                .order_by(LabReport.created_at.desc())
                .limit(limit)
            )
        )
        return [
            {
                "id": row.id,
                "source_type": row.source_type,
                "status": row.status,
                "created_at": row.created_at,
                "biomarker_count": len((row.analysis_json or {}).get("biomarkers", [])),
                "safety_level": (row.analysis_json or {}).get("safety_level", "normal"),
                "commercial_recommendations_blocked": bool((row.analysis_json or {}).get("commercial_recommendations_blocked", False)),
                "warnings": (row.analysis_json or {}).get("warnings", []),
                "biomarkers": (row.analysis_json or {}).get("biomarkers", []),
                "supplement_signals": (row.analysis_json or {}).get("supplement_signals", []),
                "ocr_engine": (row.analysis_json or {}).get("ocr_engine"),
                "file_name": row.file_name,
            }
            for row in rows
        ]

    def export_user_health_data(self, user: User) -> dict[str, Any]:
        if self.db is None:
            return {"exported_at": None, "user_id": user.id, "reports": []}
        rows = list(
            self.db.scalars(
                select(LabReport)
                .where(LabReport.user_id == user.id, LabReport.deleted_at.is_(None))
                .order_by(LabReport.created_at.desc())
            )
        )
        return {
            "exported_at": utcnow(),
            "user_id": user.id,
            "reports": [
                {
                    "id": row.id,
                    "source_type": row.source_type,
                    "file_name": row.file_name,
                    "file_mime_type": row.file_mime_type,
                    "created_at": row.created_at,
                    "status": row.status,
                    "consent_health_data": row.consent_health_data,
                    "raw_text": row.raw_text,
                    "parsed_payload": row.parsed_payload_json or {},
                    "analysis": row.analysis_json or {},
                }
                for row in rows
            ],
        }

    def delete_report(self, user: User, report_id: str) -> bool:
        if self.db is None:
            return False
        report = self.db.scalar(
            select(LabReport)
            .where(LabReport.id == report_id, LabReport.user_id == user.id, LabReport.deleted_at.is_(None))
            .limit(1)
        )
        if report is None:
            return False
        self._redact_report(report)
        self.db.commit()
        log_event("lab_report_deleted", report_id=str(report.id), user_id=str(user.id))
        return True

    def delete_all_user_health_data(self, user: User) -> int:
        if self.db is None:
            return 0
        reports = list(
            self.db.scalars(
                select(LabReport).where(LabReport.user_id == user.id, LabReport.deleted_at.is_(None))
            )
        )
        for report in reports:
            self._redact_report(report)
        self.db.commit()
        log_event("lab_reports_deleted_bulk", user_id=str(user.id), count=len(reports))
        return len(reports)

    def _redact_report(self, report: LabReport) -> None:
        now = utcnow()
        self.db.execute(delete(LabBiomarkerResult).where(LabBiomarkerResult.lab_report_id == report.id))
        report.raw_text = None
        report.parsed_payload_json = {}
        report.analysis_json = {"deleted": True, "deleted_at": now.isoformat()}
        report.status = "deleted"
        report.deleted_at = now

    def _build_response(
        self,
        *,
        biomarkers: list[dict[str, Any]],
        source_type: str,
        user: User | None,
        persist: bool,
        parsed_payload: dict[str, Any],
        raw_text: str | None,
        file_name: str | None = None,
        file_mime_type: str | None = None,
        ocr_engine: str | None = None,
    ) -> dict[str, Any]:
        analysis = analyze_biomarkers(biomarkers)
        payload = {
            "source_type": source_type,
            "biomarkers": biomarkers,
            **analysis,
            "extracted_text_preview": raw_text[:600] if raw_text else None,
            "ocr_engine": ocr_engine,
        }
        report_id = None
        created_at = None
        if persist and self.db is not None:
            report = LabReport(
                user_id=user.id if user else None,
                source_type=source_type,
                file_name=file_name,
                file_mime_type=file_mime_type,
                raw_text=raw_text,
                parsed_payload_json=parsed_payload,
                analysis_json=payload,
                consent_health_data=True,
                status="processed",
            )
            self.db.add(report)
            self.db.flush()
            for item in biomarkers:
                self.db.add(
                    LabBiomarkerResult(
                        lab_report_id=report.id,
                        code=item["code"],
                        display_name=item["display_name"],
                        value=item["value"],
                        unit=item["unit"],
                        reference_low=item.get("reference_low"),
                        reference_high=item.get("reference_high"),
                        status=item["status"],
                        severity=item["severity"],
                        confidence=item["confidence"],
                        source_text=item.get("source_text"),
                    )
                )
            self.db.commit()
            self.db.refresh(report)
            report_id = report.id
            created_at = report.created_at

        log_event(
            "lab_report_analyzed",
            report_id=str(report_id) if report_id else None,
            user_id=str(user.id) if user else None,
            source_type=source_type,
            biomarker_count=len(biomarkers),
            safety_level=analysis["safety_level"],
            commercial_recommendations_blocked=analysis["commercial_recommendations_blocked"],
        )
        return {
            "report_id": report_id,
            "created_at": created_at,
            **payload,
        }


def extract_text_from_upload(content: bytes, *, file_name: str, mime_type: str) -> tuple[str, str, str | None]:
    lower_name = file_name.lower()
    if mime_type.startswith("text/") or lower_name.endswith((".txt", ".csv")):
        return content.decode("utf-8", errors="ignore"), "text", "plain_text"

    if mime_type == "application/pdf" or lower_name.endswith(".pdf"):
        text = _extract_pdf_text(content)
        return text, "pdf", "pypdf"

    if mime_type.startswith("image/") or lower_name.endswith((".png", ".jpg", ".jpeg", ".webp", ".tiff")):
        text = _extract_image_text(content)
        return text, "image", "tesseract"

    raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Formato no soportado para OCR.")


def _extract_pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Extracción PDF no disponible.") from exc

    try:
        reader = PdfReader(io.BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No se pudo leer el PDF.") from exc
    if not text.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="PDF sin texto detectable; subir imagen legible o ingresar manualmente.")
    return text


def _extract_image_text(content: bytes) -> str:
    try:
        from PIL import Image
        import pytesseract
    except ImportError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OCR de imágenes no disponible.") from exc

    try:
        image = Image.open(io.BytesIO(content))
        text = pytesseract.image_to_string(image, lang="spa+eng")
    except pytesseract.TesseractNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Motor Tesseract no instalado.") from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No se pudo procesar la imagen.") from exc
    if not text.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No se detectó texto en la imagen.")
    return text
