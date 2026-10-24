"""Lee el paquete de revision clinica completado y resume acuerdo, errores graves y cambios pedidos en reglas.

    python scripts/clinical/importar_revision.py --xlsx data/reports/clinical_review/<paquete>_revisado.xlsx

Salida en --out-dir (default data/reports/clinical_review/):
    <package_id>_resultado.json   metricas, completitud, firma y estado
    <package_id>_acciones.csv     reglas a modificar/rechazar y casos con error grave, para el equipo

Estado:
    incompleta         faltan casos, decisiones de reglas o firma
    completa           todo revisado y firmado (la casilla del plan se marca solo si ademas no hay errores
                       graves abiertos y no cambiaron los archivos revisados)
Si los archivos revisados cambiaron desde que se genero el paquete, se listan en `changed_files` y las reglas
cuyo id ya no existe en el CSV actual se marcan como `regla_cambiada_o_eliminada`.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from scripts.clinical.generar_paquete_revision import (
    CASE_REVIEW_COLUMNS,
    DEFAULT_OUT_DIR,
    INGREDIENT_SHEET,
    RULE_SHEETS,
    SIGNATURE_FIELDS,
    file_manifest,
    rule_frames,
)

REQUIRED_CASE_COLUMNS = ["rev_condiciones", "rev_recomendaciones", "rev_seguridad", "rev_error_grave"]
MIN_CASES = 100


def _clean(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _share(series: pd.Series, options: list[str]) -> dict[str, float | None]:
    filled = series[series != ""]
    if filled.empty:
        return {option: None for option in options}
    return {option: round(float((filled == option).mean()), 4) for option in options}


def read_meta(xlsx: Path) -> dict[str, Any]:
    meta_df = pd.read_excel(xlsx, sheet_name="_meta", dtype=str)
    return {row["key"]: json.loads(row["value"]) for row in meta_df.to_dict("records")}


def summarize_cases(xlsx: Path) -> dict[str, Any]:
    cases = pd.read_excel(xlsx, sheet_name="Casos", dtype=str).fillna("")
    for column in CASE_REVIEW_COLUMNS:
        cases[column] = cases[column].map(_clean).str.lower() if column != "rev_comentario" else cases[column].map(_clean)
    complete_mask = (cases[REQUIRED_CASE_COLUMNS] != "").all(axis=1)
    reviewed = cases[complete_mask]
    serious = reviewed[reviewed["rev_error_grave"] == "si"]
    return {
        "total": int(len(cases)),
        "reviewed": int(complete_mask.sum()),
        "conditions_agreement": _share(reviewed["rev_condiciones"], CASE_REVIEW_COLUMNS["rev_condiciones"]),
        "recommendations_agreement": _share(reviewed["rev_recomendaciones"], CASE_REVIEW_COLUMNS["rev_recomendaciones"]),
        "safety": _share(reviewed["rev_seguridad"], CASE_REVIEW_COLUMNS["rev_seguridad"]),
        "serious_errors": int(len(serious)),
        "serious_error_cases": [
            {
                "case_id": row["case_id"],
                "comentario": row["rev_comentario"],
                "componentes_inadecuados": row["rev_componentes_inadecuados"],
                "seguridad": row["rev_seguridad"],
            }
            for row in serious.to_dict("records")
        ],
    }


def summarize_rules(xlsx: Path, current: dict[str, pd.DataFrame]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    sheets = [sheet for sheet, _, _ in RULE_SHEETS] + [INGREDIENT_SHEET]
    summary: dict[str, Any] = {}
    actions: list[dict[str, Any]] = []
    for sheet in sheets:
        reviewed = pd.read_excel(xlsx, sheet_name=sheet, dtype=str).fillna("")
        reviewed["rev_decision"] = reviewed["rev_decision"].map(_clean).str.lower()
        current_keys = set(current[sheet]["rule_key"]) if sheet in current else set()
        reviewed_keys = set(reviewed["rule_key"])
        counts = reviewed["rev_decision"].replace("", "sin_decision").value_counts().to_dict()
        summary[sheet] = {
            "rows": int(len(reviewed)),
            "decided": int((reviewed["rev_decision"].isin(["aprobar", "modificar", "rechazar"])).sum()),
            "decisions": {key: int(value) for key, value in counts.items()},
            "changed_or_removed_since_review": sorted(reviewed_keys - current_keys),
            "new_rules_not_reviewed": sorted(current_keys - reviewed_keys),
        }
        identity = [column for column in reviewed.columns if column not in {"rule_key"} and not column.startswith("rev_")][:6]
        for row in reviewed.to_dict("records"):
            if row["rev_decision"] in {"modificar", "rechazar"}:
                actions.append({
                    "tipo": "regla",
                    "hoja": sheet,
                    "id": row["rule_key"],
                    "accion": row["rev_decision"],
                    "detalle": " | ".join(f"{column}={row[column]}" for column in identity),
                    "cambio_propuesto": _clean(row.get("rev_cambio_propuesto")),
                    "fuente_sugerida": _clean(row.get("rev_fuente_sugerida")),
                    "comentario": _clean(row.get("rev_comentario")),
                    "regla_cambiada_o_eliminada": row["rule_key"] not in current_keys,
                })
    return summary, actions


def read_signature(xlsx: Path) -> dict[str, Any]:
    raw = pd.read_excel(xlsx, sheet_name="Firma", dtype=str, nrows=len(SIGNATURE_FIELDS)).fillna("")
    fields = {row["Campo"]: _clean(row["Valor"]) for row in raw.to_dict("records")}
    return {"fields": fields, "complete": all(fields.get(name) for name in SIGNATURE_FIELDS)}


def import_review(xlsx: Path, root: Path = ROOT) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    meta = read_meta(xlsx)
    reviewed_hashes = {item["file"]: item["sha256_12"] for item in meta.get("files", [])}
    current_hashes = {item["file"]: item["sha256_12"] for item in file_manifest(root)}
    changed = sorted(name for name, digest in reviewed_hashes.items() if current_hashes.get(name) != digest)

    cases = summarize_cases(xlsx)
    rules, actions = summarize_rules(xlsx, rule_frames())
    signature = read_signature(xlsx)
    for item in cases["serious_error_cases"]:
        actions.append({
            "tipo": "caso_error_grave",
            "hoja": "Casos",
            "id": item["case_id"],
            "accion": "corregir",
            "detalle": item["componentes_inadecuados"],
            "cambio_propuesto": "",
            "fuente_sugerida": "",
            "comentario": item["comentario"],
            "regla_cambiada_o_eliminada": "",
        })

    rules_complete = all(sheet["decided"] == sheet["rows"] for sheet in rules.values())
    complete = cases["reviewed"] >= MIN_CASES and cases["reviewed"] == cases["total"] and rules_complete and signature["complete"]
    result = {
        "package_id": meta.get("package_id"),
        "status": "completa" if complete else "incompleta",
        "plan_checkbox_ready": bool(complete and cases["serious_errors"] == 0 and not changed),
        "changed_files": changed,
        "cases": cases,
        "rules": rules,
        "signature": signature,
        "actions": len(actions),
    }
    return result, actions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Importa el paquete de revision clinica completado.")
    parser.add_argument("--xlsx", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result, actions = import_review(args.xlsx)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = result["package_id"] or args.xlsx.stem
    (args.out_dir / f"{stem}_resultado.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fieldnames = ["tipo", "hoja", "id", "accion", "detalle", "cambio_propuesto", "fuente_sugerida", "comentario", "regla_cambiada_o_eliminada"]
    with (args.out_dir / f"{stem}_acciones.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(actions)
    print(json.dumps({key: result[key] for key in ("package_id", "status", "plan_checkbox_ready", "changed_files", "actions")}, ensure_ascii=False, indent=2))
    print(json.dumps({key: result["cases"][key] for key in ("total", "reviewed", "conditions_agreement", "recommendations_agreement", "safety", "serious_errors")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
