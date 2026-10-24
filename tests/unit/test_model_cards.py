"""Model cards junto a cada artefacto servido (plan de fiabilidad, Fase 3/4)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.core.config import settings

MODEL_DIR = Path(settings.MODEL_DIR)
CARDS = {
    "condition_mvp_model.pkl": ("condition_mvp_model_card.json", {"model", "sha256_16", "clinical_validity", "data", "metrics_test", "limitations", "threshold_selection"}),
    "condition_lab_model.pkl": ("condition_lab_model_card.json", {"model", "sha256_16", "data", "metrics_test", "limitations"}),
    "modelo2_artifacts.pkl": ("modelo2_model_card.json", {"model", "sha256_16", "data", "metrics_held_out_edges", "limitations", "acceptance_threshold"}),
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


@pytest.mark.parametrize("artifact,card_name,required", [(k, *v) for k, v in CARDS.items()])
def test_each_served_artifact_has_a_model_card_with_matching_hash(artifact: str, card_name: str, required: set[str]) -> None:
    artifact_path = MODEL_DIR / artifact
    if not artifact_path.exists():
        pytest.skip(f"{artifact} no versionado")
    card_path = MODEL_DIR / card_name
    assert card_path.exists(), f"falta {card_name}: reentrenar el artefacto con su script de training"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    assert required <= set(card), required - set(card)
    assert card["sha256_16"] == _sha(artifact_path), "model card desactualizada respecto al .pkl"
    assert card["limitations"] and all(isinstance(item, str) for item in card["limitations"])


def test_condition_mvp_card_declares_synthetic_data_and_no_labs_metrics() -> None:
    card_path = MODEL_DIR / "condition_mvp_model_card.json"
    if not card_path.exists():
        pytest.skip("condition_mvp_model_card.json no versionado")
    card = json.loads(card_path.read_text(encoding="utf-8"))
    assert card["clinical_validity"] == "none_synthetic"
    assert card["threshold_selection"] == "internal_validation_split"
    assert 0.5 <= card["data"]["rows_without_labs_share"] <= 0.9, "la mayoria de filas debe ser solo encuesta"
    assert card["metrics_test"]["f1_macro_no_labs"] is not None


def test_modelo2_card_passes_acceptance_threshold() -> None:
    card_path = MODEL_DIR / "modelo2_model_card.json"
    if not card_path.exists():
        pytest.skip("modelo2_model_card.json no versionado")
    card = json.loads(card_path.read_text(encoding="utf-8"))
    assert card["acceptance_threshold"]["passed"] is True
    assert card["metrics_held_out_edges"]["roc_auc"] >= 0.65
