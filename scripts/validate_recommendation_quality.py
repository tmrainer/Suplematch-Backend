from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.ml.model_loader import load_all_models
from app.ml.runtime import feedback_store
from app.ml.runtime.feedback_store import save_feedback_event
from app.schemas.encuesta import EncuestaInput
from app.services.recommendation_service import RecommendationService


MIN_SCENARIOS = 15


SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "oficina_sin_sol_fatiga_alta",
        "expected_focus": ["DEFICIT_VIT_D", "FATIGA_CRONICA"],
        "feedback_rating": 5,
        "payload": {
            "edad_rango": "31_50",
            "horas_sueno": "menos_5h",
            "frecuencia_ejercicio": "casi_nunca",
            "dieta": "poco_variada",
            "fatiga": "siempre",
            "exposicion_solar": "menos_15min",
            "frecuencia_enfermedad": "3_4_anio",
            "estres": "alto",
            "alcohol": "ocasional",
        },
    },
    {
        "name": "joven_deportista_poco_sol",
        "expected_focus": ["DEFICIT_VIT_D", "RENDIMIENTO_DEPORTIVO"],
        "feedback_rating": 5,
        "payload": {
            "edad_rango": "18_30",
            "horas_sueno": "7_9h",
            "frecuencia_ejercicio": "diario",
            "dieta": "regular",
            "fatiga": "a_veces",
            "exposicion_solar": "menos_15min",
            "frecuencia_enfermedad": "1_2_anio",
            "estres": "moderado",
            "alcohol": "raro",
        },
    },
    {
        "name": "mayor_50_sedentario_baja_inmunidad",
        "expected_focus": ["DEFICIT_VIT_D", "BAJA_INMUNIDAD"],
        "feedback_rating": 5,
        "payload": {
            "edad_rango": "mas_50",
            "horas_sueno": "5_7h",
            "frecuencia_ejercicio": "casi_nunca",
            "dieta": "poco_variada",
            "fatiga": "a_menudo",
            "exposicion_solar": "menos_15min",
            "frecuencia_enfermedad": "muy_seguido",
            "estres": "alto",
            "alcohol": "raro",
        },
    },
    {
        "name": "fatiga_cronica_estres_sueno_bajo",
        "expected_focus": ["FATIGA_CRONICA"],
        "feedback_rating": 1,
        "payload": {
            "edad_rango": "31_50",
            "horas_sueno": "menos_5h",
            "frecuencia_ejercicio": "1_2_semana",
            "dieta": "regular",
            "fatiga": "siempre",
            "exposicion_solar": "30_60min",
            "frecuencia_enfermedad": "casi_nunca",
            "estres": "muy_alto",
            "alcohol": "ocasional",
        },
    },
    {
        "name": "inmunidad_baja_poco_ejercicio",
        "expected_focus": ["BAJA_INMUNIDAD"],
        "feedback_rating": 5,
        "payload": {
            "edad_rango": "18_30",
            "horas_sueno": "5_7h",
            "frecuencia_ejercicio": "casi_nunca",
            "dieta": "poco_variada",
            "fatiga": "a_menudo",
            "exposicion_solar": "15_30min",
            "frecuencia_enfermedad": "muy_seguido",
            "estres": "alto",
            "alcohol": "frecuente",
        },
    },
    {
        "name": "rendimiento_deportivo_activo",
        "expected_focus": ["RENDIMIENTO_DEPORTIVO"],
        "feedback_rating": 5,
        "payload": {
            "edad_rango": "mas_50",
            "horas_sueno": "7_9h",
            "frecuencia_ejercicio": "3_4_semana",
            "dieta": "bastante_variada",
            "fatiga": "a_veces",
            "exposicion_solar": "15_30min",
            "frecuencia_enfermedad": "1_2_anio",
            "estres": "moderado",
            "alcohol": "raro",
        },
    },
    {
        "name": "deficit_vit_d_puro",
        "expected_focus": ["DEFICIT_VIT_D"],
        "feedback_rating": 5,
        "payload": {
            "edad_rango": "18_30",
            "horas_sueno": "7_9h",
            "frecuencia_ejercicio": "1_2_semana",
            "dieta": "bastante_variada",
            "fatiga": "casi_nunca",
            "exposicion_solar": "menos_15min",
            "frecuencia_enfermedad": "1_2_anio",
            "estres": "moderado",
            "alcohol": "raro",
        },
    },
    {
        "name": "mayor_50_fatiga_sin_sol",
        "expected_focus": ["DEFICIT_VIT_D", "FATIGA_CRONICA"],
        "feedback_rating": 1,
        "payload": {
            "edad_rango": "mas_50",
            "horas_sueno": "menos_5h",
            "frecuencia_ejercicio": "1_2_semana",
            "dieta": "regular",
            "fatiga": "siempre",
            "exposicion_solar": "menos_15min",
            "frecuencia_enfermedad": "3_4_anio",
            "estres": "muy_alto",
            "alcohol": "ocasional",
        },
    },
    {
        "name": "inmunidad_fatiga_alcohol_frecuente",
        "expected_focus": ["BAJA_INMUNIDAD", "FATIGA_CRONICA"],
        "feedback_rating": 1,
        "payload": {
            "edad_rango": "31_50",
            "horas_sueno": "mas_9h",
            "frecuencia_ejercicio": "casi_nunca",
            "dieta": "poco_variada",
            "fatiga": "a_menudo",
            "exposicion_solar": "15_30min",
            "frecuencia_enfermedad": "3_4_anio",
            "estres": "alto",
            "alcohol": "frecuente",
        },
    },
    {
        "name": "adolescente_fatiga_inmunidad",
        "expected_focus": ["BAJA_INMUNIDAD", "FATIGA_CRONICA"],
        "feedback_rating": 5,
        "payload": {
            "edad_rango": "menos_18",
            "horas_sueno": "5_7h",
            "frecuencia_ejercicio": "1_2_semana",
            "dieta": "regular",
            "fatiga": "a_menudo",
            "exposicion_solar": "15_30min",
            "frecuencia_enfermedad": "3_4_anio",
            "estres": "moderado",
            "alcohol": "nunca",
        },
    },
    {
        "name": "perfil_extremo_multicondicion",
        "expected_focus": ["DEFICIT_VIT_D", "BAJA_INMUNIDAD", "FATIGA_CRONICA"],
        "feedback_rating": 5,
        "payload": {
            "edad_rango": "menos_18",
            "horas_sueno": "menos_5h",
            "frecuencia_ejercicio": "casi_nunca",
            "dieta": "poco_variada",
            "fatiga": "siempre",
            "exposicion_solar": "menos_15min",
            "frecuencia_enfermedad": "muy_seguido",
            "estres": "muy_alto",
            "alcohol": "frecuente",
        },
    },
    {
        "name": "adulto_activo_fatiga_y_sol_bajo",
        "expected_focus": ["DEFICIT_VIT_D", "RENDIMIENTO_DEPORTIVO"],
        "feedback_rating": 5,
        "payload": {
            "edad_rango": "31_50",
            "horas_sueno": "5_7h",
            "frecuencia_ejercicio": "diario",
            "dieta": "muy_balanceada",
            "fatiga": "a_veces",
            "exposicion_solar": "menos_15min",
            "frecuencia_enfermedad": "1_2_anio",
            "estres": "moderado",
            "alcohol": "raro",
        },
    },
    {
        "name": "mayor_50_activo_sol_bajo",
        "expected_focus": ["DEFICIT_VIT_D", "RENDIMIENTO_DEPORTIVO"],
        "feedback_rating": 5,
        "payload": {
            "edad_rango": "mas_50",
            "horas_sueno": "7_9h",
            "frecuencia_ejercicio": "diario",
            "dieta": "regular",
            "fatiga": "a_veces",
            "exposicion_solar": "menos_15min",
            "frecuencia_enfermedad": "1_2_anio",
            "estres": "moderado",
            "alcohol": "raro",
        },
    },
    {
        "name": "adulto_inmunidad_energia",
        "expected_focus": ["BAJA_INMUNIDAD", "FATIGA_CRONICA"],
        "feedback_rating": 1,
        "payload": {
            "edad_rango": "31_50",
            "horas_sueno": "5_7h",
            "frecuencia_ejercicio": "1_2_semana",
            "dieta": "regular",
            "fatiga": "a_menudo",
            "exposicion_solar": "15_30min",
            "frecuencia_enfermedad": "muy_seguido",
            "estres": "alto",
            "alcohol": "ocasional",
        },
    },
    {
        "name": "joven_inmunidad_alta_fatiga",
        "expected_focus": ["BAJA_INMUNIDAD", "FATIGA_CRONICA"],
        "feedback_rating": 5,
        "payload": {
            "edad_rango": "18_30",
            "horas_sueno": "menos_5h",
            "frecuencia_ejercicio": "1_2_semana",
            "dieta": "poco_variada",
            "fatiga": "siempre",
            "exposicion_solar": "30_60min",
            "frecuencia_enfermedad": "muy_seguido",
            "estres": "alto",
            "alcohol": "raro",
        },
    },
]


