"""Publica y descarga los modelos de runtime (`models/runtime/*.pkl`, no versionados) como assets de un release de GitHub.

El sha256 esperado de cada modelo esta en `data/insumos_manifest.json` (versionado): al descargar se rechaza cualquier
archivo con otro hash, asi un despliegue no puede quedarse con el modelo de un commit anterior sin que se note.

Uso (requiere `gh` autenticado):
  python scripts/ops/modelos_release.py publicar --tag models-2026-10-24   # sube los .pkl que coinciden con el manifiesto
  python scripts/ops/modelos_release.py descargar --tag models-2026-10-24  # baja, verifica y reemplaza
  python scripts/ops/modelos_release.py verificar                          # solo compara lo que hay en disco

El repositorio es publico: un release publica los modelos para cualquiera. Revisar que se pueda antes de publicar.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.ml.model_loader import _sha256, check_artifact_versions, expected_artifact_hashes  # noqa: E402

MODEL_DIR = ROOT / "models" / "runtime"


def _gh(*args: str) -> None:
    subprocess.run(["gh", *args], check=True, cwd=ROOT)


def publicar(tag: str) -> int:
    expected = expected_artifact_hashes()
    versions = check_artifact_versions(MODEL_DIR)
    if versions["problems"]:
        print("No se publica: los modelos en disco no son los del manifiesto.", *versions["problems"], sep="\n  ")
        print("Si se reentreno a proposito: python scripts/ops/verificar_insumos.py --update y comitear el manifiesto.")
        return 1
    files = [str(MODEL_DIR / name) for name in expected if (MODEL_DIR / name).exists()]
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, cwd=ROOT).stdout.strip()
    notes = "Modelos de runtime para el commit " + commit + ".\n\nsha256 (insumos_manifest.json):\n" + "\n".join(
        f"- `{name}`: `{sha}`" for name, sha in expected.items()
    )
    _gh("release", "create", tag, *files, "--title", f"Modelos {tag}", "--notes", notes, "--target", commit)
    print(f"Release {tag} publicado con {len(files)} modelos.")
    return 0


def descargar(tag: str) -> int:
    expected = expected_artifact_hashes()
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=MODEL_DIR) as tmp:
        _gh("release", "download", tag, "--dir", tmp, *[arg for name in expected for arg in ("--pattern", name)])
        bad = []
        for name, sha in expected.items():
            path = Path(tmp) / name
            if not path.exists():
                bad.append(f"{name}: no esta en el release")
            elif _sha256(path) != sha:
                bad.append(f"{name}: sha256 distinto del manifiesto")
        if bad:
            print(f"Release {tag} no corresponde a este commit; no se reemplazo nada.", *bad, sep="\n  ")
            return 1
        for name in expected:
            os.replace(Path(tmp) / name, MODEL_DIR / name)
    print(f"{len(expected)} modelos verificados en {MODEL_DIR}.")
    return 0


def verificar() -> int:
    versions = check_artifact_versions(MODEL_DIR)
    print(json.dumps(versions, indent=2, ensure_ascii=False))
    return 1 if versions["problems"] else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("publicar", "descargar"):
        sub.add_parser(name).add_argument("--tag", required=True)
    sub.add_parser("verificar")
    args = parser.parse_args()
    if args.command == "publicar":
        return publicar(args.tag)
    if args.command == "descargar":
        return descargar(args.tag)
    return verificar()


if __name__ == "__main__":
    sys.exit(main())
