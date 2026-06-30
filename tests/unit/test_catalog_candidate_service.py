from __future__ import annotations

import csv

import pytest

from app.domains.admin.servicio_candidatos_catalogo import CatalogCandidateService, candidate_id_for


FIELDS = [
    "component_id",
    "component_name",
    "pharmacy",
    "commercial_name",
    "price",
    "availability",
    "registro_sanitario",
    "url",
    "sku",
    "component_traceable",
    "component_ids_detected",
    "component_names_detected",
    "match_basis",
    "needs_catalog_review",
]


def write_candidates(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def candidate_rows():
    return [
        {
            "component_id": "COMP_ASHWA",
            "component_name": "Ashwagandha",
            "pharmacy": "Inkafarma",
            "commercial_name": "Ashwagandha 300 mg",
            "price": "73.90",
            "availability": "available",
            "registro_sanitario": "",
            "url": "https://example.test/ashwa",
            "sku": "A1",
            "component_traceable": "true_component_name_no_rs",
            "component_ids_detected": "COMP_ASHWA",
            "component_names_detected": "Ashwagandha",
            "match_basis": "COMP_ASHWA",
            "needs_catalog_review": "yes",
        },
        {
            "component_id": "COMP_COBRE",
            "component_name": "Cobre",
            "pharmacy": "Mifarma",
            "commercial_name": "Cobre validado",
            "price": "20.00",
            "availability": "available",
            "registro_sanitario": "RS-123",
            "url": "https://example.test/cobre",
            "sku": "C1",
            "component_traceable": "true_rs_component",
            "component_ids_detected": "COMP_COBRE",
            "component_names_detected": "Cobre",
            "match_basis": "COMP_COBRE",
            "needs_catalog_review": "yes",
        },
    ]


def service_for(tmp_path):
    candidates = tmp_path / "candidates.csv"
    write_candidates(candidates, candidate_rows())
    return CatalogCandidateService(
        relations_path=candidates,
        fallback_relations_path=tmp_path / "missing.csv",
        actions_path=tmp_path / "actions.json",
        promotions_path=tmp_path / "promotions.csv",
    )


def test_catalog_candidates_mark_missing_rs_and_promotable_verified(tmp_path):
    service = service_for(tmp_path)

    result = service.list_candidates()
    by_name = {item.component_name: item for item in result["candidates"]}

    assert by_name["Ashwagandha"].catalog_status == "candidate_needs_rs"
    assert by_name["Ashwagandha"].promotable is False
    assert by_name["Cobre"].catalog_status == "approved_verified"
    assert by_name["Cobre"].promotable is True
    assert result["status_counts"]["candidate_needs_rs"] == 1
    assert result["status_counts"]["approved_verified"] == 1


def test_catalog_candidate_action_overrides_status(tmp_path):
    service = service_for(tmp_path)
    row = candidate_rows()[0]
    candidate_id = candidate_id_for(row)

    updated = service.update_candidate_status(
        candidate_id,
        next_status="rejected_no_rs",
        reason="No se encontró RS en ficha ni envase",
        admin_user_id=None,
    )

    assert updated.catalog_status == "rejected_no_rs"
    assert updated.action_reason == "No se encontró RS en ficha ni envase"
    assert service.list_candidates(status_filter="rejected_no_rs")["total"] == 1


def test_catalog_candidate_without_rs_cannot_be_promoted(tmp_path):
    service = service_for(tmp_path)
    row = candidate_rows()[0]

    with pytest.raises(ValueError, match="requiere RS"):
        service.promote_candidate(candidate_id_for(row), reason="Intento", admin_user_id=None)
