from __future__ import annotations

import json
from pathlib import Path

from app.core.config import BASE_DIR, settings

CONDITION_MODEL = "condition_mvp_model.pkl"
MODEL2_ARTIFACTS = "modelo2_artifacts.pkl"
CONDITION_LAB_MODEL = "condition_lab_model.pkl"
# Los .pkl no estan en git; su sha256 si (insumos_manifest.json, `verificar_insumos.py --update`). Un artefacto con
# otro hash es un modelo distinto del que se reviso para este commit (p. ej. un despliegue que no copio el reentreno).
MANIFEST_PATH = BASE_DIR / "data" / "insumos_manifest.json"
STRICT_ENVIRONMENTS = {"staging", "production", "prod"}


def check_model_artifacts(model_dir: Path | None = None, manifest_path: Path | None = None, strict: bool | None = None) -> dict:
    """Verifica que los artefactos necesarios existan en disco antes de declarar el servicio listo.

    Modelo 1 requiere `condition_mvp_model.pkl` (el RF legacy `modelo1_pipeline.pkl` se retiro el 2026-10-23).
    Modelo 2 requiere `modelo2_artifacts.pkl`. Ninguno tiene fallback. Ademas compara hashes y contrato
    (`check_artifact_versions`).
    """
    base = Path(model_dir or settings.MODEL_DIR)
    present = {name: (base / name).exists() for name in (CONDITION_MODEL, MODEL2_ARTIFACTS)}
    model1_ok = present[CONDITION_MODEL]
    model2_ok = present[MODEL2_ARTIFACTS]
    missing = []
    if not model1_ok:
        missing.append(CONDITION_MODEL)
    if not model2_ok:
        missing.append(MODEL2_ARTIFACTS)
    versions = check_artifact_versions(base, manifest_path)
    if strict is None:
        strict = settings.ENVIRONMENT.lower() in STRICT_ENVIRONMENTS
    return {
        "model_dir": str(base),
        "present": present,
        "model1": CONDITION_MODEL if model1_ok else None,
        "model2": MODEL2_ARTIFACTS if model2_ok else None,
        # En staging/prod un modelo distinto del registrado deja el servicio sin listo; en desarrollo solo avisa.
        "ready": model1_ok and model2_ok and not (strict and versions["problems"]),
        "missing": missing,
        "versions": versions,
        "strict_versions": strict,
    }


def expected_artifact_hashes(manifest_path: Path | None = None) -> dict[str, str]:
    path = Path(manifest_path or MANIFEST_PATH)
    if not path.exists():
        return {}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return {
        Path(item["path"]).name: item["sha256"]
        for item in manifest.get("insumos", [])
        if item.get("path", "").startswith("models/runtime/") and item.get("sha256")
    }


def check_artifact_versions(model_dir: Path | None = None, manifest_path: Path | None = None) -> dict:
    """Compara cada artefacto con el sha256 del manifiesto y el contrato de features del modelo real.

    Estado por artefacto: `ok`, `mismatch` (otro modelo), `missing` (registrado pero ausente) o `unregistered`.
    `problems` lista lo que impide confiar en que se sirve el modelo de este commit.
    """
    base = Path(model_dir or settings.MODEL_DIR)
    expected = expected_artifact_hashes(manifest_path)
    artifacts: dict[str, dict] = {}
    problems: list[str] = []
    for name in (CONDITION_MODEL, MODEL2_ARTIFACTS, CONDITION_LAB_MODEL):
        path = base / name
        want = expected.get(name)
        if not path.exists():
            status, digest = ("missing" if want else "unregistered"), None
        else:
            digest = _sha256(path)
            status = "unregistered" if not want else ("ok" if digest == want else "mismatch")
        artifacts[name] = {"status": status, "sha256": digest, "expected_sha256": want}
        if status in {"mismatch", "missing"}:
            problems.append(f"{name}: {status}")

    lab_path = base / CONDITION_LAB_MODEL
    if lab_path.exists():
        from app.ml.runtime.condition_lab_inference import contract_problem

        try:
            import joblib

            contract = contract_problem(joblib.load(lab_path))
        except Exception as exc:  # artefacto corrupto
            contract = f"no carga: {exc}"
        artifacts[CONDITION_LAB_MODEL]["contract"] = contract or "ok"
        if contract:
            problems.append(f"{CONDITION_LAB_MODEL}: {contract}")
    return {"artifacts": artifacts, "problems": problems}


_FINGERPRINT_CACHE: dict[str, tuple[float, str]] = {}


def _sha256(path: Path) -> str:
    """sha256 completo, cacheado por mtime (se pide en cada recomendacion y en cada /health/ready)."""
    import hashlib

    mtime = path.stat().st_mtime
    cached = _FINGERPRINT_CACHE.get(str(path))
    if cached is not None and cached[0] == mtime:
        return cached[1]
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    _FINGERPRINT_CACHE[str(path)] = (mtime, digest.hexdigest())
    return digest.hexdigest()


def artifact_fingerprints(model_dir: Path | None = None) -> dict[str, str | None]:
    """Hash corto de cada artefacto y version de la knowledge base, para trazar cada recomendacion."""
    base = Path(model_dir or settings.MODEL_DIR)
    out: dict[str, str | None] = {}
    for name in (CONDITION_MODEL, MODEL2_ARTIFACTS):
        path = base / name
        if not path.exists():
            out[name] = None
            continue
        out[name] = _sha256(path)[:16]
    knowledge_dir = Path(__file__).resolve().parents[2] / "data" / "knowledge"
    versions = []
    for csv_name in ("conditions.csv", "condition_component_links.csv", "biomarkers.csv"):
        path = knowledge_dir / csv_name
        if path.exists():
            with path.open(encoding="utf-8-sig") as handle:
                handle.readline()
                first = handle.readline().split(",")[0].strip()
            versions.append(f"{csv_name.split('.')[0]}={first}")
    out["knowledge"] = ";".join(versions) or None
    return out


def load_all_models() -> dict:
    models = {
        "pipeline_vitaminas": None,
    }

    status = check_model_artifacts()
    for problem in status["versions"]["problems"]:
        level = "ERROR" if status["strict_versions"] else "WARN"
        print(f"[{level}] Artefacto distinto del registrado en insumos_manifest.json: {problem}. "
              "Copiar el modelo de este commit (scripts/ops/modelos_release.py descargar) o, si se reentreno a "
              "proposito, `python scripts/ops/verificar_insumos.py --update`.")
    # Un hash distinto no impide cargar (lo marca /health/ready); un archivo ausente si.
    if status["missing"]:
        print(f"[WARN] Artefactos de modelo ausentes en {status['model_dir']}: {', '.join(status['missing'])}. "
              "El endpoint /recommend respondera error hasta que existan.")
        return models

    try:
        from app.ml.runtime.pipeline_completo import pipeline_vitaminas

        models["pipeline_vitaminas"] = pipeline_vitaminas
        print(f"[OK] pipeline_vitaminas cargado (model1={status['model1']}, model2={status['model2']}).")

    except Exception as exc:
        print(f"[WARN] No se pudo cargar pipeline_vitaminas: {exc}")

    return models
