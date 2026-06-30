from __future__ import annotations

import argparse
import csv
import json
from copy import deepcopy
from pathlib import Path
from statistics import mean
from typing import Any

from app.core.config import BASE_DIR
from app.domains.catalog.servicio_catalogo_productos import ProductCatalogService
from app.domains.recommendations.servicio_recomendaciones import _attach_products_to_recommendations
from app.ml.runtime.feedback_reranker import rerank_packs
from app.ml.runtime.modelo2_inference import recomendar_suplementos


REPORT_DIR = BASE_DIR / "data" / "reports" / "supplement_model"


MODEL2_EVAL_CASES: list[dict[str, Any]] = [
    {
        "case_id": "vitamin_d_lab_low",
        "conditions": ["DEFICIT_VIT_D"],
        "condition_scores": {"DEFICIT_VIT_D": 0.88},
        "expected_top3": ["COMP_94DFE28A9A5C"],
        "expected_blocked": [],
        "context": {"edad": 34, "sexo": "F", "condiciones_seguridad": []},
    },
    {
        "case_id": "vegan_b12_signal",
        "conditions": ["DEFICIT_B12"],
        "condition_scores": {"DEFICIT_B12": 0.82},
        "expected_top3": ["COMP_06B36D3A8FF3"],
        "expected_blocked": [],
        "context": {"edad": 29, "sexo": "F", "tipo_dieta": "vegana"},
    },
    {
        "case_id": "iron_requires_lab_signal",
        "conditions": ["DEFICIT_HIERRO"],
        "condition_scores": {"DEFICIT_HIERRO": 0.84},
        "expected_top3": ["COMP_B6A8F8958154"],
        "expected_blocked": [],
        "expected_risky_avoided": ["COMP_D4790F9775EF"],
        "context": {"edad": 31, "sexo": "F"},
    },
    {
        "case_id": "folate_prioritizes_folic_acid_and_keeps_b12_context",
        "conditions": ["DEFICIT_FOLATO"],
        "condition_scores": {"DEFICIT_FOLATO": 0.81},
        "expected_top3": ["COMP_A9136ADF22F7", "COMP_06B36D3A8FF3"],
        "expected_blocked": [],
        "context": {"edad": 26, "sexo": "F"},
    },
    {
        "case_id": "vitamin_c_low_prioritizes_vitamin_c",
        "conditions": ["RIESGO_VITAMINA_C_BAJA"],
        "condition_scores": {"RIESGO_VITAMINA_C_BAJA": 0.79},
        "expected_top3": ["COMP_67B16EEFC42F"],
        "expected_blocked": [],
        "context": {"edad": 24, "sexo": "M"},
    },
    {
        "case_id": "protein_low_prioritizes_protein",
        "conditions": ["RIESGO_PROTEINA_INSUFICIENTE"],
        "condition_scores": {"RIESGO_PROTEINA_INSUFICIENTE": 0.77},
        "expected_top3": ["COMP_927AAC8EA873"],
        "expected_blocked": [],
        "context": {"edad": 30, "sexo": "M"},
    },
    {
        "case_id": "omega3_low_fish_intake",
        "conditions": ["RIESGO_OMEGA3_BAJO"],
        "condition_scores": {"RIESGO_OMEGA3_BAJO": 0.80},
        "expected_top3": ["COMP_447F5E523CED", "COMP_F3C5987AA984", "COMP_F71DD4665D9C"],
        "expected_blocked": [],
        "context": {"restricciones_alergias": []},
    },
    {
        "case_id": "omega3_fish_allergy_blocks_dha",
        "conditions": ["RIESGO_OMEGA3_BAJO"],
        "condition_scores": {"RIESGO_OMEGA3_BAJO": 0.80},
        "expected_top3": ["COMP_447F5E523CED", "COMP_F3C5987AA984"],
        "expected_blocked": ["COMP_F71DD4665D9C"],
        "expected_risky_avoided": ["COMP_F71DD4665D9C"],
        "context": {"restricciones_alergias": ["pescado_mariscos"]},
    },
    {
        "case_id": "renal_sport_blocks_creatine",
        "conditions": ["RENDIMIENTO_DEPORTIVO"],
        "condition_scores": {"RENDIMIENTO_DEPORTIVO": 0.78},
        "expected_top3": ["COMP_83336712C554", "COMP_927AAC8EA873", "COMP_7B47CDB437E8"],
        "expected_blocked": ["COMP_7B47CDB437E8"],
        "expected_risky_avoided": ["COMP_7B47CDB437E8"],
        "context": {"condiciones_seguridad": ["enfermedad_renal"]},
    },
    {
        "case_id": "bone_health_anticoagulants_blocks_vitamin_k",
        "conditions": ["RIESGO_SALUD_OSEA"],
        "condition_scores": {"RIESGO_SALUD_OSEA": 0.76},
        "expected_top3": ["COMP_275450118D60", "COMP_94DFE28A9A5C"],
        "expected_blocked": ["COMP_64DE5343502D"],
        "expected_risky_avoided": ["COMP_64DE5343502D"],
        "context": {"condiciones_seguridad": ["anticoagulantes"]},
    },
    {
        "case_id": "metabolic_glucose_context_not_commercial",
        "conditions": ["RIESGO_METABOLICO_GLUCOSA"],
        "condition_scores": {"RIESGO_METABOLICO_GLUCOSA": 0.74},
        "expected_top3": ["COMP_3F24EA59D864", "COMP_83336712C554"],
        "expected_blocked": ["COMP_3F24EA59D864", "COMP_83336712C554"],
        "expected_risky_avoided": ["COMP_3F24EA59D864"],
        "context": {"condiciones_seguridad": []},
    },
    {
        "case_id": "dyslipidemia_context_not_commercial",
        "conditions": ["RIESGO_DISLIPIDEMIA"],
        "condition_scores": {"RIESGO_DISLIPIDEMIA": 0.79},
        "expected_top3": ["COMP_447F5E523CED", "COMP_8BB25B9A3BE5"],
        "expected_blocked": ["COMP_447F5E523CED", "COMP_8BB25B9A3BE5"],
        "expected_risky_avoided": ["COMP_8BB25B9A3BE5"],
        "context": {"condiciones_seguridad": []},
    },
    {
        "case_id": "stress_sleep_context",
        "conditions": ["ESTRES_SUENO"],
        "condition_scores": {"ESTRES_SUENO": 0.72},
        "expected_top3": ["COMP_83336712C554", "COMP_74AC5BE900AC"],
        "expected_blocked": ["COMP_83336712C554", "COMP_74AC5BE900AC"],
        "context": {"condiciones_seguridad": []},
    },
    {
        "case_id": "magnesium_deficit_with_sleep_allows_magnesium_only",
        "conditions": ["DEFICIT_MAGNESIO", "ESTRES_SUENO"],
        "condition_scores": {"DEFICIT_MAGNESIO": 0.82, "ESTRES_SUENO": 0.72},
        "expected_top3": ["COMP_83336712C554"],
        "expected_blocked": ["COMP_74AC5BE900AC"],
        "expected_risky_avoided": ["COMP_74AC5BE900AC"],
        "context": {"condiciones_seguridad": []},
    },
    {
        "case_id": "hair_skin_nails_context",
        "conditions": ["RIESGO_CABELLO_PIEL_UNAS"],
        "condition_scores": {"RIESGO_CABELLO_PIEL_UNAS": 0.74},
        "expected_top3": ["COMP_723DBC80CC4E", "COMP_641FDABDC956"],
        "expected_blocked": ["COMP_723DBC80CC4E", "COMP_641FDABDC956"],
        "context": {"condiciones_seguridad": []},
    },
    {
        "case_id": "hair_skin_with_zinc_deficit_allows_zinc_blocks_cosmetic_context",
        "conditions": ["DEFICIT_ZINC", "RIESGO_CABELLO_PIEL_UNAS"],
        "condition_scores": {"DEFICIT_ZINC": 0.84, "RIESGO_CABELLO_PIEL_UNAS": 0.69},
        "expected_top3": ["COMP_723DBC80CC4E"],
        "expected_blocked": ["COMP_641FDABDC956", "COMP_2671E7AB4CBB"],
        "context": {"condiciones_seguridad": []},
    },
    {
        "case_id": "immunity_context_not_commercial",
        "conditions": ["BAJA_INMUNIDAD"],
        "condition_scores": {"BAJA_INMUNIDAD": 0.73},
        "expected_top3": ["COMP_723DBC80CC4E", "COMP_67B16EEFC42F", "COMP_94DFE28A9A5C"],
        "expected_blocked": ["COMP_723DBC80CC4E", "COMP_67B16EEFC42F", "COMP_94DFE28A9A5C"],
        "context": {"condiciones_seguridad": []},
    },
    {
        "case_id": "performance_context_not_commercial",
        "conditions": ["RENDIMIENTO_DEPORTIVO"],
        "condition_scores": {"RENDIMIENTO_DEPORTIVO": 0.76},
        "expected_top3": ["COMP_83336712C554", "COMP_927AAC8EA873", "COMP_7B47CDB437E8"],
        "expected_blocked": ["COMP_83336712C554", "COMP_927AAC8EA873", "COMP_7B47CDB437E8"],
        "context": {"condiciones_seguridad": []},
    },
    {
        "case_id": "renal_safety_blocks_electrolytes_and_creatine",
        "conditions": ["SAFETY_RENAL"],
        "condition_scores": {"SAFETY_RENAL": 0.92},
        "expected_top3": ["COMP_BB2F708BF799", "COMP_83336712C554", "COMP_7B47CDB437E8", "COMP_275450118D60"],
        "expected_blocked": ["COMP_BB2F708BF799", "COMP_83336712C554", "COMP_7B47CDB437E8", "COMP_275450118D60"],
        "expected_risky_avoided": ["COMP_BB2F708BF799", "COMP_7B47CDB437E8"],
        "context": {"condiciones_seguridad": ["enfermedad_renal"]},
    },
    {
        "case_id": "hepatic_safety_blocks_high_risk_components",
        "conditions": ["SAFETY_HEPATICA"],
        "condition_scores": {"SAFETY_HEPATICA": 0.91},
        "expected_top3": ["COMP_90C4121BAE0C", "COMP_AE7EE271FD2C", "COMP_8F63E852ED34"],
        "expected_blocked": ["COMP_90C4121BAE0C", "COMP_AE7EE271FD2C", "COMP_8F63E852ED34"],
        "expected_risky_avoided": ["COMP_90C4121BAE0C", "COMP_AE7EE271FD2C", "COMP_8F63E852ED34"],
        "context": {"condiciones_seguridad": ["enfermedad_hepatica"]},
    },
    {
        "case_id": "thyroid_safety_context_not_commercial",
        "conditions": ["SAFETY_TIROIDEA"],
        "condition_scores": {"SAFETY_TIROIDEA": 0.91},
        "expected_top3": ["COMP_22DA46FADFFD", "COMP_781B4EA1D853", "COMP_AE7EE271FD2C"],
        "expected_blocked": ["COMP_22DA46FADFFD", "COMP_781B4EA1D853", "COMP_AE7EE271FD2C"],
        "expected_risky_avoided": ["COMP_22DA46FADFFD"],
        "context": {"condiciones_seguridad": ["problema_tiroideo", "tiroides"]},
    },
    {
        "case_id": "visual_health_context_not_commercial",
        "conditions": ["SALUD_VISUAL"],
        "condition_scores": {"SALUD_VISUAL": 0.78},
        "expected_top3": ["COMP_C873A4B5C00A", "COMP_D02C918DB476", "COMP_90C4121BAE0C"],
        "expected_blocked": ["COMP_C873A4B5C00A", "COMP_D02C918DB476", "COMP_90C4121BAE0C"],
        "context": {"condiciones_seguridad": []},
    },
    {
        "case_id": "digestive_health_context_not_commercial",
        "conditions": ["SALUD_DIGESTIVA"],
        "condition_scores": {"SALUD_DIGESTIVA": 0.78},
        "expected_top3": ["COMP_C5CD8E1D6AAE", "COMP_5FA5A40B1A56", "COMP_43BE32DB2D1B"],
        "expected_blocked": ["COMP_C5CD8E1D6AAE", "COMP_5FA5A40B1A56", "COMP_43BE32DB2D1B"],
        "context": {"condiciones_seguridad": []},
    },
    {
        "case_id": "nutrition_fatigue_context_not_commercial",
        "conditions": ["FATIGA_NUTRICIONAL"],
        "condition_scores": {"FATIGA_NUTRICIONAL": 0.78},
        "expected_top3": ["COMP_586F3B3DE0F3", "COMP_4F4F134A6B55", "COMP_A204C673A9A2"],
        "expected_blocked": ["COMP_586F3B3DE0F3", "COMP_4F4F134A6B55", "COMP_A204C673A9A2"],
        "context": {"condiciones_seguridad": []},
    },
    {
        "case_id": "hydration_electrolytes_context_not_commercial",
        "conditions": ["HIDRATACION_ELECTROLITOS"],
        "condition_scores": {"HIDRATACION_ELECTROLITOS": 0.78},
        "expected_top3": ["COMP_83336712C554", "COMP_AFF3B61AB344", "COMP_BB2F708BF799"],
        "expected_blocked": ["COMP_83336712C554", "COMP_AFF3B61AB344", "COMP_BB2F708BF799"],
        "context": {"condiciones_seguridad": []},
    },
    {
        "case_id": "cardiovascular_context_not_commercial",
        "conditions": ["SALUD_CARDIOVASCULAR_CONTEXTUAL"],
        "condition_scores": {"SALUD_CARDIOVASCULAR_CONTEXTUAL": 0.78},
        "expected_top3": ["COMP_447F5E523CED", "COMP_83336712C554", "COMP_8BB25B9A3BE5"],
        "expected_blocked": ["COMP_447F5E523CED", "COMP_83336712C554", "COMP_8BB25B9A3BE5"],
        "context": {"condiciones_seguridad": []},
    },
    {
        "case_id": "cognitive_health_context_not_commercial",
        "conditions": ["SALUD_COGNITIVA"],
        "condition_scores": {"SALUD_COGNITIVA": 0.78},
        "expected_top3": ["COMP_A204C673A9A2", "COMP_F71DD4665D9C", "COMP_430EB7DE720D"],
        "expected_blocked": ["COMP_A204C673A9A2", "COMP_F71DD4665D9C", "COMP_430EB7DE720D"],
        "context": {"condiciones_seguridad": []},
    },
]


