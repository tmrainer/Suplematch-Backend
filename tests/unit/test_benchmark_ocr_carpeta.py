"""Harness de benchmark OCR por carpeta: matching por nivel, ground truth verificado y plantilla."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

bench = pytest.importorskip("scripts.validation.benchmark_ocr_carpeta")

LAB_A = """
EXAMEN                          RESULTADO    UNIDAD    VALORES DE REFERENCIA
Hemoglobina                     11.8         g/dL      12.0 - 16.0
Vitamina D 25-OH                18.3         ng/mL     30 - 100
TSH                             0.32         mUI/L     0.4 - 4.0
"""
LAB_B = """
Ferritina Serica                14           ng/mL     13 - 150
"""


def _write_gt(path: Path, rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["file_name", "code", "value", "unit", "verificado", "nota"])
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.fixture()
def lab_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "pdfs"
    folder.mkdir()
    (folder / "lab_a.txt").write_text(LAB_A, encoding="utf-8")
    (folder / "lab_b.txt").write_text(LAB_B, encoding="utf-8")
    (folder / "ignorar.docx").write_text("no soportado", encoding="utf-8")
    return folder


def test_match_file_levels() -> None:
    expected = [
        {"code": "vitamin_d", "value": 18.3, "unit": "ng/mL"},
        {"code": "ferritin", "value": 14.0, "unit": "ng/mL"},
        {"code": "tsh", "value": 0.32, "unit": "mUI/L"},
        {"code": "b12", "value": 300.0, "unit": "pg/mL"},
    ]
    predicted = [
        {"code": "vitamin_d", "value": 18.3, "unit": "ng / mL"},  # ok (unidad normalizada)
        {"code": "ferritin", "value": 41.0, "unit": "ng/mL"},     # valor mal
        {"code": "tsh", "value": 0.32, "unit": "ng/mL"},          # unidad mal
        {"code": "glucose", "value": 95.0, "unit": "mg/dL"},      # falso positivo
    ]
    result = bench.match_file(expected, predicted)
    assert result["hits"] == {"code": 3, "code_value": 2, "code_value_unit": 1}
    assert result["expected"] == 4 and result["predicted"] == 4
    outcomes = {row["code"]: row["outcome"] for row in result["per_code"]}
    assert outcomes == {
        "vitamin_d": "ok", "ferritin": "value_mismatch", "tsh": "unit_mismatch",
        "b12": "missed", "glucose": "false_positive",
    }


def test_ground_truth_only_counts_verified_rows(tmp_path: Path) -> None:
    gt = _write_gt(tmp_path / "gt.csv", [
        {"file_name": "a.pdf", "code": "vitamin_d", "value": "18,3", "unit": "ng/mL", "verificado": "si"},
        {"file_name": "a.pdf", "code": "tsh", "value": "0.3", "unit": "mUI/L", "verificado": "no"},
        {"file_name": "b.pdf", "code": "", "value": "", "unit": "", "verificado": "si", "nota": "negativo"},
        {"file_name": "c.pdf", "code": "unobtainium", "value": "1", "unit": "", "verificado": "si"},
    ])
    truth, problems = bench.load_ground_truth(gt)
    assert truth["a.pdf"] == [{"code": "vitamin_d", "value": 18.3, "unit": "ng/mL"}]
    assert truth["b.pdf"] == []
    assert any("unobtainium" in problem for problem in problems)


def test_end_to_end_on_folder(lab_dir: Path, tmp_path: Path) -> None:
    gt = _write_gt(tmp_path / "gt.csv", [
        {"file_name": "lab_a.txt", "code": "hemoglobin", "value": "11.8", "unit": "g/dL", "verificado": "si"},
        {"file_name": "lab_a.txt", "code": "vitamin_d", "value": "18.3", "unit": "ng/mL", "verificado": "si"},
        {"file_name": "lab_a.txt", "code": "tsh", "value": "0.32", "unit": "mUI/L", "verificado": "si"},
        {"file_name": "lab_b.txt", "code": "ferritin", "value": "14", "unit": "ng/mL", "verificado": "si"},
    ])
    out_dir = tmp_path / "out"
    code = bench.main([
        "--input-dir", str(lab_dir), "--ground-truth", str(gt), "--out-dir", str(out_dir),
        "--min-files", "2", "--hash-file-names",
    ])
    summary = json.loads((out_dir / "ocr_benchmark_summary.json").read_text(encoding="utf-8"))
    assert code == 0
    assert summary["status"] == "passed"
    assert summary["files_annotated"] == 2
    assert summary["metrics"]["code_value_unit"] == {"precision": 1.0, "recall": 1.0}
    details = (out_dir / "ocr_benchmark_details.csv").read_text(encoding="utf-8")
    assert "lab_a.txt" not in details  # nombres hasheados


def test_small_sample_is_flagged(lab_dir: Path, tmp_path: Path) -> None:
    gt = _write_gt(tmp_path / "gt.csv", [
        {"file_name": "lab_b.txt", "code": "ferritin", "value": "14", "unit": "ng/mL", "verificado": "si"},
    ])
    out_dir = tmp_path / "out"
    assert bench.main(["--input-dir", str(lab_dir), "--ground-truth", str(gt), "--out-dir", str(out_dir)]) == 0
    summary = json.loads((out_dir / "ocr_benchmark_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "insufficient_sample"
    assert summary["files_unannotated"] == ["lab_a.txt"]


def test_ground_truth_for_missing_file_fails(lab_dir: Path, tmp_path: Path) -> None:
    gt = _write_gt(tmp_path / "gt.csv", [
        {"file_name": "no_existe.pdf", "code": "ferritin", "value": "14", "unit": "ng/mL", "verificado": "si"},
    ])
    assert bench.main(["--input-dir", str(lab_dir), "--ground-truth", str(gt), "--out-dir", str(tmp_path / "o")]) == 1


def test_template_prefill_requires_verification(lab_dir: Path, tmp_path: Path) -> None:
    template = tmp_path / "tpl.csv"
    assert bench.main(["--input-dir", str(lab_dir), "--write-template", str(template), "--prefill"]) == 0
    with template.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["file_name"] for row in rows} == {"lab_a.txt", "lab_b.txt"}
    assert {row["verificado"] for row in rows} == {"no"}
    assert {"hemoglobin", "vitamin_d", "tsh", "ferritin"} <= {row["code"] for row in rows}
    # Una plantilla sin revisar no aporta ground truth.
    truth, _ = bench.load_ground_truth(template)
    assert truth == {}
