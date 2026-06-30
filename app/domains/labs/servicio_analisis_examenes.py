from __future__ import annotations

import io
import math
import re
import tempfile
import unicodedata
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.observability import log_event, metrics
from app.db.models import LabBiomarkerResult, LabReport, User, utcnow
from app.domains.labs.biomarcadores import BIOMARKERS, BiomarkerDefinition
from app.domains.labs.esquemas import LabBiomarkerInput


MAX_LAB_UPLOAD_BYTES = 8 * 1024 * 1024


ALIASES: dict[str, str] = {
    alias: code
    for code, definition in BIOMARKERS.items()
    for alias in definition.aliases
}

OCR_GUIDE_WORDS: tuple[str, ...] = tuple(
    sorted(
        {
            token
            for definition in BIOMARKERS.values()
            for phrase in (*definition.aliases, definition.display_name, definition.unit)
            for token in re.split(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9/%.-]+", phrase)
            if len(token) >= 2
        }
        | {
            "resultado", "resultados", "unidad", "unidades", "referencia", "referencial",
            "valores", "normales", "rango", "examen", "analisis", "análisis", "VN", "VR",
            "mg/dL", "ng/mL", "pg/mL", "g/dL", "ug/dL", "U/L", "mg/L", "mUI/L",
            "mmol/L",
        },
        key=lambda value: (value.lower(), value),
    )
)


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
    if alias in line:
        return True
    alias_key = _ocr_name_key(alias)
    line_key = _ocr_name_key(line)
    return alias_key in line_key


def _ocr_name_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    ascii_text = ascii_text.lower()
    # Tesseract commonly confuses letters and digits in lab names. This is only
    # used for keyword matching, never for numeric value extraction.
    ascii_text = ascii_text.translate(str.maketrans({"0": "o", "1": "i", "3": "e", "5": "s", "8": "b"}))
    return re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()


def _confidence_for_extraction(
    *,
    alias: str,
    unit: str | None,
    reference_low: float | None,
    reference_high: float | None,
    used_following_line: bool,
    context_text: str,
) -> float:
    confidence = 0.62
    if len(alias) >= 10:
        confidence += 0.12
    elif len(alias) >= 6:
        confidence += 0.08
    else:
        confidence -= 0.08

    if unit:
        confidence += 0.08
    else:
        confidence -= 0.08

    if reference_low is not None or reference_high is not None:
        confidence += 0.08

    if used_following_line:
        confidence -= 0.08

    if _RECOMMENDED_LABELS.search(context_text):
        confidence += 0.03

    return round(max(0.35, min(confidence, 0.96)), 2)


PLAUSIBLE_VALUE_RANGES: dict[str, tuple[float, float]] = {
    "hemoglobin": (3.0, 25.0),
    "hematocrit": (10.0, 75.0),
    "creatinine": (0.1, 20.0),
    "glucose": (20.0, 800.0),
    "hba1c": (3.0, 18.0),
    "ldl": (0.0, 400.0),
    "hdl": (5.0, 200.0),
    "triglycerides": (20.0, 2000.0),
    "total_cholesterol": (50.0, 500.0),
    "tsh": (0.001, 100.0),
    "t3": (0.1, 10.0),
    "t4": (0.5, 30.0),
    "free_t4": (0.1, 8.0),
    "vitamin_d": (1.0, 200.0),
    "b12": (50.0, 3000.0),
    "ferritin": (1.0, 2000.0),
    "iron": (5.0, 500.0),
    "folate": (0.5, 100.0),
    "calcium": (3.0, 20.0),
    "magnesium": (0.2, 10.0),
    "zinc": (10.0, 300.0),
    "potassium": (1.0, 10.0),
    "egfr": (1.0, 200.0),
    "ast": (1.0, 1000.0),
    "alt": (1.0, 1000.0),
    "crp": (0.01, 500.0),
    "uric_acid": (0.5, 30.0),
}


_UNSAFE_FOLLOWING_CONTEXT = re.compile(
    r"\b(direcci[oó]n|tel[eé]f|telefono|tel\.|whatsapp|paciente|edad|fecha|"
    r"indicaciones|m[eé]todo|muestra|historia|cl[ií]nica|sede|p[aá]gina)\b",
    re.IGNORECASE,
)