def _temporary_feedback_store(tmp_dir: Path) -> tuple[Path, Path, Path]:
    original_paths = (
        feedback_store.RECOMMENDATION_EVENTS_PATH,
        feedback_store.USER_FEEDBACK_EVENTS_PATH,
        feedback_store.FEEDBACK_DB_PATH,
    )
    feedback_store.RECOMMENDATION_EVENTS_PATH = tmp_dir / "recommendation_events.json"
    feedback_store.USER_FEEDBACK_EVENTS_PATH = tmp_dir / "user_feedback_events.json"
    feedback_store.FEEDBACK_DB_PATH = tmp_dir / "feedback.sqlite3"
    return original_paths


def _restore_feedback_store(paths: tuple[Path, Path, Path]) -> None:
    (
        feedback_store.RECOMMENDATION_EVENTS_PATH,
        feedback_store.USER_FEEDBACK_EVENTS_PATH,
        feedback_store.FEEDBACK_DB_PATH,
    ) = paths


def _top_pack(result: dict[str, Any]) -> dict[str, Any] | None:
    packs = result.get("packs_ranked") or []
    return packs[0] if packs else None


def _find_pack(result: dict[str, Any], pack_id: str | None) -> dict[str, Any] | None:
    if pack_id is None:
        return None

    for pack in result.get("packs_ranked") or []:
        if pack.get("pack_id") == pack_id:
            return pack

    return None


