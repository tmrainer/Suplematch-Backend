import csv
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE = ROOT / "data" / "knowledge"
EVALUATION = ROOT / "data" / "evaluation" / "condition_model"
REAL_CASES = ROOT / "data" / "evaluation" / "condition_model" / "real_cases"
sys.path.insert(0, str(ROOT / "scripts" / "training"))


def _read_csv(name: str):
    with (KNOWLEDGE / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _split(value: str):
    return [item for item in (value or "").split("|") if item]


def test_medical_knowledge_uses_only_allowed_official_domains():
    allowed = {row["domain"] for row in _read_csv("source_domains.csv")}

    for source in _read_csv("sources.csv"):
        domain = source["url"].split("/")[2].replace("www.", "")
        assert any(domain == item or domain.endswith(f".{item}") for item in allowed)


def test_condition_rules_have_sources_and_training_labels():
    sources = {source["source_id"] for source in _read_csv("sources.csv")}
    conditions = _read_csv("conditions.csv")
    labels = {condition["condition_code"] for condition in conditions}
    rules = _read_csv("condition_rules.csv")
    rules_by_condition = {}
    for rule in rules:
        rules_by_condition.setdefault(rule["condition_code"], []).append(rule)

    for condition in conditions:
        assert condition["condition_code"] in labels
        assert condition["source_ids"]
        assert set(_split(condition["source_ids"])).issubset(sources)
        assert rules_by_condition[condition["condition_code"]]
        for rule in rules_by_condition[condition["condition_code"]]:
            assert rule["field"]
            assert rule["operator"]
            assert rule["weight"]


def test_condition_data_requirements_cover_all_conditions():
    labels = {condition["condition_code"] for condition in _read_csv("conditions.csv")}
    requirements = _read_csv("condition_data_requirements.csv")
    requirement_labels = {row["condition_code"] for row in requirements}

    assert requirement_labels == labels
    for row in requirements:
        assert row["kind"] in {"recommendable", "safety_context", "safety"}
        assert row["interpretation"]
        assert row["needs_survey_fields"] or row["needs_lab_fields"] or row["needs_safety_fields"]


def test_component_evidence_profiles_have_official_sources() -> None:
    sources = {source["source_id"] for source in _read_csv("sources.csv")}
    profiles = _read_csv("component_evidence_profiles.csv")

    assert len(profiles) >= 30
    for profile in profiles:
        assert profile["component"]
        assert profile["safety_level"] in {"low", "moderate", "high"}
        assert profile["source_ids"]
        assert set(_split(profile["source_ids"])).issubset(sources)
        assert profile["dose_guidance"]
        assert profile["rationale"]


def test_condition_component_links_include_enriched_evidence_contract() -> None:
    sources = {source["source_id"] for source in _read_csv("sources.csv")}
    links = _read_csv("condition_component_links.csv")

    assert len(links) >= 50
    for link in links:
        assert link["condition_code"]
        assert link["component"]
        assert link["evidence_strength"] in {"high", "moderate", "low_moderate", "contextual"}
        assert link["evidence_type"]
        assert link["recommendation_role"] in {
            "primary",
            "primary_with_lab",
            "supportive",
            "supportive_with_lab",
            "safety_context",
        }
        assert link["requires_lab"] in {"no", "optional", "preferred", "required"}
        assert link["risk_level"] in {"low", "low_moderate", "moderate", "moderate_high", "high"}
        assert link["source_quality"]
        assert link["source_ids"]
        assert set(_split(link["source_ids"])).issubset(sources)
        assert link["rationale"]


def test_component_guidance_interactions_and_claims_have_sources() -> None:
    sources = {source["source_id"] for source in _read_csv("sources.csv")}

    guidance = _read_csv("component_life_stage_guidance.csv")
    assert len(guidance) >= 55
    for row in guidance:
        assert row["component"]
        assert row["source_ids"]
        assert set(_split(row["source_ids"])).issubset(sources)
        assert row["guidance_note"]
        assert row["reference_type"] in {"RDA", "AI", "no_dri"}

    interactions = _read_csv("component_interaction_rules.csv")
    assert len(interactions) >= 25
    for row in interactions:
        assert row["component"]
        assert row["severity"] in {"low", "medium", "high"}
        assert row["action"]
        assert row["message"]
        assert set(_split(row["source_ids"])).issubset(sources)

    claims = _read_csv("component_claim_evidence.csv")
    assert len(claims) >= 25
    for row in claims:
        assert row["component"]
        assert row["claim"]
        assert row["evidence_level"]
        assert row["display_note"]
        assert set(_split(row["source_ids"])).issubset(sources)


def test_condition_rules_use_declared_model_features():
    feature_contract = ROOT / "data" / "training" / "condition_model" / "condition_feature_contract.csv"
    assert feature_contract.exists()

    with feature_contract.open(encoding="utf-8", newline="") as handle:
        features = {row["feature"] for row in csv.DictReader(handle)}

    for rule in _read_csv("condition_rules.csv"):
        assert rule["field"] in features


def test_condition_golden_cases_cover_all_labels_and_use_valid_expectations():
    labels = {condition["condition_code"] for condition in _read_csv("conditions.csv")}
    cases_path = EVALUATION / "golden_cases.csv"
    assert cases_path.exists()

    with cases_path.open(encoding="utf-8", newline="") as handle:
        cases = list(csv.DictReader(handle))

    assert len(cases) >= 30
    case_ids = [case["case_id"] for case in cases]
    assert len(case_ids) == len(set(case_ids))

    expected_positive = set()
    expected_negative = set()
    for case in cases:
        positives = set(_split(case["expected_positive"]))
        negatives = set(_split(case["expected_negative"]))
        assert positives or negatives
        assert positives.isdisjoint(negatives)
        assert positives.issubset(labels)
        assert negatives.issubset(labels)
        expected_positive.update(positives)
        expected_negative.update(negatives)

    assert expected_positive == labels
    assert {"SAFETY_RENAL", "SAFETY_HEPATICA", "SAFETY_TIROIDEA"}.issubset(expected_negative)


def test_condition_holdout_report_contains_at_least_1000_cases():
    summary_path = ROOT / "data" / "reports" / "condition_model" / "06_holdout_1000_summary.csv"
    condition_path = ROOT / "data" / "reports" / "condition_model" / "06_holdout_1000_condition_metrics.csv"
    cases_path = ROOT / "data" / "evaluation" / "condition_model" / "holdout_1000_cases.csv"

    assert summary_path.exists()
    assert condition_path.exists()
    assert cases_path.exists()

    with summary_path.open(encoding="utf-8", newline="") as handle:
        summary = next(csv.DictReader(handle))
    assert int(summary["rows"]) >= 1000
    assert float(summary["f1_macro"]) >= 0.85
    assert float(summary["hamming_loss"]) <= 0.05

    labels = {condition["condition_code"] for condition in _read_csv("conditions.csv")}
    with condition_path.open(encoding="utf-8", newline="") as handle:
        condition_metrics = {row["condition"] for row in csv.DictReader(handle)}
    assert condition_metrics == labels


def test_real_case_demo_outputs_are_anonymized():
    anonymized_path = REAL_CASES / "demo_real_cases_anonymized.csv"
    predictions_path = ROOT / "data" / "reports" / "condition_model" / "07_demo_real_cases_predictions.csv"
    summary_path = ROOT / "data" / "reports" / "condition_model" / "07_demo_real_cases_summary.csv"
    assert anonymized_path.exists()
    assert predictions_path.exists()
    assert summary_path.exists()

    text = anonymized_path.read_text(encoding="utf-8")
    assert "DEMO-001" not in text
    assert "DEMO-002" not in text

    with anonymized_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert all(row["case_id"].startswith("real_") for row in rows)
    assert "source_case_id" not in rows[0]

    with summary_path.open(encoding="utf-8", newline="") as handle:
        summary = next(csv.DictReader(handle))
    assert int(summary["accepted_cases"]) == 2
    assert int(summary["rejected_cases"]) == 0


def test_nhanes_public_cases_are_anonymized_and_predicted():
    cases_path = REAL_CASES / "nhanes_2017_2018_condition_cases.csv"
    predictions_path = ROOT / "data" / "reports" / "condition_model" / "08_nhanes_2017_2018_predictions.csv"
    summary_path = ROOT / "data" / "reports" / "condition_model" / "08_nhanes_2017_2018_summary.csv"
    condition_summary_path = ROOT / "data" / "reports" / "condition_model" / "08_nhanes_2017_2018_condition_summary.csv"
    source_manifest_path = ROOT / "data" / "reports" / "condition_model" / "08_nhanes_2017_2018_source_manifest.csv"

    for path in [cases_path, predictions_path, summary_path, condition_summary_path, source_manifest_path]:
        assert path.exists()

    text = cases_path.read_text(encoding="utf-8")
    assert "SEQN" not in text
    assert "NHANES-2017-2018-" not in text

    with cases_path.open(encoding="utf-8", newline="") as handle:
        cases = list(csv.DictReader(handle))
    assert len(cases) >= 1000
    assert all(row["case_id"].startswith("nhanes_") for row in cases)
    assert "source_case_id" not in cases[0]
    assert "SEQN" not in cases[0]

    labels = {condition["condition_code"] for condition in _read_csv("conditions.csv")}
    with predictions_path.open(encoding="utf-8", newline="") as handle:
        predictions = list(csv.DictReader(handle))
    assert len(predictions) == len(cases) * len(labels)
    assert {row["expected_state"] for row in predictions} == {"unreviewed"}

    with summary_path.open(encoding="utf-8", newline="") as handle:
        summary = next(csv.DictReader(handle))
    assert int(summary["accepted_cases"]) >= 1000
    assert summary["source"] == "CDC NHANES public-use 2017-2018"
    assert summary["seqn_in_output"] == "False"
    assert summary["clinical_validation"] == "not_clinically_validated"

    with condition_summary_path.open(encoding="utf-8", newline="") as handle:
        condition_summary = {row["condition"] for row in csv.DictReader(handle)}
    assert condition_summary == labels

    with source_manifest_path.open(encoding="utf-8", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    assert len(source_rows) >= 10
    assert all(row["url"].startswith("https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/") for row in source_rows)
    assert all(row["status"] in {"cached", "downloaded"} for row in source_rows)


def test_nhanes_benchmark_has_rule_derived_labels_and_metrics():
    labels_path = ROOT / "data" / "evaluation" / "condition_model" / "nhanes_2017_2018_benchmark_labels.csv"
    details_path = ROOT / "data" / "reports" / "condition_model" / "09_nhanes_2017_2018_benchmark_details.csv"
    summary_path = ROOT / "data" / "reports" / "condition_model" / "09_nhanes_2017_2018_benchmark_summary.csv"
    condition_metrics_path = ROOT / "data" / "reports" / "condition_model" / "09_nhanes_2017_2018_benchmark_condition_metrics.csv"
    case_results_path = ROOT / "data" / "reports" / "condition_model" / "09_nhanes_2017_2018_benchmark_case_results.csv"

    for path in [labels_path, details_path, summary_path, condition_metrics_path, case_results_path]:
        assert path.exists()

    text = labels_path.read_text(encoding="utf-8")
    assert "SEQN" not in text
    assert "NHANES-2017-2018-" not in text

    with labels_path.open(encoding="utf-8", newline="") as handle:
        labels = list(csv.DictReader(handle))
    assert len(labels) >= 20_000
    assert {"positive", "negative", "unknown"}.issubset({row["expected_state"] for row in labels})
    assert any(row["condition"] == "DEFICIT_B12" and row["expected_state"] == "unknown" for row in labels)
    assert any(row["label_source"] == "direct_ferritin_rule" for row in labels)
    assert any(row["label_source"] == "plasma_vitamin_c_rule" for row in labels)

    with summary_path.open(encoding="utf-8", newline="") as handle:
        summary = next(csv.DictReader(handle))
    assert int(summary["cases"]) >= 1000
    assert int(summary["evaluated_labels"]) >= 8000
    assert float(summary["benchmark_coverage"]) >= 0.40
    assert summary["clinical_validation"] == "rule_derived_benchmark_not_diagnosis"

    with condition_metrics_path.open(encoding="utf-8", newline="") as handle:
        metrics = {row["condition"]: row for row in csv.DictReader(handle)}
    assert metrics["DEFICIT_VIT_D"]["coverage"]
    assert float(metrics["DEFICIT_VIT_D"]["recall"]) >= 0.95
    assert float(metrics["RIESGO_VITAMINA_C_BAJA"]["coverage"]) >= 0.90
    assert metrics["DEFICIT_B12"]["evaluated_cases"] == "0"


def test_nhanes_multi_cycle_benchmark_expands_coverage_and_calibration():
    cases_path = REAL_CASES / "nhanes_multi_cycle_condition_cases.csv"
    predictions_path = ROOT / "data" / "reports" / "condition_model" / "08_nhanes_multi_cycle_predictions.csv"
    labels_path = ROOT / "data" / "evaluation" / "condition_model" / "nhanes_multi_cycle_benchmark_labels.csv"
    summary_path = ROOT / "data" / "reports" / "condition_model" / "09_nhanes_multi_cycle_benchmark_summary.csv"
    condition_metrics_path = ROOT / "data" / "reports" / "condition_model" / "09_nhanes_multi_cycle_benchmark_condition_metrics.csv"
    calibration_path = ROOT / "data" / "reports" / "condition_model" / "10_nhanes_multi_cycle_threshold_calibration.csv"
    calibration_summary_path = ROOT / "data" / "reports" / "condition_model" / "10_nhanes_multi_cycle_threshold_calibration_summary.csv"
    source_manifest_path = ROOT / "data" / "reports" / "condition_model" / "08_nhanes_multi_cycle_source_manifest.csv"

    for path in [
        cases_path,
        predictions_path,
        labels_path,
        summary_path,
        condition_metrics_path,
        calibration_path,
        calibration_summary_path,
        source_manifest_path,
    ]:
        assert path.exists()

    text = cases_path.read_text(encoding="utf-8")
    assert "SEQN" not in text
    assert "NHANES-2011_2012-" not in text
    assert "NHANES-2017_2018-" not in text

    with cases_path.open(encoding="utf-8", newline="") as handle:
        cases = list(csv.DictReader(handle))
    assert len(cases) >= 2000
    cycles = {row["benchmark_nhanes_cycle"] for row in cases}
    assert {"2011_2012", "2013_2014", "2015_2016", "2017_2018"}.issubset(cycles)

    labels = {condition["condition_code"] for condition in _read_csv("conditions.csv")}
    with predictions_path.open(encoding="utf-8", newline="") as handle:
        predictions = list(csv.DictReader(handle))
    assert len(predictions) == len(cases) * len(labels)

    with labels_path.open(encoding="utf-8", newline="") as handle:
        benchmark_labels = list(csv.DictReader(handle))
    assert any(row["label_source"] == "direct_b12_rule" and row["expected_state"] != "unknown" for row in benchmark_labels)
    assert any(row["label_source"] == "dietary_zinc_intake_rule" for row in benchmark_labels)
    assert any(row["label_source"] == "dietary_magnesium_intake_rule" for row in benchmark_labels)
    assert any(row["label_source"] == "dietary_protein_intake_rule" for row in benchmark_labels)
    assert any(row["label_source"] == "direct_tsh_rule" and row["expected_state"] != "unknown" for row in benchmark_labels)

    with summary_path.open(encoding="utf-8", newline="") as handle:
        summary = next(csv.DictReader(handle))
    assert int(summary["cases"]) >= 2000
    assert int(summary["evaluated_labels"]) >= 20_000
    assert float(summary["benchmark_coverage"]) >= 0.55
    assert summary["clinical_validation"] == "rule_derived_benchmark_not_diagnosis"

    with condition_metrics_path.open(encoding="utf-8", newline="") as handle:
        metrics = {row["condition"]: row for row in csv.DictReader(handle)}
    assert int(metrics["DEFICIT_B12"]["evaluated_cases"]) > 0
    assert int(metrics["SAFETY_TIROIDEA"]["evaluated_cases"]) > 0
    assert float(metrics["RIESGO_PROTEINA_INSUFICIENTE"]["f1"]) >= 0.80
    assert float(metrics["RIESGO_DISLIPIDEMIA"]["recall"]) >= 0.90
    assert float(metrics["RIESGO_OMEGA3_BAJO"]["f1"]) >= 0.90
    assert float(metrics["RIESGO_VITAMINA_C_BAJA"]["recall"]) >= 0.90

    with calibration_summary_path.open(encoding="utf-8", newline="") as handle:
        calibration_summary = next(csv.DictReader(handle))
    assert calibration_summary["clinical_validation"] == "threshold_calibration_not_diagnosis"

    import joblib

    model = joblib.load(ROOT / "models" / "runtime" / "condition_mvp_model.pkl")
    assert model["thresholds"]["DEFICIT_FOLATO"] == 0.27
    assert "threshold_calibration" in model


def test_nhanes_multi_cycle_evidence_and_executive_reports_exist():
    evidence_path = ROOT / "data" / "reports" / "condition_model" / "09_nhanes_multi_cycle_benchmark_evidence_group_metrics.csv"
    executive_path = ROOT / "data" / "reports" / "condition_model" / "09_nhanes_multi_cycle_benchmark_executive_report.csv"
    runner_path = ROOT / "scripts" / "training" / "ejecutar_suite_benchmark_condiciones.py"

    assert evidence_path.exists()
    assert executive_path.exists()
    assert runner_path.exists()

    with evidence_path.open(encoding="utf-8", newline="") as handle:
        evidence_rows = list(csv.DictReader(handle))
    evidence_groups = {row["evidence_group"] for row in evidence_rows}
    assert {"lab_only", "diet_only", "safety_only"}.issubset(evidence_groups)
    assert any(row["condition"] == "DEFICIT_B12" and row["evidence_group"] == "lab_only" for row in evidence_rows)
    assert any(row["condition"] == "RIESGO_OMEGA3_BAJO" and row["evidence_group"] == "diet_only" for row in evidence_rows)

    with executive_path.open(encoding="utf-8", newline="") as handle:
        executive_rows = list(csv.DictReader(handle))
    statuses = {row["status"] for row in executive_rows}
    assert {"listo", "necesita_mejora", "no_evaluable"}.issubset(statuses)
    assert all("false_negative_risk" in row for row in executive_rows)


def test_real_case_pii_column_detection_blocks_direct_identifiers():
    from preparar_casos_reales_condiciones import has_pii_columns

    assert has_pii_columns(["source_case_id", "email", "telefono", "dni", "edad"]) == [
        "email",
        "telefono",
        "dni",
    ]


def test_condition_mvp_training_report_exists_after_pipeline_run():
    report = ROOT / "data" / "reports" / "condition_model" / "04_training_metrics.csv"
    assert report.exists()

    with report.open(encoding="utf-8", newline="") as handle:
        metrics = next(csv.DictReader(handle))

    assert metrics["model_type"] == "OneVsRestClassifier(Calibrated LogisticRegression)"
    assert metrics["disclaimer"].startswith("Modelo de probabilidades")
    assert (ROOT / "data" / "reports" / "condition_model" / "04_training_metrics_by_label.csv").exists()


def test_condition_mvp_runtime_predicts_probabilities():
    from app.ml.runtime.condition_mvp_inference import predict_condition_probabilities

    result = predict_condition_probabilities(
        {
            "tipo_dieta": "vegano",
            "exposicion_solar": "baja",
            "fatiga_general": 5,
            "lab_vitamin_d_status": "low",
            "lab_b12_status": "low",
            "dieta_deficiente": 1,
        }
    )

    assert result
    assert {"condition", "probability", "threshold", "positive"}.issubset(result[0])
    assert any(item["condition"] == "DEFICIT_VIT_D" and item["positive"] for item in result)
    assert {
        "drivers",
        "missing_data",
        "evidence_level",
        "safety_flag",
        "signal_groups",
        "primary_signal_group",
        "signal_strength",
        "model_probability",
        "rule_score",
        "calibrated_by_rules",
    }.issubset(result[0])
    b12 = next(item for item in result if item["condition"] == "DEFICIT_B12")
    assert b12["signal_groups"]["observed_lab"]["drivers"] == ["lab_b12_status"]
    assert b12["signal_strength"] == "alta"


def test_condition_mvp_runtime_separates_soft_survey_signals():
    from app.ml.runtime.condition_mvp_inference import predict_condition_probabilities

    result = predict_condition_probabilities(
        {
            "problemas_sueno": 5,
            "irritabilidad": 5,
            "niebla_mental": 5,
            "fatiga_general": 4,
            "meta_cognitivo": 1,
            "estres_alto": 1,
        }
    )

    stress = next(item for item in result if item["condition"] == "ESTRES_SUENO")
    assert stress["positive"]
    assert stress["primary_signal_group"] == "self_reported_symptoms"
    assert stress["signal_groups"]["self_reported_symptoms"]["count"] >= 4
    assert "observed_lab" not in stress["signal_groups"]
    assert stress["evidence_level"] == "self_reported_symptoms"


def test_condition_mvp_runtime_adds_contextual_wellness_probabilities():
    from app.ml.runtime.condition_mvp_inference import predict_condition_probabilities

    result = predict_condition_probabilities(
        {
            "meta_visual": 1,
            "screen_hours_day": 8,
            "fruit_veg_servings_day": 1,
            "meta_digestiva": 1,
            "digestive_discomfort": 4,
            "fermented_foods_week": 0,
            "meta_hidratacion": 1,
            "water_intake_l_day": 1.0,
            "heavy_sweat_days_week": 4,
            "calambres": 4,
            "meta_cardiovascular": 1,
            "edad": 58,
            "fish_servings_week": 0,
            "meta_cognitivo": 1,
            "niebla_mental": 4,
            "fatiga_general": 4,
            "dieta_deficiente": 1,
            "benchmark_diet_b12_status": "low",
            "benchmark_diet_protein_status": "low",
        }
    )

    contextual = {
        item["condition"]: item
        for item in result
        if item.get("runtime_contextual")
    }

    expected = {
        "SALUD_VISUAL",
        "SALUD_DIGESTIVA",
        "FATIGA_NUTRICIONAL",
        "HIDRATACION_ELECTROLITOS",
        "SALUD_CARDIOVASCULAR_CONTEXTUAL",
        "SALUD_COGNITIVA",
    }
    assert expected.issubset(contextual)
    assert all(contextual[condition]["positive"] for condition in expected)
    assert all(contextual[condition]["model_probability"] == 0.0 for condition in expected)
    assert all(contextual[condition]["calibrated_by_rules"] is True for condition in expected)


def test_condition_mvp_runtime_detects_safety_lab_signals():
    from app.ml.runtime.condition_mvp_inference import predict_condition_probabilities

    result = predict_condition_probabilities(
        {
            "lab_creatinine_status": "critical_high",
            "lab_egfr_status": "low",
            "lab_alt_status": "critical_high",
            "lab_tsh_status": "high",
        }
    )

    positives = {item["condition"] for item in result if item["positive"]}
    assert {"SAFETY_RENAL", "SAFETY_HEPATICA", "SAFETY_TIROIDEA"}.issubset(positives)