def _is_excluded_alias_context(code: str, line: str) -> bool:
    if re.search(
        r"(\$\s*\d|\b83036\b|medical/surgical|cpt\b|billing|invoice|amount|charge|subtotal|total\s*\$)",
        line,
        re.IGNORECASE,
    ):
        return True
    if code == "hemoglobin" and re.search(r"hba1c|glicosilad", line, re.IGNORECASE):
        return True
    if code == "glucose" and re.search(r"\balb[uú]mina\b|\bacetona\b|orina|uroan[aá]lisis", line, re.IGNORECASE):
        return True
    if code in {"tsh", "t3", "t4", "free_t4"} and re.search(
        r"\b(biologically|active|fraction|correlate|clinical status|binding protein)\b",
        line,
        re.IGNORECASE,
    ):
        return True
    return False


def _has_other_biomarker_before_value(code: str, text: str, value_start: int) -> bool:
    prefix = text[:value_start].lower()
    for alias, alias_code in ALIASES.items():
        if alias_code == code:
            continue
        if _alias_matches(alias, prefix):
            return True
    return False


def _has_unexpected_words_before_value(text: str, value_start: int) -> bool:
    prefix = text[:value_start].lower()
    prefix = re.sub(
        r"\b(resultado|resultados|unidad|unidades|valor|valores|referencia|referencial|"
        r"rango|normal|normales|vn|vr|um|u\.m)\b",
        " ",
        prefix,
        flags=re.IGNORECASE,
    )
    return bool(re.search(r"[a-záéíóúüñ]{2,}", prefix, re.IGNORECASE))


def _looks_like_reference_range_value(text: str, match_end: int) -> bool:
    return bool(re.match(r"\s*(?:-|a|hasta|--)\s*[-+]?\d+(?:[.,]\d+)?", text[match_end:], re.IGNORECASE))


def _alias_regex(alias: str) -> str:
    parts = [re.escape(part) for part in re.split(r"[^a-zA-Z0-9]+", alias) if part]
    return r"[^a-zA-Z0-9]*".join(parts) if parts else re.escape(alias)


def _leading_value_match_for_code(code: str, line: str):
    if re.match(r"^\s*\d+\.\s+", line):
        return None
    first_value = re.match(r"^\s*([-+]?\d+(?:[.,]\d+)?)", line)
    if not first_value:
        return None
    next_number = re.search(r"(?<![a-zA-Z0-9])(?<![.,])\d+(?:[.,]\d+)?", line[first_value.end():])
    name_segment = line[first_value.end(): first_value.end() + (next_number.start() if next_number else 80)]
    for alias, alias_code in ALIASES.items():
        if alias_code == code and _alias_matches(alias, name_segment):
            return first_value
    return None


