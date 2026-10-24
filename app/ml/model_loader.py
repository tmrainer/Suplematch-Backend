from __future__ import annotations

from pathlib import Path

from app.core.config import settings

CONDITION_MODEL = "condition_mvp_model.pkl"
MODEL2_ARTIFACTS = "modelo2_artifacts.pkl"


def check_model_artifacts(model_dir: Path | None = None) -> dict:
    """Verifica que los artefactos necesarios existan en disco antes de declarar el servicio listo.

    Modelo 1 requiere `condition_mvp_model.pkl` (el RF legacy `modelo1_pipeline.pkl` se retiro el 2026-10-23).
    Modelo 2 requiere `modelo2_artifacts.pkl`. Ninguno tiene fallback.
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
    return {
        "model_dir": str(base),
        "present": present,
        "model1": CONDITION_MODEL if model1_ok else None,
        "model2": MODEL2_ARTIFACTS if model2_ok else None,
        "ready": model1_ok and model2_ok,
        "missing": missing,
    }


_FINGERPRINT_CACHE: dict[str, tuple[float, str]] = {}


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def artifact_fingerprints(model_dir: Path | None = None) -> dict[str, str | None]:
    """Hash corto de cada artefacto y version de la knowledge base, para trazar cada recomendacion."""
    base = Path(model_dir or settings.MODEL_DIR)
    out: dict[str, str | None] = {}
    for name in (CONDITION_MODEL, MODEL2_ARTIFACTS):
        path = base / name
        if not path.exists():
            out[name] = None
            continue
        mtime = path.stat().st_mtime
        cached = _FINGERPRINT_CACHE.get(str(path))
        if cached is None or cached[0] != mtime:
            cached = (mtime, _sha256(path))
            _FINGERPRINT_CACHE[str(path)] = cached
        out[name] = cached[1]
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
    if not status["ready"]:
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
