"""Paquete de revision clinica: generacion (casos estratificados, hojas de reglas, firma) e importacion."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")
gen = pytest.importorskip("scripts.clinical.generar_paquete_revision")
imp = pytest.importorskip("scripts.clinical.importar_revision")


def _fake_recommend(payload: dict) -> dict:
    blocked = bool(payload.get("condiciones_seguridad"))
    return {
        "conditions_display": [{"code": "DEFICIT_VIT_D", "display_name": "Riesgo de vitamina D baja", "risk_index": 0.8}],
        "lab_risk_estimates": [],
        "safety_level": "medical_review_required" if blocked else "normal",
        "commercial_recommendations_blocked": blocked,
        "profile_warnings": [],
        "safety_actions": [],
        "alertas": [],
        "recommendations": [
            {"display_name": f"Comp {i}", "component_id": f"C{i}", "recommendation_role": "primary",
             "evidence_grade": "high", "commercial_eligible": not blocked}
            for i in range(12)
        ],
    }


def test_case_payloads_meet_quotas_and_validate() -> None:
    from app.domains.survey.esquemas_encuesta import EncuestaInput

    cases = gen.build_case_payloads(120, seed=7)
    assert len(cases) == 120 and len({case["case_id"] for case in cases}) == 120
    payloads = [case["payload"] for case in cases]
    for payload in payloads:
        EncuestaInput(**payload)
    for condition in gen.SAFETY_CONDITIONS:
        assert sum(condition in p["condiciones_seguridad"] for p in payloads) >= 4, condition
    assert all(p["sexo"] == "femenino" for p in payloads if "embarazo_lactancia" in p["condiciones_seguridad"])
    assert sum(p["age_years"] < 18 for p in payloads) >= 4
    assert sum(p["age_years"] > 60 for p in payloads) >= 8
    assert sum(bool(p.get("lab_results")) for p in payloads) >= 20
    # Determinista: la misma semilla produce el mismo paquete.
    assert gen.build_case_payloads(120, seed=7) == cases


def test_profile_description_is_readable() -> None:
    payload = gen.build_case_payloads(1, seed=1)[0]["payload"]
    text = gen.describe_profile(payload)
    assert "años" in text and "dieta" in text and "SEGURIDAD" in text


def _generate(tmp_path: Path) -> Path:
    assert gen.main(["--cases", "100", "--out-dir", str(tmp_path)], recommend=_fake_recommend) == 0
    return next(tmp_path.glob("*.xlsx"))


def test_generated_workbook_structure(tmp_path: Path) -> None:
    xlsx = _generate(tmp_path)
    book = openpyxl.load_workbook(xlsx)
    expected = {"Instrucciones", "Casos", "Recomendaciones", "Firma", "_meta", gen.INGREDIENT_SHEET}
    expected |= {sheet for sheet, _, _ in gen.RULE_SHEETS}
    assert expected <= set(book.sheetnames)
    assert book["_meta"].sheet_state == "hidden"
    casos = book["Casos"]
    assert casos.max_row == 101
    headers = [cell.value for cell in casos[1]]
    assert set(gen.CASE_REVIEW_COLUMNS) <= set(headers)
    assert casos.data_validations.dataValidation  # listas desplegables
    recs = casos.cell(row=2, column=headers.index("sistema_recomendaciones") + 1).value
    assert "y 2 más" in recs  # 12 componentes, se muestran 10
    assert book["Recomendaciones"].max_row == 100 * 12 + 1
    manifest = json.loads(next(tmp_path.glob("*.manifest.json")).read_text(encoding="utf-8"))
    assert {item["file"] for item in manifest["files"]} == set(gen.REVIEWED_FILES)


def _fill_review(xlsx: Path, *, serious_case_row: int | None = None, leave_rule_blank: bool = False) -> None:
    book = openpyxl.load_workbook(xlsx)
    casos = book["Casos"]
    headers = {cell.value: idx + 1 for idx, cell in enumerate(casos[1])}
    for row in range(2, casos.max_row + 1):
        casos.cell(row, headers["rev_condiciones"], "de_acuerdo" if row % 4 else "parcial")
        casos.cell(row, headers["rev_recomendaciones"], "de_acuerdo")
        casos.cell(row, headers["rev_seguridad"], "correcta")
        casos.cell(row, headers["rev_error_grave"], "si" if row == serious_case_row else "no")
        if row == serious_case_row:
            casos.cell(row, headers["rev_comentario"], "Hierro con anticoagulantes sin advertencia")
    first_rule_sheet = gen.RULE_SHEETS[0][0]
    for sheet in [name for name, _, _ in gen.RULE_SHEETS] + [gen.INGREDIENT_SHEET]:
        ws = book[sheet]
        cols = {cell.value: idx + 1 for idx, cell in enumerate(ws[1])}
        for row in range(2, ws.max_row + 1):
            decision = "modificar" if (sheet == first_rule_sheet and row == 2) else "aprobar"
            if leave_rule_blank and sheet == first_rule_sheet and row == 3:
                decision = None
            ws.cell(row, cols["rev_decision"], decision)
        if sheet == first_rule_sheet:
            ws.cell(2, cols["rev_cambio_propuesto"], "Bajar peso a 0.2")
    firma = book["Firma"]
    for row in range(2, 2 + len(gen.SIGNATURE_FIELDS)):
        firma.cell(row, 2, "dato")
    book.save(xlsx)


def test_import_complete_review(tmp_path: Path) -> None:
    xlsx = _generate(tmp_path)
    _fill_review(xlsx)
    result, actions = imp.import_review(xlsx)
    assert result["status"] == "completa"
    assert result["cases"]["reviewed"] == 100
    assert result["cases"]["conditions_agreement"]["parcial"] == 0.25
    assert result["cases"]["serious_errors"] == 0
    assert [a["accion"] for a in actions] == ["modificar"]
    assert actions[0]["cambio_propuesto"] == "Bajar peso a 0.2"
    assert result["plan_checkbox_ready"] is (not result["changed_files"])


def test_import_flags_serious_errors_and_gaps(tmp_path: Path) -> None:
    xlsx = _generate(tmp_path)
    _fill_review(xlsx, serious_case_row=5, leave_rule_blank=True)
    result, actions = imp.import_review(xlsx)
    assert result["status"] == "incompleta"
    assert result["plan_checkbox_ready"] is False
    assert result["cases"]["serious_errors"] == 1
    assert result["cases"]["serious_error_cases"][0]["case_id"] == "CR004"
    assert any(a["tipo"] == "caso_error_grave" for a in actions)


def test_import_detects_files_changed_since_package(tmp_path: Path) -> None:
    xlsx = _generate(tmp_path)
    _fill_review(xlsx)
    book = openpyxl.load_workbook(xlsx)
    meta = book["_meta"]
    for row in range(2, meta.max_row + 1):
        if meta.cell(row, 1).value == "files":
            files = json.loads(meta.cell(row, 2).value)
            files[0]["sha256_12"] = "000000000000"
            meta.cell(row, 2, json.dumps(files))
    book.save(xlsx)
    result, _ = imp.import_review(xlsx)
    assert gen.REVIEWED_FILES[0] in result["changed_files"]
    assert result["plan_checkbox_ready"] is False
