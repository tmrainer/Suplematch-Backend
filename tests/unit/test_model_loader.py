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


def _manifest(tmp_path: Path, **hashes: str) -> Path:
    import json

    path = tmp_path / "manifest.json"
    insumos = [{"path": f"models/runtime/{name}.pkl", "versioned": False, "sha256": sha} for name, sha in hashes.items()]
    path.write_text(json.dumps({"insumos": insumos}), encoding="utf-8")
    return path


def _sha(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def test_artifact_with_other_hash_blocks_readiness_only_in_strict_mode(tmp_path: Path) -> None:
    models = tmp_path / "models"
    models.mkdir()
    (models / "condition_mvp_model.pkl").write_bytes(b"m1")
    (models / "modelo2_artifacts.pkl").write_bytes(b"m2-viejo")
    manifest = _manifest(tmp_path, condition_mvp_model=_sha(b"m1"), modelo2_artifacts=_sha(b"m2-nuevo"))

    strict = check_model_artifacts(models, manifest, strict=True)
    relaxed = check_model_artifacts(models, manifest, strict=False)

    assert strict["ready"] is False and relaxed["ready"] is True
    assert strict["versions"]["artifacts"]["condition_mvp_model.pkl"]["status"] == "ok"
    assert strict["versions"]["artifacts"]["modelo2_artifacts.pkl"]["status"] == "mismatch"
    assert strict["versions"]["problems"] == ["modelo2_artifacts.pkl: mismatch"]


def test_registered_lab_model_missing_is_a_problem(tmp_path: Path) -> None:
    models = tmp_path / "models"
    models.mkdir()
    (models / "condition_mvp_model.pkl").write_bytes(b"m1")
    (models / "modelo2_artifacts.pkl").write_bytes(b"m2")
    manifest = _manifest(tmp_path, condition_mvp_model=_sha(b"m1"), modelo2_artifacts=_sha(b"m2"), condition_lab_model="ab" * 32)

    status = check_model_artifacts(models, manifest, strict=True)

    assert status["ready"] is False
    assert status["versions"]["problems"] == ["condition_lab_model.pkl: missing"]


def test_lab_model_trained_with_other_feature_contract_is_rejected(tmp_path: Path) -> None:
    import joblib

    from app.ml.runtime import condition_lab_inference as cli

    models = tmp_path / "models"
    models.mkdir()
    joblib.dump({"feature_contract_version": "nhanes_questionnaire_v1"}, models / "condition_lab_model.pkl")

    lab = check_model_artifacts(models, _manifest(tmp_path), strict=True)["versions"]["artifacts"]["condition_lab_model.pkl"]

    assert lab["status"] == "unregistered"
    assert "nhanes_questionnaire_v1" in lab["contract"]
    assert cli.contract_problem({"feature_contract_version": cli.FEATURE_CONTRACT_VERSION}) is None


def test_repo_manifest_registers_every_runtime_model() -> None:
    from app.ml.model_loader import CONDITION_LAB_MODEL, CONDITION_MODEL, MODEL2_ARTIFACTS, expected_artifact_hashes

    assert {CONDITION_MODEL, MODEL2_ARTIFACTS, CONDITION_LAB_MODEL} <= set(expected_artifact_hashes())
