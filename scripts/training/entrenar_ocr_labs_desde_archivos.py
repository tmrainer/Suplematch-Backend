from __future__ import annotations

import argparse
import csv
import io
import json
import mimetypes
import re
import shutil
import sys
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import HTTPException

from app.domains.labs.biomarcadores import BIOMARKERS
from app.domains.labs.servicio_analisis_examenes import (
    analyze_biomarkers,
    extract_text_from_upload,
    parse_lab_text,
)


REPORT_DIR = ROOT / "data/reports/labs"
PROJECT_ROOT = ROOT.parent


def _clean_float(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", ".")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _expected_code_for_name(name: str) -> str | None:
    name_key = _key(name)
    if not name_key:
        return None
    name_tokens = set(name_key.split())
    matches: list[tuple[int, str]] = []
    for code, definition in BIOMARKERS.items():
        for alias in definition.aliases:
            alias_key = _key(alias)
            if not alias_key:
                continue
            if len(alias_key) <= 3:
                if alias_key in name_tokens:
                    matches.append((len(alias_key), code))
                continue
            if alias_key in name_key:
                matches.append((len(alias_key), code))
    if not matches:
        return None
    return sorted(matches, reverse=True)[0][1]


def _value_matches(parsed_value: float, expected_value: float) -> bool:
    tolerance = max(0.02, abs(expected_value) * 0.01)
    return abs(parsed_value - expected_value) <= tolerance


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not fieldnames:
        fieldnames = list(rows[0].keys()) if rows else ["empty"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_zip_csv_cases(zip_path: Path, *, max_cases: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not zip_path.exists():
        return rows

    with zipfile.ZipFile(zip_path) as archive:
        csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        for csv_name in csv_names:
            with archive.open(csv_name) as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8", errors="ignore")
                reader = csv.DictReader(text)
                for row in reader:
                    test_name = row.get("Test_Name") or row.get("test_name") or ""
                    expected_code = _expected_code_for_name(test_name)
                    expected_value = _clean_float(row.get("Result"))
                    if expected_code is None or expected_value is None:
                        continue

                    line = " ".join(
                        str(row.get(key) or "")
                        for key in ("Test_Name", "Result", "Unit", "Reference_Range")
                    ).strip()
                    parsed = parse_lab_text(line)
                    by_code = {item["code"]: item for item in parsed}
                    parsed_item = by_code.get(expected_code)
                    matched = parsed_item is not None and _value_matches(float(parsed_item["value"]), expected_value)
                    rows.append(
                        {
                            "source_zip": zip_path.name,
                            "source_file": csv_name,
                            "test_name": test_name,
                            "expected_code": expected_code,
                            "expected_value": expected_value,
                            "expected_unit": row.get("Unit") or "",
                            "detected": bool(parsed_item),
                            "detected_value": parsed_item["value"] if parsed_item else "",
                            "detected_unit": parsed_item["unit"] if parsed_item else "",
                            "value_match": matched,
                            "status": parsed_item["status"] if parsed_item else "",
                            "confidence": parsed_item["confidence"] if parsed_item else "",
                            "detected_codes": "|".join(sorted(by_code)),
                        }
                    )
                    if len(rows) >= max_cases:
                        return rows
    return rows


def _evaluate_pdf_files(project_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pdf_path in sorted(project_root.glob("*.pdf")):
        try:
            text, source_type, engine = extract_text_from_upload(
                pdf_path.read_bytes(),
                file_name=pdf_path.name,
                mime_type="application/pdf",
            )
            parsed = parse_lab_text(text)
            analysis = analyze_biomarkers(parsed)
            rows.append(
                {
                    "file_name": pdf_path.name,
                    "source_type": source_type,
                    "engine": engine or "",
                    "text_length": len(text),
                    "biomarker_count": len(parsed),
                    "biomarkers": "|".join(f"{item['code']}={item['value']} {item['unit']}" for item in parsed),
                    "statuses": "|".join(f"{item['code']}:{item['status']}" for item in parsed),
                    "avg_confidence": round(mean(float(item.get("confidence") or 0) for item in parsed), 4) if parsed else 0,
                    "safety_level": analysis["safety_level"],
                    "commercial_blocked": analysis["commercial_recommendations_blocked"],
                    "evaluated": True,
                    "warnings_count": len(analysis["warnings"]),
                    "error": "",
                }
            )
        except HTTPException as exc:
            rows.append(
                {
                    "file_name": pdf_path.name,
                    "source_type": "",
                    "engine": "",
                    "text_length": 0,
                    "biomarker_count": 0,
                    "biomarkers": "",
                    "statuses": "",
                    "avg_confidence": 0,
                    "safety_level": "",
                    "commercial_blocked": "",
                    "evaluated": False,
                    "warnings_count": 0,
                    "error": str(exc.detail),
                }
            )
    return rows


def _evaluate_negative_zip(zip_path: Path, *, max_images: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if max_images <= 0 or not zip_path.exists():
        return rows

    with zipfile.ZipFile(zip_path) as archive:
        names = [
            name for name in archive.namelist()
            if name.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".tiff"))
        ][:max_images]
        for name in names:
            try:
                content = archive.read(name)
                mime_type = mimetypes.guess_type(name)[0] or "image/jpeg"
                text, source_type, engine = extract_text_from_upload(content, file_name=Path(name).name, mime_type=mime_type)
                parsed = parse_lab_text(text)
                rows.append(
                    {
                        "source_zip": zip_path.name,
                        "source_file": name,
                        "source_type": source_type,
                        "engine": engine or "",
                        "text_length": len(text),
                        "detected_biomarker_count": len(parsed),
                        "detected_codes": "|".join(sorted({item["code"] for item in parsed})),
                        "expected_negative_ok": len(parsed) == 0,
                        "evaluated": True,
                        "error": "",
                    }
                )
            except HTTPException as exc:
                rows.append(
                    {
                        "source_zip": zip_path.name,
                        "source_file": name,
                        "source_type": "",
                        "engine": "",
                        "text_length": 0,
                        "detected_biomarker_count": 0,
                        "detected_codes": "",
                        "expected_negative_ok": "",
                        "evaluated": False,
                        "error": str(exc.detail),
                    }
                )
    return rows


def _summarize(csv_cases: list[dict[str, Any]], pdf_rows: list[dict[str, Any]], negative_rows: list[dict[str, Any]]) -> dict[str, Any]:
    supported_cases = len(csv_cases)
    detected_cases = sum(1 for row in csv_cases if row["detected"])
    value_matches = sum(1 for row in csv_cases if row["value_match"])
    negative_evaluated = [row for row in negative_rows if row["evaluated"]]
    negative_ok = sum(1 for row in negative_evaluated if row["expected_negative_ok"])
    pdf_ok = [row for row in pdf_rows if row["evaluated"]]
    skipped = [row for row in [*pdf_rows, *negative_rows] if not row["evaluated"]]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "completed_with_skips" if skipped else "completed",
        "tesseract_available": shutil.which("tesseract") is not None,
        "supported_csv_cases": supported_cases,
        "csv_detection_rate": round(detected_cases / max(supported_cases, 1), 4),
        "csv_value_match_rate": round(value_matches / max(supported_cases, 1), 4),
        "pdf_files": len(pdf_rows),
        "pdf_files_read": len(pdf_ok),
        "pdf_files_skipped": len(pdf_rows) - len(pdf_ok),
        "pdf_detected_biomarkers": sum(int(row["biomarker_count"]) for row in pdf_ok),
        "negative_images": len(negative_rows),
        "negative_images_evaluated": len(negative_evaluated),
        "negative_images_skipped": len(negative_rows) - len(negative_evaluated),
        "negative_precision_rate": round(negative_ok / max(len(negative_evaluated), 1), 4) if negative_evaluated else None,
        "skip_reasons": sorted({str(row["error"]) for row in skipped if row["error"]}),
        "csv_cases_by_code": {
            code: {
                "cases": sum(1 for row in csv_cases if row["expected_code"] == code),
                "detected": sum(1 for row in csv_cases if row["expected_code"] == code and row["detected"]),
                "value_matches": sum(1 for row in csv_cases if row["expected_code"] == code and row["value_match"]),
            }
            for code in sorted({str(row["expected_code"]) for row in csv_cases})
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Construye benchmark/calibración OCR con PDFs y ZIPs subidos al proyecto."
    )
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--reports-dir", type=Path, default=REPORT_DIR)
    parser.add_argument("--lab-csv-zip", type=Path, default=PROJECT_ROOT / "archive(1).zip")
    parser.add_argument("--negative-zip", type=Path, default=PROJECT_ROOT / "archive.zip")
    parser.add_argument("--max-csv-cases", type=int, default=500)
    parser.add_argument("--max-negative-images", type=int, default=8)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    csv_cases = _read_zip_csv_cases(args.lab_csv_zip, max_cases=args.max_csv_cases)
    pdf_rows = _evaluate_pdf_files(args.project_root)
    negative_rows = _evaluate_negative_zip(args.negative_zip, max_images=args.max_negative_images)

    csv_path = args.reports_dir / "02_uploaded_ocr_lab_csv_cases.csv"
    pdf_path = args.reports_dir / "02_uploaded_ocr_file_report.csv"
    negative_path = args.reports_dir / "02_uploaded_ocr_negative_cases.csv"
    summary_path = args.reports_dir / "02_uploaded_ocr_summary.json"

    _write_csv(
        csv_path,
        csv_cases,
        [
            "source_zip", "source_file", "test_name", "expected_code", "expected_value",
            "expected_unit", "detected", "detected_value", "detected_unit", "value_match",
            "status", "confidence", "detected_codes",
        ],
    )
    _write_csv(
        pdf_path,
        pdf_rows,
        [
            "file_name", "source_type", "engine", "text_length", "biomarker_count",
            "biomarkers", "statuses", "avg_confidence", "safety_level",
            "commercial_blocked", "evaluated", "warnings_count", "error",
        ],
    )
    _write_csv(
        negative_path,
        negative_rows,
        [
            "source_zip", "source_file", "source_type", "engine", "text_length",
            "detected_biomarker_count", "detected_codes", "expected_negative_ok",
            "evaluated", "error",
        ],
    )
    summary = _summarize(csv_cases, pdf_rows, negative_rows)
    summary.update(
        {
            "csv_report": str(csv_path),
            "pdf_report": str(pdf_path),
            "negative_report": str(negative_path),
            "summary_report": str(summary_path),
        }
    )
    _write_json(summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