def _pack_names(pack: dict[str, Any] | None) -> list[str]:
    if not pack:
        return []

    return [str(name) for name in pack.get("component_names", [])]


def _run_scenario(service: RecommendationService, scenario: dict[str, Any]) -> dict[str, Any]:
    baseline = service.recommend(EncuestaInput(**scenario["payload"]))
    baseline_pack = _top_pack(baseline)

    if baseline_pack:
        save_feedback_event(
            recommendation_id=baseline.get("recommendation_id") or f"rec_{scenario['name']}",
            pack_id=baseline_pack["pack_id"],
            component_ids=baseline_pack.get("component_ids", []),
            rating_overall=scenario["feedback_rating"],
            conditions_context=baseline.get("conditions", []),
            comment=f"quality validation: {scenario['name']}",
        )

    after_feedback = service.recommend(EncuestaInput(**scenario["payload"]))
    after_pack = _top_pack(after_feedback)
    after_rated_pack = _find_pack(
        after_feedback,
        baseline_pack.get("pack_id") if baseline_pack else None,
    )

    return {
        "scenario": scenario["name"],
        "input_data": scenario["payload"],
        "feedback_rating": scenario["feedback_rating"],
        "expected_focus": scenario["expected_focus"],
        "baseline": {
            "conditions": baseline.get("conditions", []),
            "recommendation_count": len(baseline.get("recommendations", [])),
            "pack_count": len(baseline.get("packs_ranked", [])),
            "combo_seguro": baseline.get("combo_seguro"),
            "alert_count": len(baseline.get("alertas", [])),
            "top_pack_id": baseline_pack.get("pack_id") if baseline_pack else None,
            "top_pack": _pack_names(baseline_pack),
            "score_feedback": baseline_pack.get("score_feedback") if baseline_pack else None,
            "score_final": baseline_pack.get("score_final") if baseline_pack else None,
            "feedback_count": baseline_pack.get("feedback_count") if baseline_pack else None,
        },
        "after_feedback": {
            "conditions": after_feedback.get("conditions", []),
            "recommendation_count": len(after_feedback.get("recommendations", [])),
            "pack_count": len(after_feedback.get("packs_ranked", [])),
            "combo_seguro": after_feedback.get("combo_seguro"),
            "alert_count": len(after_feedback.get("alertas", [])),
            "top_pack_id": after_pack.get("pack_id") if after_pack else None,
            "top_pack": _pack_names(after_pack),
            "score_feedback": after_pack.get("score_feedback") if after_pack else None,
            "score_final": after_pack.get("score_final") if after_pack else None,
            "feedback_count": after_pack.get("feedback_count") if after_pack else None,
        },
        "rated_pack_after_feedback": {
            "top_pack_changed": (
                baseline_pack.get("pack_id") != after_pack.get("pack_id")
                if baseline_pack and after_pack
                else False
            ),
            "pack_id": after_rated_pack.get("pack_id") if after_rated_pack else None,
            "rank": after_rated_pack.get("rank") if after_rated_pack else None,
            "top_pack": _pack_names(after_rated_pack),
            "score_feedback": after_rated_pack.get("score_feedback") if after_rated_pack else None,
            "score_final": after_rated_pack.get("score_final") if after_rated_pack else None,
            "feedback_count": after_rated_pack.get("feedback_count") if after_rated_pack else None,
        },
    }


