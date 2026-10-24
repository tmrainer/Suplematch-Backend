"""Verifica presencia y hash de los insumos declarados en data/insumos_manifest.json.

Uso:
  python scripts/ops/verificar_insumos.py                 # reporta presentes/ausentes y hashes cambiados
  python scripts/ops/verificar_insumos.py --update        # escribe sha256 de los insumos presentes
  python scripts/ops/verificar_insumos.py --strict        # exit 1 si falta cualquier insumo o cambio un hash
  python scripts/ops/verificar_insumos.py --strict-versioned  # exit 1 solo por insumos versionados (CI)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "insumos_manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--strict-versioned", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    report = []
    failures = 0
    for item in manifest["insumos"]:
        path = ROOT / item["path"]
        entry = {"path": item["path"], "versioned": item["versioned"], "present": path.exists()}
        if path.exists():
            digest = sha256(path)
            entry["sha256"] = digest
            if item.get("sha256") and item["sha256"] != digest:
                entry["changed"] = True
                if args.strict or (args.strict_versioned and item["versioned"]):
                    failures += 1
            if args.update:
                item["sha256"] = digest
        else:
            entry["generador"] = item.get("generador")
            if args.strict or (args.strict_versioned and item["versioned"]):
                failures += 1
        report.append(entry)

    if args.update:
        MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps({"failures": failures, "insumos": report}, indent=2, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
