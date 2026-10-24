"""Valor de cada pregunta de la encuesta: en cuantos casos cambian las condiciones detectadas si no se hiciera.

Para cada pregunta se repite la deteccion (FeatureBuilder + condition_mvp) sobre los casos del paquete clinico
quitando la respuesta (preguntas opcionales) o poniendo su valor neutro (obligatorias). Una pregunta que no cambia
nada en ningun caso es candidata a eliminarse; una que cambia muchos casos merece quedarse aunque alargue.

    python scripts/clinical/valor_preguntas.py --cases 120

Limitacion: mide el efecto sobre la deteccion de condiciones, no sobre seguridad ni orden de productos (p. ej.
`restricciones` o `suplementos_actuales` no cambian condiciones pero si bloqueos y duplicados).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.domains.survey.esquemas_encuesta import EncuestaInput
from app.ml.feature_builder import FeatureBuilder
from app.ml.runtime.condition_mvp_inference import predict_condition_probabilities
from scripts.clinical.generar_paquete_revision import FOOD_FIELDS, build_case_payloads

REPORT_DIR = ROOT / "data/reports/clinical_review"

# Paso de la app -> campos del payload. Obligatorias: valor neutro (sin señal de riesgo).
QUESTIONS: dict[str, dict[str, Any]] = {
    "variedad_dieta (dieta)": {"set": {"dieta": "bastante_variada"}},
    "alimentacion_medible": {"drop": FOOD_FIELDS + ["fruit_veg_servings_day", "no_meat"]},
    "exposicion_solar": {"set": {"exposicion_solar": "30_60min"}},
    "sol_detalle": {"drop": ["protector_solar", "piel_expuesta"]},
    "frecuencia_ejercicio": {"set": {"frecuencia_ejercicio": "1_2_semana"}},
    "fatiga": {"set": {"fatiga": "casi_nunca"}, "drop": ["fatiga_duracion", "fatiga_mejora_descanso"]},
    "fatiga_detalle": {"drop": ["fatiga_duracion", "fatiga_mejora_descanso"]},
    "horas_sueno": {"set": {"horas_sueno": "7_9h"}},
    "frecuencia_enfermedad": {"set": {"frecuencia_enfermedad": "casi_nunca"}},
    "estres": {"set": {"estres": "bajo"}},
    "sintomas": {"set": {key: "nunca" for key in ("dolor_muscular", "dolor_articular", "niebla_mental", "caida_cabello", "piel_seca", "unas_quebradizas", "calambres")}},
    "factores_hierro": {"drop": ["menstruacion_abundante", "parto_ultimo_anio", "dona_sangre", "iron_anemia_history"]},
    "factores_b12": {"drop": ["anios_dieta_vegetal", "alimentos_fortificados_b12"]},
    "medicamentos_b12": {"drop": ["medicamentos_b12"]},
    "contexto_bienestar": {"drop": ["screen_hours_day", "water_intake_l_day", "heavy_sweat_days_week", "digestive_discomfort", "tabaco"]},
    "objetivos": {"set": {"objetivos": []}},
    "alcohol": {"set": {"alcohol": "nunca"}},
    "toma_suplementos": {"set": {"toma_suplementos": "no", "suplementos_actuales": []}},
}


def detect(payload: dict[str, Any], builder: FeatureBuilder) -> set[str]:
    features = builder.build_pipeline_payload(EncuestaInput(**payload))
    return {item["condition"] for item in predict_condition_probabilities(features) if item["positive"]}


def ablate(payload: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    changed = {key: value for key, value in payload.items() if key not in spec.get("drop", [])}
    changed.update(spec.get("set", {}))
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valor de cada pregunta sobre la deteccion de condiciones.")
    parser.add_argument("--cases", type=int, default=120)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--out-dir", type=Path, default=REPORT_DIR)
    args = parser.parse_args(argv)

    builder = FeatureBuilder()
    payloads = [case["payload"] for case in build_case_payloads(args.cases, seed=args.seed)]
    baseline = [detect(payload, builder) for payload in payloads]
    rows = []
    for question, spec in QUESTIONS.items():
        changed_cases, gained, lost = 0, 0, 0
        for payload, base in zip(payloads, baseline):
            after = detect(ablate(payload, spec), builder)
            if after != base:
                changed_cases += 1
            gained += len(after - base)
            lost += len(base - after)
        rows.append({
            "question": question,
            "cases_changed": changed_cases,
            "share_changed": round(changed_cases / len(payloads), 3),
            "conditions_lost_without_it": lost,
            "conditions_gained_without_it": gained,
        })
    rows.sort(key=lambda row: -row["cases_changed"])
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"valor_preguntas_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}.json"
    out.write_text(json.dumps({"cases": len(payloads), "questions": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{'pregunta':28s} casos que cambian  pierde  gana")
    for row in rows:
        print(f"{row['question']:28s} {row['cases_changed']:5d} ({row['share_changed']:.0%})  {row['conditions_lost_without_it']:6d}  {row['conditions_gained_without_it']:4d}")
    print(f"Informe: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