def _evaluate(records: list[dict[str, Any]]) -> dict[str, Any]:
    failures = []
    all_supplements = set()
    changed_scores = 0
    positive_score_increases = 0
    negative_score_decreases = 0

    for record in records:
        baseline = record["baseline"]
        after = record["after_feedback"]
        rated_after = record["rated_pack_after_feedback"]
        expected_focus = set(record["expected_focus"])
        conditions = set(baseline["conditions"])

        all_supplements.update(baseline["top_pack"])
        all_supplements.update(after["top_pack"])

        if not baseline["conditions"] or baseline["conditions"] == ["SALUDABLE"]:
            failures.append(f"{record['scenario']}: no detectó condición accionable")

        if not expected_focus.intersection(conditions):
            failures.append(
                f"{record['scenario']}: condiciones {baseline['conditions']} no cubren foco esperado {record['expected_focus']}"
            )

        if baseline["recommendation_count"] < 3:
            failures.append(f"{record['scenario']}: menos de 3 suplementos recomendados")

        if baseline["pack_count"] < 1:
            failures.append(f"{record['scenario']}: no generó packs_ranked")

        if len(baseline["top_pack"]) < 2:
            failures.append(f"{record['scenario']}: top pack con menos de 2 suplementos")

        if baseline["combo_seguro"] is not True or baseline["alert_count"] != 0:
            failures.append(f"{record['scenario']}: top-level combo no seguro o con alertas")

        before_feedback = baseline["score_feedback"]
        after_feedback = rated_after["score_feedback"]
        before_final = baseline["score_final"]
        after_final = rated_after["score_final"]

        if before_feedback is None or after_feedback is None:
            failures.append(f"{record['scenario']}: no hay score_feedback comparable")
            continue

        if rated_after["feedback_count"] is None or rated_after["feedback_count"] < baseline["feedback_count"] + 1:
            failures.append(f"{record['scenario']}: feedback_count no subió después del feedback")

        if after_feedback != before_feedback or after_final != before_final:
            changed_scores += 1

        if record["feedback_rating"] >= 4 and after_feedback <= before_feedback:
            failures.append(f"{record['scenario']}: rating positivo no elevó score_feedback")
        elif record["feedback_rating"] >= 4:
            positive_score_increases += 1

        if record["feedback_rating"] <= 2 and after_feedback >= before_feedback:
            failures.append(f"{record['scenario']}: rating negativo no redujo score_feedback")
        elif record["feedback_rating"] <= 2:
            negative_score_decreases += 1

    if len(records) < MIN_SCENARIOS:
        failures.append(f"se requieren al menos {MIN_SCENARIOS} escenarios")

    if changed_scores < MIN_SCENARIOS:
        failures.append("score_final/score_feedback no cambió en todos los escenarios")

    return {
        "passed": not failures,
        "failures": failures,
        "summary": {
            "scenario_count": len(records),
            "unique_top_pack_supplements": sorted(all_supplements),
            "unique_top_pack_supplement_count": len(all_supplements),
            "changed_score_count": changed_scores,
            "positive_score_increase_count": positive_score_increases,
            "negative_score_decrease_count": negative_score_decreases,
        },
    }


