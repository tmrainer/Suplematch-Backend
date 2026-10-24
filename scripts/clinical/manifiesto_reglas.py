"""Candado de version de las tablas clinicas (data/knowledge).

Cualquier cambio en reglas, umbrales, interacciones o guias de dosis cambia el comportamiento clinico. Este
manifiesto guarda el hash aprobado de cada tabla; tests/unit/test_clinical_rules_manifest.py falla si una tabla
cambia sin actualizar el manifiesto a proposito.

    # Ver que cambio (no modifica nada)
    python scripts/clinical/manifiesto_reglas.py --check

    # Aprobar la version actual, despues de revisar el informe de impacto
    python scripts/clinical/informe_impacto_reglas.py --base-ref HEAD
    python scripts/clinical/manifiesto_reglas.py --approve --by "Nombre" --note "Por que cambia y quien lo reviso"

Los hashes se calculan con saltos de linea normalizados (\\r\\n -> \\n) para no depender del sistema operativo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "data/knowledge/clinical_rules_manifest.json"
CLINICAL_FILES = [
    "data/knowledge/condition_rules.csv",
    "data/knowledge/conditions.csv",
    "data/knowledge/condition_data_requirements.csv",
    "data/knowledge/safety_rules.csv",
    "data/knowledge/component_interaction_rules.csv",
    "data/knowledge/condition_component_links.csv",
    "data/knowledge/component_life_stage_guidance.csv",
    "data/knowledge/biomarkers.csv",
]


def file_hash(path: Path) -> str:
    text = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(text).hexdigest()


def current_hashes(root: Path = ROOT) -> dict[str, str]:
    return {rel: file_hash(root / rel) for rel in CLINICAL_FILES}


def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def changed_files(root: Path = ROOT, manifest_path: Path = MANIFEST_PATH) -> list[str]:
    approved = load_manifest(manifest_path).get("files", {})
    now = current_hashes(root)
    return sorted(rel for rel in set(approved) | set(now) if approved.get(rel) != now.get(rel))


def approve(by: str, note: str, manifest_path: Path = MANIFEST_PATH) -> dict:
    previous = load_manifest(manifest_path) if manifest_path.exists() else {}
    history = list(previous.get("history", []))
    if previous.get("files"):
        history.append({key: previous[key] for key in ("approved_at", "approved_by", "note") if key in previous})
    manifest = {
        "_doc": "Hash aprobado de cada tabla clinica. Actualizar solo con scripts/clinical/manifiesto_reglas.py --approve "
                "tras revisar el informe de impacto (scripts/clinical/informe_impacto_reglas.py).",
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "approved_by": by,
        "note": note,
        "files": current_hashes(),
        "history": history[-20:],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Candado de version de las tablas clinicas.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--approve", action="store_true")
    parser.add_argument("--by", help="Quien aprueba (obligatorio con --approve).")
    parser.add_argument("--note", help="Motivo del cambio y revision (obligatorio con --approve).")
    args = parser.parse_args(argv)

    if args.approve:
        if not args.by or not args.note:
            parser.error("--approve requiere --by y --note")
        manifest = approve(args.by, args.note)
        print(f"Manifiesto actualizado ({len(manifest['files'])} tablas) por {args.by}.")
        return 0

    changed = changed_files()
    if not changed:
        print("Tablas clinicas sin cambios respecto del manifiesto aprobado.")
        return 0
    print("Tablas clinicas cambiadas sin aprobar:")
    for rel in changed:
        print(f"  - {rel}")
    print("Revisa el impacto (scripts/clinical/informe_impacto_reglas.py) y aprueba con --approve --by --note.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
