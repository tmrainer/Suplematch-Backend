#!/usr/bin/env python3
"""Construye un benchmark semi-curado desde NHANES para condition_mvp.

El benchmark usa reglas auditables sobre laboratorios reales ya normalizados
por `import_nhanes_condition_mvp_cases.py`. No usa las predicciones para
crear etiquetas, por lo que sirve para medir el modelo contra una referencia
externa parcial.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CASES = ROOT_DIR / "data/evaluation/condition_model/real_cases/nhanes_2017_2018_condition_cases.csv"
DEFAULT_PREDICTIONS = ROOT_DIR / "data/reports/condition_model/08_nhanes_2017_2018_predictions.csv"
EVALUATION_DIR = ROOT_DIR / "data/evaluation/condition_model"
REPORT_DIR = ROOT_DIR / "data/reports/condition_model"
DEFAULT_LABELS = EVALUATION_DIR / "nhanes_2017_2018_benchmark_labels.csv"
DEFAULT_DETAILS = REPORT_DIR / "09_nhanes_2017_2018_benchmark_details.csv"
DEFAULT_CASE_RESULTS = REPORT_DIR / "09_nhanes_2017_2018_benchmark_case_results.csv"
DEFAULT_CONDITION_METRICS = REPORT_DIR / "09_nhanes_2017_2018_benchmark_condition_metrics.csv"
DEFAULT_EVIDENCE_METRICS = REPORT_DIR / "09_nhanes_2017_2018_benchmark_evidence_group_metrics.csv"
DEFAULT_EXECUTIVE_REPORT = REPORT_DIR / "09_nhanes_2017_2018_benchmark_executive_report.csv"
DEFAULT_SUMMARY = REPORT_DIR / "09_nhanes_2017_2018_benchmark_summary.csv"

POSITIVE_LOW = {"low", "critical_low"}
POSITIVE_HIGH = {"high", "critical_high"}
NORMAL = {"normal"}
OBSERVED_STATUSES = POSITIVE_LOW | POSITIVE_HIGH | NORMAL
SAFETY_CONDITIONS = {"SAFETY_RENAL", "SAFETY_HEPATICA", "SAFETY_TIROIDEA"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT_DIR)) if path.is_relative_to(ROOT_DIR) else str(path)


def is_positive_low(value: str) -> bool:
    return str(value or "") in POSITIVE_LOW


def is_positive_high(value: str) -> bool:
    return str(value or "") in POSITIVE_HIGH


def is_observed(value: str) -> bool:
    return str(value or "") in OBSERVED_STATUSES


def make_label(
    case_id: str,
    condition: str,
    state: str,
    *,
    label_source: str,
    evidence_fields: list[str],
    rationale: str,
    confidence: float,
    evidence_group: str | None = None,
) -> dict[str, Any]:
    if evidence_group is None:
        if label_source.startswith("direct_") or label_source.startswith("plasma_"):
            evidence_group = "safety_only" if condition.startswith("SAFETY_") else "lab_only"
        elif label_source.startswith("dietary_"):
            evidence_group = "diet_only"
        elif "surrogate" in label_source:
            evidence_group = "surrogate"
        elif "missing" in label_source or "insufficient" in label_source:
            evidence_group = "unknown"
        else:
            evidence_group = "lab_or_diet"
    return {
        "case_id": case_id,
        "condition": condition,
        "expected_state": state,
        "label_source": label_source,
        "evidence_group": evidence_group,
        "evidence_fields": "|".join(evidence_fields),
        "rationale": rationale,
        "confidence": round(confidence, 3),
    }


def direct_low_label(case: dict[str, str], condition: str, field: str, *, label_source: str) -> dict[str, Any]:
    status = str(case.get(field, "missing"))
    if is_positive_low(status):
        return make_label(
            case["case_id"],
            condition,
            "positive",
            label_source=label_source,
            evidence_fields=[field],
            rationale=f"{field}={status}",
            confidence=0.95,
        )
    if status == "normal":
        return make_label(
            case["case_id"],
            condition,
            "negative",
            label_source=label_source,
            evidence_fields=[field],
            rationale=f"{field}=normal",
            confidence=0.9,
        )
    return make_label(
        case["case_id"],
        condition,
        "unknown",
        label_source="missing_lab",
        evidence_fields=[field],
        rationale=f"{field}=missing_or_not_labelable",
        confidence=0.0,
    )


def diet_low_label(
    case: dict[str, str],
    condition: str,
    field: str,
    *,
    label_source: str,
    confidence_positive: float = 0.78,
    confidence_negative: float = 0.75,
) -> dict[str, Any]:
    status = str(case.get(field, "missing"))
    if is_positive_low(status):
        return make_label(
            case["case_id"],
            condition,
            "positive",
            label_source=label_source,
            evidence_fields=[field],
            rationale=f"{field}={status}",
            confidence=confidence_positive,
        )
    if status == "normal":
        return make_label(
            case["case_id"],
            condition,
            "negative",
            label_source=label_source,
            evidence_fields=[field],
            rationale=f"{field}=normal",
            confidence=confidence_negative,
        )
    return make_label(
        case["case_id"],
        condition,
        "unknown",
        label_source="missing_dietary_evidence",
        evidence_fields=[field],
        rationale=f"{field}=missing_or_not_labelable",
        confidence=0.0,
    )


def direct_or_diet_low_label(
    case: dict[str, str],
    condition: str,
    lab_field: str,
    diet_field: str,
    *,
    lab_source: str,
    diet_source: str,
) -> dict[str, Any]:
    lab_status = str(case.get(lab_field, "missing"))
    if is_observed(lab_status):
        return direct_low_label(case, condition, lab_field, label_source=lab_source)
    return diet_low_label(case, condition, diet_field, label_source=diet_source)


def label_b12(case: dict[str, str]) -> dict[str, Any]:
    return direct_or_diet_low_label(
        case,
        "DEFICIT_B12",
        "lab_b12_status",
        "benchmark_diet_b12_status",
        lab_source="direct_b12_rule",
        diet_source="dietary_b12_intake_rule",
    )


def label_iron(case: dict[str, str]) -> dict[str, Any]:
    ferritin = str(case.get("lab_ferritin_status", "missing"))
    hemoglobin = str(case.get("lab_hemoglobin_status", "missing"))
    if is_positive_low(ferritin):
        return make_label(
            case["case_id"],
            "DEFICIT_HIERRO",
            "positive",
            label_source="direct_ferritin_rule",
            evidence_fields=["lab_ferritin_status"],
            rationale=f"lab_ferritin_status={ferritin}",
            confidence=0.95,
        )
    if ferritin == "normal" and hemoglobin == "normal":
        return make_label(
            case["case_id"],
            "DEFICIT_HIERRO",
            "negative",
            label_source="direct_ferritin_rule",
            evidence_fields=["lab_ferritin_status", "lab_hemoglobin_status"],
            rationale="ferritin_and_hemoglobin_normal",
            confidence=0.9,
        )
    if ferritin == "missing" and is_positive_low(hemoglobin):
        return make_label(
            case["case_id"],
            "DEFICIT_HIERRO",
            "positive",
            label_source="hemoglobin_surrogate_rule",
            evidence_fields=["lab_hemoglobin_status"],
            rationale=f"lab_hemoglobin_status={hemoglobin}; ferritin_missing",
            confidence=0.65,
        )
    return make_label(
        case["case_id"],
        "DEFICIT_HIERRO",
        "unknown",
        label_source="insufficient_iron_evidence",
        evidence_fields=["lab_ferritin_status", "lab_hemoglobin_status"],
        rationale=f"ferritin={ferritin}; hemoglobin={hemoglobin}",
        confidence=0.0,
    )


def label_bone_health(case: dict[str, str]) -> dict[str, Any]:
    vitamin_d = str(case.get("lab_vitamin_d_status", "missing"))
    calcium = str(case.get("lab_calcium_status", "missing"))
    if is_positive_low(vitamin_d) or is_positive_low(calcium):
        evidence = []
        if is_positive_low(vitamin_d):
            evidence.append("lab_vitamin_d_status")
        if is_positive_low(calcium):
            evidence.append("lab_calcium_status")
        return make_label(
            case["case_id"],
            "RIESGO_SALUD_OSEA",
            "positive",
            label_source="direct_bone_lab_rule",
            evidence_fields=evidence,
            rationale=f"vitamin_d={vitamin_d}; calcium={calcium}",
            confidence=0.85,
        )
    if vitamin_d == "normal" and calcium == "normal":
        return make_label(
            case["case_id"],
            "RIESGO_SALUD_OSEA",
            "negative",
            label_source="direct_bone_lab_rule",
            evidence_fields=["lab_vitamin_d_status", "lab_calcium_status"],
            rationale="vitamin_d_and_calcium_normal",
            confidence=0.8,
        )
    return make_label(
        case["case_id"],
        "RIESGO_SALUD_OSEA",
        "unknown",
        label_source="insufficient_bone_evidence",
        evidence_fields=["lab_vitamin_d_status", "lab_calcium_status"],
        rationale=f"vitamin_d={vitamin_d}; calcium={calcium}",
        confidence=0.0,
    )


def label_calcium(case: dict[str, str]) -> dict[str, Any]:
    return direct_or_diet_low_label(
        case,
        "DEFICIT_CALCIO",
        "lab_calcium_status",
        "benchmark_diet_calcium_status",
        lab_source="direct_calcium_rule",
        diet_source="dietary_calcium_intake_rule",
    )


def label_folate(case: dict[str, str]) -> dict[str, Any]:
    return direct_or_diet_low_label(
        case,
        "DEFICIT_FOLATO",
        "lab_folate_status",
        "benchmark_diet_folate_status",
        lab_source="direct_folate_rule",
        diet_source="dietary_folate_intake_rule",
    )


def label_magnesium(case: dict[str, str]) -> dict[str, Any]:
    return direct_or_diet_low_label(
        case,
        "DEFICIT_MAGNESIO",
        "lab_magnesium_status",
        "benchmark_diet_magnesium_status",
        lab_source="direct_magnesium_rule",
        diet_source="dietary_magnesium_intake_rule",
    )


def label_zinc(case: dict[str, str]) -> dict[str, Any]:
    return direct_or_diet_low_label(
        case,
        "DEFICIT_ZINC",
        "lab_zinc_status",
        "benchmark_diet_zinc_status",
        lab_source="direct_zinc_rule",
        diet_source="dietary_zinc_intake_rule",
    )


def label_vitamin_c(case: dict[str, str]) -> dict[str, Any]:
    status = str(case.get("benchmark_lab_vitamin_c_status", "missing"))
    if is_positive_low(status):
        return make_label(
            case["case_id"],
            "RIESGO_VITAMINA_C_BAJA",
            "positive",
            label_source="plasma_vitamin_c_rule",
            evidence_fields=["benchmark_lab_vitamin_c_status"],
            rationale=f"benchmark_lab_vitamin_c_status={status}",
            confidence=0.8,
        )
    if status == "normal":
        return make_label(
            case["case_id"],
            "RIESGO_VITAMINA_C_BAJA",
            "negative",
            label_source="plasma_vitamin_c_rule",
            evidence_fields=["benchmark_lab_vitamin_c_status"],
            rationale="benchmark_lab_vitamin_c_status=normal",
        confidence=0.75,
    )
    diet_status = str(case.get("benchmark_diet_vitamin_c_status", "missing"))
    if is_positive_low(diet_status):
        return make_label(
            case["case_id"],
            "RIESGO_VITAMINA_C_BAJA",
            "positive",
            label_source="dietary_vitamin_c_intake_rule",
            evidence_fields=["benchmark_diet_vitamin_c_status"],
            rationale=f"benchmark_diet_vitamin_c_status={diet_status}; lab_missing",
            confidence=0.78,
        )
    if diet_status == "normal":
        return make_label(
            case["case_id"],
            "RIESGO_VITAMINA_C_BAJA",
            "negative",
            label_source="dietary_vitamin_c_intake_rule",
            evidence_fields=["benchmark_diet_vitamin_c_status"],
            rationale="benchmark_diet_vitamin_c_status=normal; lab_missing",
            confidence=0.75,
        )
    return make_label(
        case["case_id"],
        "RIESGO_VITAMINA_C_BAJA",
        "unknown",
        label_source="missing_lab",
        evidence_fields=["benchmark_lab_vitamin_c_status"],
        rationale="vitamin_c_lab_missing",
        confidence=0.0,
    )


def label_protein(case: dict[str, str]) -> dict[str, Any]:
    return diet_low_label(
        case,
        "RIESGO_PROTEINA_INSUFICIENTE",
        "benchmark_diet_protein_status",
        label_source="dietary_protein_intake_rule",
    )


def label_omega3(case: dict[str, str]) -> dict[str, Any]:
    return diet_low_label(
        case,
        "RIESGO_OMEGA3_BAJO",
        "benchmark_diet_omega3_status",
        label_source="dietary_omega3_intake_rule",
    )


def label_dyslipidemia(case: dict[str, str]) -> dict[str, Any]:
    fields = [
        "lab_total_cholesterol_status",
        "lab_ldl_status",
        "lab_hdl_status",
        "lab_triglycerides_status",
    ]
    statuses = {field: str(case.get(field, "missing")) for field in fields}
    abnormal_fields = [
        field
        for field, status in statuses.items()
        if is_positive_high(status) or (field == "lab_hdl_status" and is_positive_low(status))
    ]
    observed_fields = [field for field, status in statuses.items() if is_observed(status)]
    if abnormal_fields:
        return make_label(
            case["case_id"],
            "RIESGO_DISLIPIDEMIA",
            "positive",
            label_source="direct_lipid_panel_rule",
            evidence_fields=abnormal_fields,
            rationale="; ".join(f"{field}={statuses[field]}" for field in abnormal_fields),
            confidence=0.9,
        )
    if len(observed_fields) >= 3 and all(statuses[field] == "normal" for field in observed_fields):
        return make_label(
            case["case_id"],
            "RIESGO_DISLIPIDEMIA",
            "negative",
            label_source="direct_lipid_panel_rule",
            evidence_fields=observed_fields,
            rationale="available_lipid_markers_normal",
            confidence=0.8,
        )
    return make_label(
        case["case_id"],
        "RIESGO_DISLIPIDEMIA",
        "unknown",
        label_source="insufficient_lipid_panel",
        evidence_fields=fields,
        rationale="lipid_panel_incomplete_without_abnormal_marker",
        confidence=0.0,
    )


def label_glucose(case: dict[str, str]) -> dict[str, Any]:
    status = str(case.get("lab_glucose_status", "missing"))
    if is_positive_high(status):
        return make_label(
            case["case_id"],
            "RIESGO_METABOLICO_GLUCOSA",
            "positive",
            label_source="direct_glucose_rule",
            evidence_fields=["lab_glucose_status"],
            rationale=f"lab_glucose_status={status}",
            confidence=0.9,
        )
    if status == "normal":
        return make_label(
            case["case_id"],
            "RIESGO_METABOLICO_GLUCOSA",
            "negative",
            label_source="direct_glucose_rule",
            evidence_fields=["lab_glucose_status"],
            rationale="lab_glucose_status=normal",
            confidence=0.85,
        )
    return make_label(
        case["case_id"],
        "RIESGO_METABOLICO_GLUCOSA",
        "unknown",
        label_source="missing_lab",
        evidence_fields=["lab_glucose_status"],
        rationale=f"lab_glucose_status={status}",
        confidence=0.0,
    )


def label_renal(case: dict[str, str]) -> dict[str, Any]:
    creatinine = str(case.get("lab_creatinine_status", "missing"))
    egfr = str(case.get("lab_egfr_status", "missing"))
    if is_positive_high(creatinine) or is_positive_low(egfr):
        fields = []
        if is_positive_high(creatinine):
            fields.append("lab_creatinine_status")
        if is_positive_low(egfr):
            fields.append("lab_egfr_status")
        return make_label(
            case["case_id"],
            "SAFETY_RENAL",
            "positive",
            label_source="direct_renal_safety_rule",
            evidence_fields=fields,
            rationale=f"creatinine={creatinine}; egfr={egfr}",
            confidence=0.95,
        )
    if creatinine == "normal" and egfr == "normal":
        return make_label(
            case["case_id"],
            "SAFETY_RENAL",
            "negative",
            label_source="direct_renal_safety_rule",
            evidence_fields=["lab_creatinine_status", "lab_egfr_status"],
            rationale="creatinine_and_egfr_normal",
            confidence=0.9,
        )
    return make_label(
        case["case_id"],
        "SAFETY_RENAL",
        "unknown",
        label_source="insufficient_renal_evidence",
        evidence_fields=["lab_creatinine_status", "lab_egfr_status"],
        rationale=f"creatinine={creatinine}; egfr={egfr}",
        confidence=0.0,
    )


def label_hepatic(case: dict[str, str]) -> dict[str, Any]:
    alt = str(case.get("lab_alt_status", "missing"))
    ast = str(case.get("lab_ast_status", "missing"))
    if is_positive_high(alt) or is_positive_high(ast):
        fields = []
        if is_positive_high(alt):
            fields.append("lab_alt_status")
        if is_positive_high(ast):
            fields.append("lab_ast_status")
        return make_label(
            case["case_id"],
            "SAFETY_HEPATICA",
            "positive",
            label_source="direct_liver_safety_rule",
            evidence_fields=fields,
            rationale=f"alt={alt}; ast={ast}",
            confidence=0.95,
        )
    if alt == "normal" and ast == "normal":
        return make_label(
            case["case_id"],
            "SAFETY_HEPATICA",
            "negative",
            label_source="direct_liver_safety_rule",
            evidence_fields=["lab_alt_status", "lab_ast_status"],
            rationale="alt_and_ast_normal",
            confidence=0.9,
        )
    return make_label(
        case["case_id"],
        "SAFETY_HEPATICA",
        "unknown",
        label_source="insufficient_liver_evidence",
        evidence_fields=["lab_alt_status", "lab_ast_status"],
        rationale=f"alt={alt}; ast={ast}",
        confidence=0.0,
    )


def label_thyroid_safety(case: dict[str, str]) -> dict[str, Any]:
    status = str(case.get("lab_tsh_status", "missing"))
    if is_positive_low(status) or is_positive_high(status):
        return make_label(
            case["case_id"],
            "SAFETY_TIROIDEA",
            "positive",
            label_source="direct_tsh_rule",
            evidence_fields=["lab_tsh_status"],
            rationale=f"lab_tsh_status={status}",
            confidence=0.9,
        )
    if status == "normal":
        return make_label(
            case["case_id"],
            "SAFETY_TIROIDEA",
            "negative",
            label_source="direct_tsh_rule",
            evidence_fields=["lab_tsh_status"],
            rationale="lab_tsh_status=normal",
            confidence=0.85,
        )
    return make_label(
        case["case_id"],
        "SAFETY_TIROIDEA",
        "unknown",
        label_source="missing_lab",
        evidence_fields=["lab_tsh_status"],
        rationale="lab_tsh_status=missing",
        confidence=0.0,
    )


def unknown_label(case: dict[str, str], condition: str, reason: str, fields: list[str]) -> dict[str, Any]:
    return make_label(
        case["case_id"],
        condition,
        "unknown",
        label_source=reason,
        evidence_fields=fields,
        rationale="condition_not_labelable_from_nhanes_2017_2018_fields",
        confidence=0.0,
    )


def build_labels(case: dict[str, str]) -> list[dict[str, Any]]:
    return [
        direct_low_label(case, "DEFICIT_VIT_D", "lab_vitamin_d_status", label_source="direct_25ohd_rule"),
        label_b12(case),
        label_iron(case),
        label_magnesium(case),
        unknown_label(case, "BAJA_INMUNIDAD", "missing_zinc_or_clinical_infection_label", ["lab_zinc_status"]),
        label_bone_health(case),
        unknown_label(case, "ESTRES_SUENO", "missing_sleep_stress_instrument", ["problemas_sueno", "estres_alto"]),
        unknown_label(case, "RENDIMIENTO_DEPORTIVO", "missing_activity_performance_label", ["nivel_actividad", "meta_rendimiento"]),
        label_folate(case),
        label_zinc(case),
        label_calcium(case),
        label_vitamin_c(case),
        label_omega3(case),
        label_protein(case),
        unknown_label(case, "RIESGO_CABELLO_PIEL_UNAS", "missing_dermatologic_label", ["caida_cabello", "piel_seca", "unas_quebradizas"]),
        label_glucose(case),
        label_dyslipidemia(case),
        label_renal(case),
        label_hepatic(case),
        label_thyroid_safety(case),
    ]


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "t", "yes", "si", "sí"}


def outcome(expected_state: str, predicted_positive: bool) -> str:
    if expected_state == "positive":
        return "tp" if predicted_positive else "fn"
    if expected_state == "negative":
        return "fp" if predicted_positive else "tn"
    return "unknown_predicted_positive" if predicted_positive else "unknown_predicted_negative"


def safe_metric(numerator: int, denominator: int) -> float | str:
    if denominator == 0:
        return ""
    return round(numerator / denominator, 4)


def brier_score(rows: list[dict[str, Any]]) -> float | str:
    scored = []
    for row in rows:
        expected = 1.0 if row["expected_state"] == "positive" else 0.0 if row["expected_state"] == "negative" else None
        if expected is None:
            continue
        scored.append((float(row["probability"]) - expected) ** 2)
    if not scored:
        return ""
    return round(sum(scored) / len(scored), 4)


def metric_bucket(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tp = sum(1 for row in rows if row["outcome"] == "tp")
    fp = sum(1 for row in rows if row["outcome"] == "fp")
    tn = sum(1 for row in rows if row["outcome"] == "tn")
    fn = sum(1 for row in rows if row["outcome"] == "fn")
    positives = tp + fn
    negatives = tn + fp
    precision = safe_metric(tp, tp + fp)
    if precision == "" and positives:
        precision = 0.0
    recall = safe_metric(tp, positives)
    specificity = safe_metric(tn, negatives)
    f1 = ""
    if precision != "" and recall != "":
        f1 = round(2 * precision * recall / (precision + recall), 4) if (precision + recall) > 0 else 0.0
    return {
        "expected_positive": positives,
        "expected_negative": negatives,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1": f1,
        "brier_score": brier_score(rows),
        "mean_probability_positive_labels": safe_metric(
            sum(float(row["probability"]) for row in rows if row["expected_state"] == "positive"),
            positives,
        ),
        "mean_probability_negative_labels": safe_metric(
            sum(float(row["probability"]) for row in rows if row["expected_state"] == "negative"),
            negatives,
        ),
    }


def false_negative_risk(metric: dict[str, Any]) -> str:
    positives = int(metric["expected_positive"])
    recall = metric["recall"]
    if positives == 0 or recall == "":
        return "no_evaluable"
    recall_value = float(recall)
    if recall_value < 0.50 and positives >= 20:
        return "alto"
    if recall_value < 0.80:
        return "medio"
    return "bajo"


def condition_status(metric: dict[str, Any]) -> str:
    coverage = float(metric["coverage"]) if metric["coverage"] != "" else 0.0
    if coverage < 0.10:
        return "no_evaluable"
    recall = metric["recall"]
    specificity = metric["specificity"]
    if recall != "" and specificity != "" and float(recall) >= 0.80 and float(specificity) >= 0.90:
        return "listo"
    return "necesita_mejora"


def evaluate(labels: list[dict[str, Any]], predictions: list[dict[str, str]], min_confidence: float, generated_at: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    prediction_by_key = {(row["case_id"], row["condition"]): row for row in predictions}
    details = []
    for label in labels:
        prediction = prediction_by_key.get((label["case_id"], label["condition"]))
        if not prediction:
            continue
        predicted_positive = parse_bool(prediction["positive"])
        label_confidence = float(label["confidence"])
        evaluated = label["expected_state"] in {"positive", "negative"} and label_confidence >= min_confidence
        row_outcome = outcome(label["expected_state"], predicted_positive) if evaluated else "not_evaluated"
        details.append(
            {
                "generated_at": generated_at,
                **label,
                "evaluated": evaluated,
                "outcome": row_outcome,
                "predicted_positive": predicted_positive,
                "probability": prediction["probability"],
                "threshold": prediction["threshold"],
                "model_evidence_level": prediction["evidence_level"],
                "model_drivers": prediction["drivers"],
                "model_missing_data": prediction["missing_data"],
                "model_safety_flag": prediction["safety_flag"],
            }
        )

    case_buckets: dict[str, dict[str, Any]] = {}
    for row in details:
        bucket = case_buckets.setdefault(
            row["case_id"],
            {
                "generated_at": generated_at,
                "case_id": row["case_id"],
                "evaluated_conditions": 0,
                "unknown_conditions": 0,
                "tp": 0,
                "fp": 0,
                "tn": 0,
                "fn": 0,
            },
        )
        if row["expected_state"] == "unknown":
            bucket["unknown_conditions"] += 1
        if row["evaluated"]:
            bucket["evaluated_conditions"] += 1
            if row["outcome"] in {"tp", "fp", "tn", "fn"}:
                bucket[row["outcome"]] += 1
    case_results = []
    for bucket in case_buckets.values():
        errors = bucket["fp"] + bucket["fn"]
        bucket["passed_all_evaluated"] = errors == 0
        bucket["error_count"] = errors
        case_results.append(bucket)

    condition_metrics = []
    conditions = sorted({row["condition"] for row in labels})
    for condition in conditions:
        rows = [row for row in details if row["condition"] == condition]
        evaluated_rows = [row for row in rows if row["evaluated"]]
        bucket = metric_bucket(evaluated_rows)
        condition_metrics.append(
            {
                "generated_at": generated_at,
                "condition": condition,
                "total_cases": len(rows),
                "evaluated_cases": len(evaluated_rows),
                "coverage": safe_metric(len(evaluated_rows), len(rows)),
                "unknown_cases": sum(1 for row in rows if row["expected_state"] == "unknown"),
                **bucket,
            }
        )

    evidence_group_metrics = []
    for condition in conditions:
        condition_rows = [row for row in details if row["condition"] == condition and row["evaluated"]]
        for group in sorted({row["evidence_group"] for row in condition_rows}):
            group_rows = [row for row in condition_rows if row["evidence_group"] == group]
            evidence_group_metrics.append(
                {
                    "generated_at": generated_at,
                    "condition": condition,
                    "evidence_group": group,
                    "evaluated_cases": len(group_rows),
                    **metric_bucket(group_rows),
                }
            )

    executive_report = []
    for metric in condition_metrics:
        risk = false_negative_risk(metric)
        status = condition_status(metric)
        executive_report.append(
            {
                "generated_at": generated_at,
                "condition": metric["condition"],
                "coverage": metric["coverage"],
                "precision": metric["precision"],
                "recall": metric["recall"],
                "specificity": metric["specificity"],
                "f1": metric["f1"],
                "false_negative_risk": risk,
                "status": status,
                "expected_positive": metric["expected_positive"],
                "expected_negative": metric["expected_negative"],
                "fn": metric["fn"],
                "fp": metric["fp"],
            }
        )

    evaluated_details = [row for row in details if row["evaluated"]]
    case_pass_rate = safe_metric(sum(1 for row in case_results if row["passed_all_evaluated"]), len(case_results))
    summary = [
        {
            "generated_at": generated_at,
            "cases": len(case_results),
            "conditions": len(conditions),
            "labels": len(labels),
            "evaluated_labels": len(evaluated_details),
            "unknown_labels": sum(1 for row in labels if row["expected_state"] == "unknown"),
            "benchmark_coverage": safe_metric(len(evaluated_details), len(labels)),
            "min_confidence": min_confidence,
            "case_pass_rate": case_pass_rate,
            "tp": sum(1 for row in evaluated_details if row["outcome"] == "tp"),
            "fp": sum(1 for row in evaluated_details if row["outcome"] == "fp"),
            "tn": sum(1 for row in evaluated_details if row["outcome"] == "tn"),
            "fn": sum(1 for row in evaluated_details if row["outcome"] == "fn"),
            "macro_f1_evaluated_conditions": round(
                sum(float(row["f1"]) for row in condition_metrics if row["f1"] != "")
                / max(1, sum(1 for row in condition_metrics if row["f1"] != "")),
                4,
            ),
            "clinical_validation": "rule_derived_benchmark_not_diagnosis",
        }
    ]
    return details, case_results, condition_metrics, evidence_group_metrics, executive_report, summary


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def run(args: argparse.Namespace) -> None:
    cases_path = Path(args.cases)
    predictions_path = Path(args.predictions)
    labels_path = Path(args.labels)
    details_path = Path(args.details)
    case_results_path = Path(args.case_results)
    condition_metrics_path = Path(args.condition_metrics)
    evidence_metrics_path = Path(args.evidence_metrics)
    executive_report_path = Path(args.executive_report)
    summary_path = Path(args.summary)
    generated_at = utc_now()

    cases = read_csv(cases_path)
    predictions = read_csv(predictions_path)
    if not cases:
        raise SystemExit(f"No hay casos NHANES en {cases_path}")
    if not predictions:
        raise SystemExit(f"No hay predicciones NHANES en {predictions_path}")

    labels: list[dict[str, Any]] = []
    for case in cases:
        labels.extend(build_labels(case))

    details, case_results, condition_metrics, evidence_group_metrics, executive_report, summary = evaluate(
        labels,
        predictions,
        min_confidence=args.min_confidence,
        generated_at=generated_at,
    )

    labels_path.parent.mkdir(parents=True, exist_ok=True)
    details_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(labels).to_csv(labels_path, index=False)
    pd.DataFrame(details).to_csv(details_path, index=False)
    pd.DataFrame(case_results).to_csv(case_results_path, index=False)
    pd.DataFrame(condition_metrics).to_csv(condition_metrics_path, index=False)
    pd.DataFrame(evidence_group_metrics).to_csv(evidence_metrics_path, index=False)
    pd.DataFrame(executive_report).to_csv(executive_report_path, index=False)
    pd.DataFrame(summary).to_csv(summary_path, index=False)

    print("Benchmark NHANES condition_mvp completado")
    print(f"  casos: {len(cases)}")
    print(f"  labels: {len(labels)}")
    print(f"  evaluados: {summary[0]['evaluated_labels']}")
    print(f"  cobertura: {summary[0]['benchmark_coverage']}")
    print(f"  macro_f1: {summary[0]['macro_f1_evaluated_conditions']}")
    print(f"  labels_csv: {labels_path}")
    print(f"  metricas: {condition_metrics_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Construye/evalua benchmark NHANES semi-curado para condition_mvp.")
    parser.add_argument("--cases", default=str(DEFAULT_CASES), help="CSV de casos NHANES anonimos.")
    parser.add_argument("--predictions", default=str(DEFAULT_PREDICTIONS), help="CSV de predicciones NHANES.")
    parser.add_argument("--labels", default=str(DEFAULT_LABELS), help="CSV de labels rule-derived.")
    parser.add_argument("--details", default=str(DEFAULT_DETAILS), help="CSV detalle label vs prediccion.")
    parser.add_argument("--case-results", default=str(DEFAULT_CASE_RESULTS), help="CSV resumen por caso.")
    parser.add_argument("--condition-metrics", default=str(DEFAULT_CONDITION_METRICS), help="CSV metricas por condicion.")
    parser.add_argument("--evidence-metrics", default=str(DEFAULT_EVIDENCE_METRICS), help="CSV metricas por grupo de evidencia.")
    parser.add_argument("--executive-report", default=str(DEFAULT_EXECUTIVE_REPORT), help="CSV ejecutivo por condicion.")
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY), help="CSV resumen global.")
    parser.add_argument("--min-confidence", type=float, default=0.75, help="Confianza minima para evaluar una etiqueta.")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