def _value_is_plausible(code: str, value: float) -> bool:
    allowed = PLAUSIBLE_VALUE_RANGES.get(code)
    if not allowed:
        return True
    low, high = allowed
    return low <= value <= high


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
            if _is_excluded_alias_context(code, normalized_line):
                continue

            # Try value on the same line first. Some lab PDFs export rows as
            # "1.00Creatinine", so a leading value directly attached to the
            # analyte name is a valid result and must win over reference ranges.
            match = _leading_value_match_for_code(code, normalized_line)
            if not match:
                pattern = rf"{re.escape(alias)}[^\d,.-]{{0,70}}(?<![a-zA-Z])([-+]?\d+(?:[.,]\d+)?)(?![a-zA-Z])\s*([a-zA-Z/%µμ./0-9]+)?"
                match = re.search(pattern, normalized_line)
            context_text = normalized_line
            used_following_line = False

            if not match:
                # Biomarker name found but value is on a following line (multi-line format)
                next_text = " ".join(lines[i + 1:i + 4]).lower() if i + 1 < len(lines) else ""
                combined = normalized_line + " " + next_text
                value_match = _RESULT_VALUE_PATTERN.search(next_text)
                if (
                    value_match
                    and not _UNSAFE_FOLLOWING_CONTEXT.search(next_text)
                    and not _has_other_biomarker_before_value(code, next_text, value_match.start())
                    and not _has_unexpected_words_before_value(next_text, value_match.start())
                    and not _looks_like_reference_range_value(next_text, value_match.end())
                ):
                    match = value_match
                    context_text = combined
                    used_following_line = True
                else:
                    match = _RESULT_VALUE_PATTERN.search(normalized_line)

            if not match:
                continue
            value = _clean_float(match.group(1))
            if value is None or value <= 0:
                continue
            if not _value_is_plausible(code, value):
                continue
            unit = _normalize_unit(match.group(2) if len(match.groups()) >= 2 else None)
            if unit is None:
                unit = _find_unit_near_value(context_text, match.end())
            reference_low, reference_high = _extract_reference_range(context_text, match.end())
            confidence = _confidence_for_extraction(
                alias=alias,
                unit=unit,
                reference_low=reference_low,
                reference_high=reference_high,
                used_following_line=used_following_line,
                context_text=context_text,
            )
            parsed = _biomarker_out(
                code=code,
                value=value,
                unit=unit,
                reference_low=reference_low,
                reference_high=reference_high,
                confidence=confidence,
                source_text=line[:500],
            )
            if parsed is not None:
                results[parsed["code"]] = parsed

    return list(results.values())


def _find_unit_near_value(text: str, start_index: int) -> str | None:
    window = text[start_index:start_index + 80]
    for raw_unit in re.findall(r"[a-zA-Zµμ/%]+(?:\s*/\s*[a-zA-Z0-9µμ.]+)?", window):
        unit = _normalize_unit(raw_unit)
        if unit is not None:
            return unit
    return None


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
    text = re.sub(r"(?i)\bng\s*/\s*dl\b", "ng/dL", text)
    text = re.sub(r"(?i)\bug\s*/\s*l\b", "ug/L", text)
    text = re.sub(r"(?i)\bmg\s*/\s*l\b", "mg/L", text)
    text = re.sub(r"(?i)\bmmol\s*/\s*l\b", "mmol/L", text)
    text = re.sub(r"(?i)\bnmol\s*/\s*l\b", "nmol/L", text)
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
    if clean.lower() in {
        "unidad", "unidades", "resultado", "resultados", "valor", "valores",
        "referencia", "referencial", "normal", "normales", "rango", "vn", "vr",
    }:
        return None
    aliases = {
        "mg/dl": "mg/dL",
        "ng/ml": "ng/mL",
        "pg/ml": "pg/mL",
        "g/dl": "g/dL",
        "u/l": "U/L",
        "ui/l": "U/L",
        "ug/dl": "ug/dL",
        "ng/dl": "ng/dL",
        "ug/l": "ug/L",
        "mg/l": "mg/L",
        "mmol/l": "mmol/L",
        "nmol/l": "nmol/L",
        "mui/l": "mUI/L",
        "mui/ml": "mUI/L",
        "miu/l": "mUI/L",
        "miu/ml": "mUI/L",
        "uui/ml": "uIU/mL",
        "iu/l": "IU/L",
        "iu/ml": "IU/mL",
        "uiu/ml": "uIU/mL",  # TSH sometimes reported in uIU/mL
        "%": "%",
        "porciento": "%",
    }
    normalized = aliases.get(clean.lower())
    if normalized is not None:
        return normalized
    if re.match(r"^[a-zA-Zµμ]+/[a-zA-Z0-9µμ.]+$", clean) or clean == "%":
        return clean
    return None


