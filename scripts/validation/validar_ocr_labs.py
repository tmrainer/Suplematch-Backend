from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean
from typing import Any

from app.core.config import BASE_DIR
from app.domains.labs.servicio_analisis_examenes import analyze_biomarkers, parse_lab_text


REPORT_DIR = BASE_DIR / "data/reports/labs"


OCR_CASES: list[dict[str, Any]] = [
    {
        "case_id": "roe_table_common_deficiencies",
        "source_kind": "text_pdf",
        "expected_codes": ["vitamin_d", "ferritin", "hemoglobin", "creatinine", "tsh"],
        "critical_expected": [],
        "text": """
EXAMEN                          RESULTADO    UNIDAD    VALORES DE REFERENCIA
Glucosa en Ayunas               95           mg/dL     70 - 100
Hemoglobina                     11.8         g/dL      12.0 - 16.0
Ferritina Serica                14           ng/mL     13 - 150
Vitamina D 25-OH                18.3         ng/mL     30 - 100
Creatinina Serica               0.89         mg/dL     0.57 - 1.11
TSH                             0.32         mUI/L     0.4 - 4.0
""",
    },
    {
        "case_id": "suiza_lipid_metabolic_panel",
        "source_kind": "text_pdf",
        "expected_codes": ["glucose", "triglycerides", "total_cholesterol", "hdl", "ldl", "crp"],
        "critical_expected": [],
        "text": """
ANALISIS                  RESULTADO   U.M.    VN
GLUCOSA                   89.5        mg/dL   74 - 106
TRIGLICERIDOS             185         mg/dL   < 150
COLESTEROL TOTAL          215         mg/dL   < 200
COLESTEROL HDL            38          mg/dL   > 40
COLESTEROL LDL            140         mg/dL   < 130
PROTEINA C REACTIVA       6.5         mg/L    < 3.0
""",
    },
    {
        "case_id": "hospital_dotted_liver_iron",
        "source_kind": "ocr_image_like",
        "expected_codes": ["ast", "alt", "vitamin_d", "ferritin", "iron", "folate"],
        "critical_expected": [],
        "text": """
T.G.O.          38     U/L     Hasta 40
T.G.P.          52     U/L     Hasta 40
Vit. D          12,5   ng/mL   30 - 100
Ferritina Sr.   18     ng/mL   13 - 150
Hierro Serico   45     ug/dL   60 - 170
Folato Serico   2.1    ng/mL   3.0 - 20.0
""",
    },
    {
        "case_id": "renal_safety_panel",
        "source_kind": "text_pdf",
        "expected_codes": ["creatinine", "egfr", "potassium", "calcium"],
        "critical_expected": ["egfr"],
        "text": """
Creatinina sérica        1.9 mg/dL      0.6 - 1.3
TFG estimada             52 mL/min/1.73m2  > 90
Potasio                  5.4 mmol/L     3.5 - 5.1
Calcio sérico            10.0 mg/dL     8.6 - 10.2
""",
    },
    {
        "case_id": "noisy_photo_multiline",
        "source_kind": "ocr_image_like",
        "expected_codes": ["vitamin_d", "b12", "magnesium", "zinc"],
        "critical_expected": [],
        "text": """
RESULTADOS DE LABORATORIO
Vitamina D 25 OH
19 ng / ml   referencia 30 - 100
VIT. B12
185 pg/ml VR 200 - 900
Magnesio sérico   1,6   mg / dL   1.7 - 2.4
Zinc sérico 66 ug/dL valores normales 70 - 120
""",
    },
]


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    parsed = parse_lab_text(case["text"])
    analysis = analyze_biomarkers(parsed)
    by_code = {item["code"]: item for item in parsed}
    expected = set(case["expected_codes"])
    critical_expected = set(case.get("critical_expected") or [])
    detected = set(by_code)
    missing = sorted(expected - detected)
    extra = sorted(detected - expected)
    critical_detected = {
        code for code, item in by_code.items()
        if item.get("severity") == "critical"
    }

    return {
        "case_id": case["case_id"],
        "source_kind": case["source_kind"],
        "expected_count": len(expected),
        "detected_expected_count": len(expected.intersection(detected)),
        "detected_total": len(detected),
        "recall": round(len(expected.intersection(detected)) / max(len(expected), 1), 4),
        "missing_codes": "|".join(missing),
        "extra_codes": "|".join(extra),
        "critical_expected": "|".join(sorted(critical_expected)),
        "critical_detected": "|".join(sorted(critical_detected)),
        "critical_ok": critical_expected.issubset(critical_detected),
        "avg_confidence": round(mean(float(item.get("confidence") or 0) for item in parsed), 4) if parsed else 0,
        "safety_level": analysis["safety_level"],
        "commercial_blocked": analysis["commercial_recommendations_blocked"],
        "warnings_count": len(analysis["warnings"]),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def build_analyte_rows(details: list[dict[str, Any]], cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_case = {case["case_id"]: case for case in cases}
    rows: dict[str, dict[str, Any]] = {}
    for detail in details:
        case = by_case[detail["case_id"]]
        expected = set(case["expected_codes"])
        missing = set(filter(None, str(detail["missing_codes"] or "").split("|")))
        for code in expected:
            row = rows.setdefault(code, {
                "code": code,
                "expected_cases": 0,
                "detected_cases": 0,
                "missing_cases": [],
            })
            row["expected_cases"] += 1
            if code not in missing:
                row["detected_cases"] += 1
            else:
                row["missing_cases"].append(detail["case_id"])

    final_rows = []
    for code, row in sorted(rows.items()):
        final_rows.append({
            "code": code,
            "expected_cases": row["expected_cases"],
            "detected_cases": row["detected_cases"],
            "recall": round(row["detected_cases"] / max(row["expected_cases"], 1), 4),
            "missing_cases": "|".join(row["missing_cases"]),
        })
    return final_rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evalúa parser OCR/labs con formatos peruanos representativos.")
    parser.add_argument("--details-out", type=Path, default=REPORT_DIR / "01_ocr_lab_case_details.csv")
    parser.add_argument("--analytes-out", type=Path, default=REPORT_DIR / "01_ocr_lab_analyte_details.csv")
    parser.add_argument("--summary-out", type=Path, default=REPORT_DIR / "01_ocr_lab_summary.json")
    parser.add_argument("--min-recall", type=float, default=0.90)
    parser.add_argument("--min-analyte-recall", type=float, default=0.80)
    parser.add_argument("--min-critical-accuracy", type=float, default=1.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    details = [evaluate_case(case) for case in OCR_CASES]
    analyte_rows = build_analyte_rows(details, OCR_CASES)
    recall = mean(row["recall"] for row in details)
    analyte_recall = mean(row["recall"] for row in analyte_rows)
    critical_cases = [row for row in details if row["critical_expected"]]
    critical_accuracy = mean(row["critical_ok"] for row in critical_cases) if critical_cases else 1.0
    errors = []
    if recall < args.min_recall:
        errors.append(f"recall_below_threshold={recall:.4f}<{args.min_recall}")
    if analyte_recall < args.min_analyte_recall:
        errors.append(f"analyte_recall_below_threshold={analyte_recall:.4f}<{args.min_analyte_recall}")
    if critical_accuracy < args.min_critical_accuracy:
        errors.append(f"critical_accuracy_below_threshold={critical_accuracy:.4f}<{args.min_critical_accuracy}")

    summary = {
        "status": "failed" if errors else "passed",
        "errors": errors,
        "cases": len(details),
        "recall": round(recall, 4),
        "analytes": len(analyte_rows),
        "analyte_recall": round(analyte_recall, 4),
        "analyte_recall_by_code": {row["code"]: row["recall"] for row in analyte_rows},
        "critical_accuracy": round(critical_accuracy, 4),
        "avg_confidence": round(mean(row["avg_confidence"] for row in details), 4),
        "details_path": str(args.details_out),
        "analytes_path": str(args.analytes_out),
        "summary_path": str(args.summary_out),
    }
    write_csv(args.details_out, details)
    write_csv(args.analytes_out, analyte_rows)
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