def _top_ids(recommendations: list[dict[str, Any]], top_n: int = 3) -> list[str]:
    return [
        str(item.get("component_id"))
        for item in recommendations[:top_n]
        if item.get("component_id")
    ]


def _eligible_recommendations(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item for item in recommendations
        if item.get("commercial_eligible") is not False
        and item.get("recommendation_role") != "safety_context"
    ]


def evaluate_case(case: dict[str, Any], product_catalog: ProductCatalogService) -> dict[str, Any]:
    result = recomendar_suplementos(
        case["conditions"],
        condition_scores=case.get("condition_scores"),
        user_context=case.get("context"),
    )
    recommendations = result.get("recomendaciones", [])
    with_products = _attach_products_to_recommendations(deepcopy(recommendations), product_catalog)
    by_component = {
        str(item.get("component_id")): item
        for item in with_products
        if item.get("component_id")
    }

    top3_ids = _top_ids(recommendations)
    expected_top3 = set(case.get("expected_top3") or [])
    expected_blocked = set(case.get("expected_blocked") or [])
    expected_risky_avoided = set(case.get("expected_risky_avoided") or [])

    matched_top3 = sorted(expected_top3.intersection(top3_ids))
    blocked_ok = []
    blocked_fail = []
    for component_id in expected_blocked:
        item = by_component.get(component_id)
        if item and (
            item.get("commercial_eligible") is False
            or item.get("commercial_recommendation_blocked") is True
            or not item.get("products")
        ):
            blocked_ok.append(component_id)
        else:
            blocked_fail.append(component_id)

    risky_avoided_ok = []
    risky_avoided_fail = []
    for component_id in expected_risky_avoided:
        item = by_component.get(component_id)
        if not item or (
            item.get("commercial_eligible") is False
            or item.get("commercial_recommendation_blocked") is True
            or not item.get("products")
        ):
            risky_avoided_ok.append(component_id)
        else:
            risky_avoided_fail.append(component_id)

    eligible = _eligible_recommendations(with_products)
    eligible_with_products = [
        item for item in eligible
        if item.get("products")
    ]
    commercial_coverage = (
        round(len(eligible_with_products) / len(eligible), 4)
        if eligible
        else 1.0
    )

    packs = rerank_packs(recommendations, case["conditions"], result.get("alertas", []))
    selected_products = []
    if packs:
        selected_products = product_catalog.select_products_for_pack(packs[0].get("component_ids", []))
    pharmacies = {
        str(product.get("pharmacy"))
        for product in selected_products
        if product.get("pharmacy")
    }

    return {
        "case_id": case["case_id"],
        "model2_ranker_version": result.get("model2_ranker_version"),
        "top3_ids": "|".join(top3_ids),
        "expected_top3": "|".join(sorted(expected_top3)),
        "matched_top3": "|".join(matched_top3),
        "top3_hit": bool(not expected_top3 or matched_top3),
        "expected_blocked": "|".join(sorted(expected_blocked)),
        "blocked_ok": "|".join(sorted(blocked_ok)),
        "blocked_fail": "|".join(sorted(blocked_fail)),
        "blocking_ok": not blocked_fail,
        "expected_risky_avoided": "|".join(sorted(expected_risky_avoided)),
        "risky_avoided_ok": "|".join(sorted(risky_avoided_ok)),
        "risky_avoided_fail": "|".join(sorted(risky_avoided_fail)),
        "risk_avoidance_ok": not risky_avoided_fail,
        "eligible_components": len(eligible),
        "eligible_with_products": len(eligible_with_products),
        "commercial_coverage_evaluable": bool(eligible),
        "commercial_coverage": commercial_coverage,
        "pack_count": len(packs),
        "selected_product_count": len(selected_products),
        "selected_pharmacy_count": len(pharmacies),
        "pharmacy_diversity": round(len(pharmacies) / max(len(selected_products), 1), 4),
        "alert_count": len(result.get("alertas") or []),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evalúa Modelo 2 con casos fijos de producto.")
    parser.add_argument("--details-out", type=Path, default=REPORT_DIR / "01_model2_case_details.csv")
    parser.add_argument("--summary-out", type=Path, default=REPORT_DIR / "01_model2_summary.json")
    parser.add_argument("--min-top3-accuracy", type=float, default=0.80)
    parser.add_argument("--min-block-accuracy", type=float, default=1.00)
    parser.add_argument("--min-risk-avoidance-accuracy", type=float, default=1.00)
    parser.add_argument("--min-commercial-coverage", type=float, default=0.35)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    product_catalog = ProductCatalogService()
    details = [evaluate_case(case, product_catalog) for case in MODEL2_EVAL_CASES]

    cases_with_expected = [row for row in details if row["expected_top3"]]
    cases_with_blocking = [row for row in details if row["expected_blocked"]]
    cases_with_risk_avoidance = [row for row in details if row["expected_risky_avoided"]]
    cases_with_commercial_coverage = [row for row in details if row["commercial_coverage_evaluable"]]
    top3_accuracy = mean(row["top3_hit"] for row in cases_with_expected) if cases_with_expected else 1.0
    block_accuracy = mean(row["blocking_ok"] for row in cases_with_blocking) if cases_with_blocking else 1.0
    risk_avoidance_accuracy = (
        mean(row["risk_avoidance_ok"] for row in cases_with_risk_avoidance)
        if cases_with_risk_avoidance
        else 1.0
    )
    commercial_coverage = (
        mean(row["commercial_coverage"] for row in cases_with_commercial_coverage)
        if cases_with_commercial_coverage
        else 1.0
    )
    pharmacy_diversity = mean(row["pharmacy_diversity"] for row in details)

    errors = []
    if top3_accuracy < args.min_top3_accuracy:
        errors.append(f"top3_accuracy_below_threshold={top3_accuracy:.4f}<{args.min_top3_accuracy}")
    if block_accuracy < args.min_block_accuracy:
        errors.append(f"block_accuracy_below_threshold={block_accuracy:.4f}<{args.min_block_accuracy}")
    if risk_avoidance_accuracy < args.min_risk_avoidance_accuracy:
        errors.append(
            "risk_avoidance_accuracy_below_threshold="
            f"{risk_avoidance_accuracy:.4f}<{args.min_risk_avoidance_accuracy}"
        )
    if commercial_coverage < args.min_commercial_coverage:
        errors.append(
            f"commercial_coverage_below_threshold={commercial_coverage:.4f}<{args.min_commercial_coverage}"
        )

    summary = {
        "status": "failed" if errors else "passed",
        "errors": errors,
        "cases": len(details),
        "top3_accuracy": round(top3_accuracy, 4),
        "block_accuracy": round(block_accuracy, 4),
        "risk_avoidance_accuracy": round(risk_avoidance_accuracy, 4),
        "commercial_coverage_cases": len(cases_with_commercial_coverage),
        "commercial_coverage": round(commercial_coverage, 4),
        "pharmacy_diversity": round(pharmacy_diversity, 4),
        "details_path": str(args.details_out),
        "summary_path": str(args.summary_out),
    }

    write_csv(args.details_out, details)
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
