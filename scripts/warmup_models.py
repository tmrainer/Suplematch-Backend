from __future__ import annotations

from pathlib import Path
import sys

import joblib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.ml.runtime.condition_mvp_inference import load_condition_mvp_model
from app.ml.runtime.modelo2_inference import _register_torch_cpu_fallback


REQUIRED_ARTIFACTS = (
    "condition_mvp_model.pkl",
    "modelo1_pipeline.pkl",
    "modelo2_artifacts.pkl",
)


def main() -> int:
    model_dir = Path(settings.MODEL_DIR)
    missing = [name for name in REQUIRED_ARTIFACTS if not (model_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"Faltan artefactos en {model_dir}: {', '.join(missing)}")

    condition_model = load_condition_mvp_model()
    modelo1 = joblib.load(model_dir / "modelo1_pipeline.pkl")
    _register_torch_cpu_fallback()
    modelo2 = joblib.load(model_dir / "modelo2_artifacts.pkl")

    print(f"[OK] condition_mvp_model.pkl keys={sorted(condition_model.keys())[:8]}")
    print(f"[OK] modelo1_pipeline.pkl type={type(modelo1).__name__}")
    print(f"[OK] modelo2_artifacts.pkl keys={sorted(modelo2.keys())[:8]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
