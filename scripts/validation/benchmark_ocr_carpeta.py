"""Benchmark OCR de laboratorio sobre una carpeta de PDFs (o imagenes) con ground truth anotado a mano.

Uso tipico (plan de fiabilidad, Fase 6: >=50 PDFs reales anonimizados):

    # 1) Plantilla para anotar (una fila por archivo; --prefill agrega lo que detecta el OCR para corregir)
    python scripts/validation/benchmark_ocr_carpeta.py --input-dir /ruta/pdfs --write-template gt.csv --prefill

    # 2) Una persona revisa cada PDF, corrige/agrega filas y marca verificado=si
    # 3) Benchmark
    python scripts/validation/benchmark_ocr_carpeta.py --input-dir /ruta/pdfs --ground-truth gt.csv

Ground truth (CSV, una fila por biomarcador esperado):
    file_name,code,value,unit,verificado,nota
    lab_001.pdf,vitamin_d,18.3,ng/mL,si,
    lab_002.pdf,,,,si,sin biomarcadores reconocibles   <- archivo sin resultados (negativo)

`value` y `unit` son los que aparecen IMPRESOS en el informe (antes de conversion); el harness los compara
con `original_value`/`original_unit` del parser. Solo cuentan filas con verificado=si.

Metricas (micro, sobre todos los archivos anotados) a tres niveles:
    code             biomarcador detectado
    code_value       + valor dentro de tolerancia (1 % o 0.02)
    code_value_unit  + unidad igual (normalizada) — es la metrica que pide el plan
Precision = aciertos / biomarcadores extraidos; recall = aciertos / biomarcadores esperados.

Los reportes no guardan texto OCR (puede contener PII); con --hash-file-names tampoco nombres de archivo.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import HTTPException

from app.domains.labs.biomarcadores import BIOMARKERS, normalize_unit_key
from app.domains.labs.servicio_analisis_examenes import (
    extract_text_from_upload,
    normalize_biomarker_code,
    parse_lab_text,
)

REPORT_DIR = ROOT / "data/reports/labs/ocr_benchmark"
SUPPORTED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tiff", ".txt"}
MIME_BY_SUFFIX = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".tiff": "image/tiff",
    ".txt": "text/plain",
}
LEVELS = ("code", "code_value", "code_value_unit")
TEMPLATE_FIELDS = ["file_name", "code", "value", "unit", "verificado", "nota", "ocr_confidence"]


def _parse_float(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def value_matches(predicted: float, expected: float) -> bool:
    return abs(predicted - expected) <= max(0.02, abs(expected) * 0.01)


def list_input_files(input_dir: Path) -> list[Path]:
    return sorted(
        path for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )


def extract_biomarkers(path: Path) -> dict[str, Any]:
    """Corre el mismo camino que `/labs/upload`: extraccion de texto + parser. No devuelve el texto."""
    try:
        text, source_type, engine = extract_text_from_upload(
            path.read_bytes(),
            file_name=path.name,
            mime_type=MIME_BY_SUFFIX.get(path.suffix.lower(), "application/octet-stream"),
        )
    except HTTPException as exc:
        return {"ok": False, "error": str(exc.detail), "engine": "", "source_type": "", "biomarkers": []}
    parsed = parse_lab_text(text)
    return {
        "ok": True,
        "error": "",
        "engine": engine or "",
        "source_type": source_type,
        "text_length": len(text),
        "biomarkers": [
            {
                "code": item["code"],
                "value": float(item["original_value"]),
                "unit": item.get("original_unit") or "",
                "confidence": item.get("confidence"),
            }
            for item in parsed
        ],
    }


def load_ground_truth(path: Path) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """Agrupa filas verificadas por archivo. Devuelve (gt, problemas). Un archivo con solo filas sin code es negativo."""
    truth: dict[str, list[dict[str, Any]]] = {}
    problems: list[str] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for line_no, row in enumerate(csv.DictReader(handle), start=2):
            file_name = (row.get("file_name") or "").strip()
            if not file_name:
                problems.append(f"linea {line_no}: file_name vacio")
                continue
            if (row.get("verificado") or "").strip().lower() not in {"si", "sí", "yes", "true", "1"}:
                continue
            entries = truth.setdefault(file_name, [])
            raw_code = (row.get("code") or "").strip()
            if not raw_code:
                continue
            code = normalize_biomarker_code(raw_code)
            if code not in BIOMARKERS:
                problems.append(f"linea {line_no}: code desconocido '{raw_code}'")
                continue
            value = _parse_float(row.get("value"))
            if value is None:
                problems.append(f"linea {line_no}: value no numerico para {code}")
                continue
            entries.append({"code": code, "value": value, "unit": (row.get("unit") or "").strip()})
    return truth, problems


def match_file(expected: list[dict[str, Any]], predicted: list[dict[str, Any]]) -> dict[str, Any]:
    """Empareja por codigo (1 a 1, el parser emite un valor por codigo) y cuenta aciertos por nivel."""
    hits = {level: 0 for level in LEVELS}
    per_code: list[dict[str, Any]] = []
    predicted_by_code: dict[str, dict[str, Any]] = {}
    for item in predicted:
        predicted_by_code.setdefault(item["code"], item)
    expected_codes = set()
    for exp in expected:
        expected_codes.add(exp["code"])
        pred = predicted_by_code.get(exp["code"])
        code_ok = pred is not None
        value_ok = code_ok and value_matches(pred["value"], exp["value"])
        unit_ok = value_ok and normalize_unit_key(pred["unit"]) == normalize_unit_key(exp["unit"])
        hits["code"] += code_ok
        hits["code_value"] += value_ok
        hits["code_value_unit"] += unit_ok
        per_code.append({
            "code": exp["code"],
            "expected_value": exp["value"],
            "expected_unit": exp["unit"],
            "predicted_value": pred["value"] if pred else "",
            "predicted_unit": pred["unit"] if pred else "",
            "outcome": "ok" if unit_ok else ("unit_mismatch" if value_ok else ("value_mismatch" if code_ok else "missed")),
        })
    for code, pred in predicted_by_code.items():
        if code not in expected_codes:
            per_code.append({
                "code": code,
                "expected_value": "",
                "expected_unit": "",
                "predicted_value": pred["value"],
                "predicted_unit": pred["unit"],
                "outcome": "false_positive",
            })
    return {"hits": hits, "expected": len(expected_codes), "predicted": len(predicted_by_code), "per_code": per_code}


def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def _display_name(file_name: str, hash_names: bool) -> str:
    return hashlib.sha256(file_name.encode("utf-8")).hexdigest()[:12] if hash_names else file_name


def run_benchmark(
    input_dir: Path,
    truth: dict[str, list[dict[str, Any]]],
    *,
    hash_names: bool = False,
    extractor=extract_biomarkers,
) -> dict[str, Any]:
    files = {path.name: path for path in list_input_files(input_dir)}
    missing_files = sorted(set(truth) - set(files))
    unannotated = sorted(set(files) - set(truth))

    totals = {"expected": 0, "predicted": 0, **{level: 0 for level in LEVELS}}
    by_code: dict[str, dict[str, int]] = defaultdict(lambda: {"expected": 0, "predicted": 0, **{level: 0 for level in LEVELS}})
    file_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []
    extraction_errors = 0

    for file_name in sorted(set(truth) & set(files)):
        extraction = extractor(files[file_name])
        if not extraction["ok"]:
            extraction_errors += 1
        result = match_file(truth[file_name], extraction["biomarkers"])
        shown = _display_name(file_name, hash_names)
        totals["expected"] += result["expected"]
        totals["predicted"] += result["predicted"]
        for level in LEVELS:
            totals[level] += result["hits"][level]
        for row in result["per_code"]:
            stats = by_code[row["code"]]
            if row["outcome"] != "false_positive":
                stats["expected"] += 1
            if row["predicted_value"] != "":
                stats["predicted"] += 1
            stats["code"] += row["outcome"] in {"ok", "unit_mismatch", "value_mismatch"}
            stats["code_value"] += row["outcome"] in {"ok", "unit_mismatch"}
            stats["code_value_unit"] += row["outcome"] == "ok"
            detail_rows.append({"file": shown, **row})
        file_rows.append({
            "file": shown,
            "engine": extraction["engine"],
            "extraction_ok": extraction["ok"],
            "error": extraction["error"],
            "expected": result["expected"],
            "predicted": result["predicted"],
            **{f"hits_{level}": result["hits"][level] for level in LEVELS},
        })

    metrics = {
        level: {
            "precision": _ratio(totals[level], totals["predicted"]),
            "recall": _ratio(totals[level], totals["expected"]),
        }
        for level in LEVELS
    }
    code_rows = [
        {
            "code": code,
            "expected": stats["expected"],
            "predicted": stats["predicted"],
            **{f"precision_{level}": _ratio(stats[level], stats["predicted"]) for level in LEVELS},
            **{f"recall_{level}": _ratio(stats[level], stats["expected"]) for level in LEVELS},
        }
        for code, stats in sorted(by_code.items())
    ]
    return {
        "files_annotated": len(file_rows),
        "files_in_dir": len(files),
        "files_unannotated": [_display_name(name, hash_names) for name in unannotated],
        "ground_truth_files_missing": missing_files,
        "extraction_errors": extraction_errors,
        "expected_biomarkers": totals["expected"],
        "predicted_biomarkers": totals["predicted"],
        "metrics": metrics,
        "file_rows": file_rows,
        "detail_rows": detail_rows,
        "code_rows": code_rows,
    }


def write_template(input_dir: Path, out_path: Path, *, prefill: bool, extractor=extract_biomarkers) -> int:
    rows: list[dict[str, Any]] = []
    for path in list_input_files(input_dir):
        detected = extractor(path)["biomarkers"] if prefill else []
        if not detected:
            rows.append({"file_name": path.name, "verificado": "no"})
            continue
        for item in detected:
            rows.append({
                "file_name": path.name,
                "code": item["code"],
                "value": item["value"],
                "unit": item["unit"],
                "verificado": "no",
                "nota": "prellenado por OCR: corregir y agregar los que falten",
                "ocr_confidence": item["confidence"],
            })
    _write_csv(out_path, rows, TEMPLATE_FIELDS)
    return len(rows)


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = fieldnames or (list(rows[0].keys()) if rows else ["empty"])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark OCR de laboratorio sobre una carpeta de PDFs con ground truth.")
    parser.add_argument("--input-dir", type=Path, required=True, help="Carpeta con PDFs/imagenes (no recursivo).")
    parser.add_argument("--ground-truth", type=Path, help="CSV file_name,code,value,unit,verificado.")
    parser.add_argument("--write-template", type=Path, help="Escribe una plantilla de ground truth y termina.")
    parser.add_argument("--prefill", action="store_true", help="Con --write-template, prellena con lo que detecta el OCR.")
    parser.add_argument("--out-dir", type=Path, default=REPORT_DIR)
    parser.add_argument("--hash-file-names", action="store_true", help="Reemplaza nombres de archivo por sha256[:12] en reportes.")
    parser.add_argument("--min-files", type=int, default=50, help="Muestra minima para dar el benchmark por valido (plan: 50).")
    parser.add_argument("--min-precision", type=float, default=None, help="Umbral opcional de precision code_value_unit.")
    parser.add_argument("--min-recall", type=float, default=None, help="Umbral opcional de recall code_value_unit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.input_dir.is_dir():
        print(f"No existe la carpeta {args.input_dir}", file=sys.stderr)
        return 2

    if args.write_template:
        count = write_template(args.input_dir, args.write_template, prefill=args.prefill)
        print(f"Plantilla con {count} filas en {args.write_template}. Revisar cada PDF y marcar verificado=si.")
        return 0

    if not args.ground_truth:
        print("Falta --ground-truth (o usar --write-template para generarlo).", file=sys.stderr)
        return 2

    truth, problems = load_ground_truth(args.ground_truth)
    result = run_benchmark(args.input_dir, truth, hash_names=args.hash_file_names)

    errors = [*problems]
    if result["ground_truth_files_missing"]:
        errors.append(f"ground_truth_sin_archivo={len(result['ground_truth_files_missing'])}")
    headline = result["metrics"]["code_value_unit"]
    if args.min_precision is not None and (headline["precision"] or 0) < args.min_precision:
        errors.append(f"precision_below_threshold={headline['precision']}<{args.min_precision}")
    if args.min_recall is not None and (headline["recall"] or 0) < args.min_recall:
        errors.append(f"recall_below_threshold={headline['recall']}<{args.min_recall}")

    if errors:
        status = "failed"
    elif result["files_annotated"] < args.min_files:
        status = "insufficient_sample"
    else:
        status = "passed"

    out_dir = args.out_dir
    _write_csv(out_dir / "ocr_benchmark_files.csv", result["file_rows"])
    _write_csv(out_dir / "ocr_benchmark_details.csv", result["detail_rows"])
    _write_csv(out_dir / "ocr_benchmark_by_code.csv", result["code_rows"])
    summary = {
        "status": status,
        "errors": errors,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_dir_sha256_12": hashlib.sha256(str(args.input_dir.resolve()).encode()).hexdigest()[:12],
        "min_files": args.min_files,
        **{key: value for key, value in result.items() if key not in {"file_rows", "detail_rows", "code_rows"}},
    }
    (out_dir / "ocr_benchmark_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("status", "errors", "files_annotated", "extraction_errors", "metrics")}, ensure_ascii=False, indent=2))
    return 1 if status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