def run_validation() -> dict[str, Any]:
    models = load_all_models()
    if models.get("pipeline_vitaminas") is None:
        raise RuntimeError("pipeline_vitaminas no está cargado")

    service = RecommendationService(models)
    records = [_run_scenario(service, scenario) for scenario in SCENARIOS]
    evaluation = _evaluate(records)

    return {
        "evaluation": evaluation,
        "records": records,
        "feedback_summary": feedback_store.get_feedback_summary(limit=10),
    }


def _print_summary(report: dict[str, Any]) -> None:
    evaluation = report["evaluation"]
    summary = evaluation["summary"]

    print("\nQuality validation summary")
    print("==========================")
    print(f"passed: {evaluation['passed']}")
    print(f"scenario_count: {summary['scenario_count']}")
    print(f"unique_top_pack_supplement_count: {summary['unique_top_pack_supplement_count']}")
    print(f"changed_score_count: {summary['changed_score_count']}")
    print(f"positive_score_increase_count: {summary['positive_score_increase_count']}")
    print(f"negative_score_decrease_count: {summary['negative_score_decrease_count']}")

    print("\nScenario effects")
    print("----------------")
    for record in report["records"]:
        before = record["baseline"]
        top_after = record["after_feedback"]
        rated_after = record["rated_pack_after_feedback"]
        before_feedback = _format_score(before["score_feedback"])
        after_feedback = _format_score(rated_after["score_feedback"])
        before_final = _format_score(before["score_final"])
        after_final = _format_score(rated_after["score_final"])
        print(
            f"{record['scenario']}: rating={record['feedback_rating']} "
            f"conditions={before['conditions']} "
            f"pack={before['top_pack']} "
            f"feedback {before_feedback}->{after_feedback} "
            f"final {before_final}->{after_final} "
            f"rank_after={rated_after['rank']} "
            f"top_changed={rated_after['top_pack_changed']} "
            f"new_top={top_after['top_pack']}"
        )

    if evaluation["failures"]:
        print("\nFailures")
        print("--------")
        for failure in evaluation["failures"]:
            print(f"- {failure}")


def _format_score(value: Any) -> str:
    if value is None:
        return "n/a"

    return f"{float(value):.4f}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate recommendation quality and feedback impact across 15 ideal scenarios."
    )
    parser.add_argument("--output", type=Path, help="Optional path to write a JSON report.")
    parser.add_argument(
        "--use-runtime-store",
        action="store_true",
        help="Use the configured runtime SQLite store instead of an isolated temporary store.",
    )
    args = parser.parse_args()

    if args.use_runtime_store:
        report = run_validation()
    else:
        with TemporaryDirectory() as tmp_dir:
            original_paths = _temporary_feedback_store(Path(tmp_dir))
            try:
                report = run_validation()
            finally:
                _restore_feedback_store(original_paths)

    _print_summary(report)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nJSON report written to {args.output}")

    return 0 if report["evaluation"]["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
