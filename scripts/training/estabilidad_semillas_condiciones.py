"""Estabilidad de condition_mvp entre semillas: que detecciones dependen del modelo y cuales del ruido.

Entrena el modelo con varias semillas (sin tocar models/runtime) y compara, sobre los casos del paquete clinico y
los escenarios de validar_calidad_recomendaciones, que condiciones salen en todas las semillas (estables) y cuales
solo en algunas (inestables). Una diferencia entre dos entrenamientos que cae en las inestables es ruido del modelo
sintetico, no un cambio real.

    python scripts/training/estabilidad_semillas_condiciones.py --seeds 42 7 13 101 2026 --rows 10000

Salida: consola y data/reports/condition_model/estabilidad_semillas_<fecha>.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "scripts" / "training", ROOT / "scripts" / "validation"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import joblib

from app.domains.survey.esquemas_encuesta import EncuestaInput
from app.ml.feature_builder import FeatureBuilder
from app.ml.runtime.condition_mvp_inference import predict_condition_probabilities
from entrenar_modelo_condiciones import DEFAULT_LAB_PANEL_RATE, generate_dataset, load_knowledge, train_model
from scripts.clinical.generar_paquete_revision import build_case_payloads

SEEDS_DIR = ROOT / "data/training/condition_model/seeds"
REPORT_DIR = ROOT / "data/reports/condition_model"


def train_seed(knowledge: dict, seed: int, rows: int, aggregation: str) -> dict:
    model_dir = SEEDS_DIR / f"seed_{seed}"
    df = generate_dataset(knowledge, n_rows=rows, seed=seed, lab_panel_rate=DEFAULT_LAB_PANEL_RATE, rule_aggregation=aggregation)
    metrics = train_model(df, knowledge, seed=seed, lab_panel_rate=DEFAULT_LAB_PANEL_RATE, rule_aggregation=aggregation, model_dir=model_dir)
    return {"artifact": joblib.load(model_dir / "condition_mvp_model.pkl"), "f1_macro": metrics.get("f1_macro")}


def positives(features: list[dict], artifact: dict) -> list[set[str]]:
    return [{d["condition"] for d in predict_condition_probabilities(f, artifact) if d["positive"]} for f in features]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Estabilidad de condition_mvp entre semillas.")
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 7, 13, 101, 2026])
    parser.add_argument("--rows", type=int, default=10000)
    parser.add_argument("--aggregation", choices=["family", "sum"], default="family")
    parser.add_argument("--cases", type=int, default=120)
    args = parser.parse_args(argv)

    from validar_calidad_recomendaciones import SCENARIOS

    knowledge = load_knowledge()
    builder = FeatureBuilder()
    case_features = [builder.build_pipeline_payload(EncuestaInput(**c["payload"])) for c in build_case_payloads(args.cases)]
    scenario_features = [builder.build_pipeline_payload(EncuestaInput(**s["payload"])) for s in SCENARIOS]

    per_seed_cases, per_seed_coverage, f1 = {}, {}, {}
    for seed in args.seeds:
        trained = train_seed(knowledge, seed, args.rows, args.aggregation)
        f1[seed] = trained["f1_macro"]
        per_seed_cases[seed] = positives(case_features, trained["artifact"])
        scen = positives(scenario_features, trained["artifact"])
        per_seed_coverage[seed] = {s["name"]: bool(p & set(s["expected_focus"])) for s, p in zip(SCENARIOS, scen)}
        print(f"semilla {seed}: f1_macro={f1[seed]:.3f}  cond/caso={sum(map(len, per_seed_cases[seed])) / len(case_features):.2f}"
              f"  escenarios {sum(per_seed_coverage[seed].values())}/{len(SCENARIOS)}")

    n_seeds = len(args.seeds)
    hits: dict[tuple[int, str], int] = Counter()
    for cases in per_seed_cases.values():
        for index, conditions in enumerate(cases):
            for condition in conditions:
                hits[(index, condition)] += 1
    by_condition: dict[str, dict] = defaultdict(lambda: {"stable_cases": 0, "unstable_cases": 0, "per_seed": []})
    for (index, condition), count in hits.items():
        bucket = by_condition[condition]
        bucket["stable_cases" if count == n_seeds else "unstable_cases"] += 1
    for condition, bucket in by_condition.items():
        bucket["per_seed"] = [sum(1 for c in per_seed_cases[seed] if condition in c) for seed in args.seeds]
    stable_pairs = sum(b["stable_cases"] for b in by_condition.values())
    unstable_pairs = sum(b["unstable_cases"] for b in by_condition.values())
    scenarios = {
        name: sum(per_seed_coverage[seed][name] for seed in args.seeds)
        for name in per_seed_coverage[args.seeds[0]]
    }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seeds": args.seeds,
        "rows": args.rows,
        "aggregation": args.aggregation,
        "f1_macro": f1,
        "stable_detections": stable_pairs,
        "unstable_detections": unstable_pairs,
        "unstable_share": round(unstable_pairs / max(stable_pairs + unstable_pairs, 1), 3),
        "by_condition": dict(sorted(by_condition.items(), key=lambda item: -item[1]["unstable_cases"])),
        "scenario_coverage_by_seed_count": scenarios,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / f"estabilidad_semillas_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"\nDetecciones caso-condicion: estables {stable_pairs}, inestables {unstable_pairs} ({report['unstable_share']:.0%})")
    print(f"{'condicion':34s} estables inestables  por semilla")
    for condition, bucket in report["by_condition"].items():
        print(f"{condition:34s} {bucket['stable_cases']:7d} {bucket['unstable_cases']:9d}   {bucket['per_seed']}")
    print("\nEscenarios: en cuantas semillas se cubre el foco esperado")
    for name, count in scenarios.items():
        tag = "estable" if count in (0, n_seeds) else "INESTABLE"
        print(f"  {name:36s} {count}/{n_seeds} {tag}")
    print(f"Informe: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