_RECOMMENDED_LABELS = re.compile(
    r"valores?\s+recomendados?|rango\s+normal|normal|referencia|adecuado|optimo|óptimo"
    r"|v\.?\s*n\.?|v\.?\s*r\.?|valores?\s+normales?|valores?\s+de\s+referencia"
    r"|rango\s+de\s+referencia|val\.\s*ref\.|vr\b",
    re.IGNORECASE,
)
_RANGE_PATTERN = re.compile(r"([-+]?\d+(?:[.,]\d+)?)\s*(?:-|a|hasta|--)\s*([-+]?\d+(?:[.,]\d+)?)")
_UPPER_BOUND_PATTERN = re.compile(r"[<≤]\s*([-+]?\d+(?:[.,]\d+)?)")
_LOWER_BOUND_PATTERN = re.compile(r"[>≥]\s*([-+]?\d+(?:[.,]\d+)?)")
_RESULT_VALUE_PATTERN = re.compile(r"(?<![a-zA-Z])([-+]?\d+(?:[.,]\d+)?)(?![a-zA-Z])\s*([a-zA-Z/%µμ./0-9]+)?")


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
        if float(item.get("confidence") or 1.0) < 0.65:
            warnings.append(
                f"{item['display_name']}: lectura OCR con confianza baja; confirma valor, unidad y rango antes de usarlo."
            )
            if safety_level == "normal":
                safety_level = "caution"

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
        metrics.record_domain_event("lab_report_analyzed", analysis["safety_level"])
        if analysis["commercial_recommendations_blocked"]:
            metrics.record_domain_event("lab_commercial_block", "blocked")
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
        text, engine = _extract_pdf_text(content)
        return text, "pdf", engine

    if mime_type.startswith("image/") or lower_name.endswith((".png", ".jpg", ".jpeg", ".webp", ".tiff")):
        text = _extract_image_text(content)
        return text, "image", "tesseract"

    raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Formato no soportado para OCR.")


def _extract_pdf_text(content: bytes) -> tuple[str, str]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Extracción PDF no disponible.") from exc

    try:
        reader = PdfReader(io.BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No se pudo leer el PDF.") from exc
    if text.strip() and len(text.strip()) >= 20:
        return text, "pypdf"

    tesseract_text = _extract_pdf_images_text(content)
    if tesseract_text.strip():
        return tesseract_text, "pdf2image+tesseract"

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="PDF sin texto detectable; sube una imagen legible o ingresa los valores manualmente.",
    )


def _extract_pdf_images_text(content: bytes) -> str:
    try:
        from pdf2image import convert_from_bytes
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OCR de PDF escaneado no disponible; falta pdf2image.",
        ) from exc

    try:
        pages = convert_from_bytes(content, dpi=220, fmt="png", thread_count=1)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No se pudo convertir el PDF escaneado para OCR.",
        ) from exc

    texts = [_extract_image_text_from_pil(page) for page in pages[:5]]
    return "\n".join(text for text in texts if text.strip())


def _extract_image_text(content: bytes) -> str:
    try:
        from PIL import Image
    except ImportError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OCR de imágenes no disponible.") from exc

    try:
        image = Image.open(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No se pudo procesar la imagen.") from exc

    text = _extract_image_text_from_pil(image)
    if not text.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No se detectó texto en la imagen.")
    return text


def _extract_image_text_from_pil(image) -> str:
    try:
        from PIL import ImageOps
        import pytesseract
    except ImportError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OCR de imágenes no disponible.") from exc

    try:
        prepared = _prepare_ocr_image(image, ImageOps)
        text = _tesseract_image_to_string(pytesseract, prepared, psm=6)
        if not text.strip():
            text = _tesseract_image_to_string(pytesseract, prepared, psm=11)
        return text
    except pytesseract.TesseractNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Motor Tesseract no instalado.") from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No se pudo procesar la imagen con OCR.") from exc


def _prepare_ocr_image(image, image_ops):
    prepared = image.convert("L")
    prepared = image_ops.autocontrast(prepared)
    width, height = prepared.size
    if width < 1500:
        scale = min(3, max(2, math.ceil(1500 / max(width, 1))))
        prepared = prepared.resize((width * scale, height * scale))
    return prepared.point(lambda pixel: 255 if pixel > 170 else 0)


def _tesseract_image_to_string(pytesseract_module, image, *, psm: int) -> str:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8") as user_words:
        user_words.write("\n".join(OCR_GUIDE_WORDS))
        user_words.flush()
        config = f"--oem 3 --psm {psm} --user-words {user_words.name}"
        return pytesseract_module.image_to_string(image, lang="spa+eng", config=config)
