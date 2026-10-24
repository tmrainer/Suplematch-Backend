"""check_model_artifacts: el RF legacy `modelo1_pipeline.pkl` ya no cuenta como Modelo 1."""

from __future__ import annotations

from pathlib import Path

from app.ml.model_loader import artifact_fingerprints, check_model_artifacts


def test_legacy_model1_alone_is_not_ready(tmp_path: Path) -> None:
    (tmp_path / "modelo1_pipeline.pkl").write_bytes(b"legacy")
    (tmp_path / "modelo2_artifacts.pkl").write_bytes(b"m2")

    status = check_model_artifacts(tmp_path)

    assert status["ready"] is False
    assert status["model1"] is None
    assert status["missing"] == ["condition_mvp_model.pkl"]
    assert "modelo1_pipeline.pkl" not in status["present"]


def test_condition_mvp_and_model2_are_ready(tmp_path: Path) -> None:
    (tmp_path / "condition_mvp_model.pkl").write_bytes(b"m1")
    (tmp_path / "modelo2_artifacts.pkl").write_bytes(b"m2")

    status = check_model_artifacts(tmp_path)

    assert status["ready"] is True
    assert status["model1"] == "condition_mvp_model.pkl"
    assert "modelo1_pipeline.pkl" not in artifact_fingerprints(tmp_path)
