"""Informe de impacto de un cambio en condition_rules.csv ANTES de reentrenar el modelo.

Compara dos versiones de reglas (y/o dos modos de agregacion) sobre los casos del paquete clinico usando solo las
reglas: positivo = puntaje agregado >= umbral de conditions.csv y confirmado (dos familias sin laboratorio). Es
independiente del modelo sintetico, asi que muestra el efecto del cambio de pesos sin el ruido del reentreno.

    # Reglas actuales contra las de HEAD (git)
    python scripts/clinical/informe_impacto_reglas.py --base-ref HEAD

    # Contra un CSV guardado, o el mismo CSV con otro modo de agregacion
    python scripts/clinical/informe_impacto_reglas.py --base-file /ruta/condition_rules_antes.csv
    python scripts/clinical/informe_impacto_reglas.py --base-aggregation sum --aggregation family

Salida: resumen por consola y JSON en data/reports/clinical_review/impacto_reglas_<fecha>.json con las reglas
agregadas/quitadas/cambiadas y los positivos por condicion antes y despues.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.domains.survey.esquemas_encuesta import EncuestaInput
from app.ml.feature_builder import FeatureBuilder
from app.ml.features_contract import (
    CAT_COLS,
    NUM_COLS,
    aggregate_rule_score,
    is_corroborated,
    prepare_features,
    rule_matches,
    rule_thresholds,
)
from scripts.clinical.generar_paquete_revision import build_case_payloads

RULES_PATH = "data/knowledge/condition_rules.csv"
CONDITIONS_PATH = ROOT / "data/knowledge/conditions.csv"
REPORT_DIR = ROOT / "data/reports/clinical_review"


def _parse_value(value: str, operator: str) -> Any:
    if operator == "in":
        return [item.strip() for item in value.split("|") if item.strip()]
    try:
        number = float(value)
    except ValueError:
        return value
    return int(number) if number.is_integer() else number


def parse_rules(text: str) -> dict[str, list[dict[str, Any]]]:
    rules: dict[str, list[dict[str, Any]]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        rules.setdefault(row["condition_code"], []).append({
            "field": row["field"],
            "operator": row["operator"],
            "value": _parse_value(row["value"], row["operator"]),
            "raw_value": row["value"],
            "weight": float(row["weight"]),
        })
    return rules


def read_base_rules(base_ref: str | None, base_file: Path | None) -> str:
    if base_file is not None:
        return base_file.read_text(encoding="utf-8")
    if base_ref is not None:
        return subprocess.run(
            ["git", "show", f"{base_ref}:{RULES_PATH}"], cwd=ROOT, check=True, capture_output=True, text=True,
        ).stdout
    return (ROOT / RULES_PATH).read_text(encoding="utf-8")


def rule_diff(base: dict[str, list[dict[str, Any]]], new: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    def keyed(rules: dict[str, list[dict[str, Any]]]) -> dict[tuple, float]:
        return {(code, r["field"], r["operator"], r["raw_value"]): r["weight"] for code, items in rules.items() for r in items}

    before, after = keyed(base), keyed(new)
    fmt = lambda key: {"condition": key[0], "field": key[1], "operator": key[2], "value": key[3]}  # noqa: E731
    return {
        "added": [{**fmt(k), "weight": after[k]} for k in sorted(set(after) - set(before))],
        "removed": [{**fmt(k), "weight": before[k]} for k in sorted(set(before) - set(after))],
        "weight_changed": [
            {**fmt(k), "before": before[k], "after": after[k]}
            for k in sorted(set(before) & set(after)) if abs(before[k] - after[k]) > 1e-9
        ],
    }


def load_thresholds() -> dict[str, float]:
    with CONDITIONS_PATH.open(encoding="utf-8") as handle:
        return {row["condition_code"]: float(row["positive_threshold"]) for row in csv.DictReader(handle)}


def case_features(n_cases: int, seed: int) -> list[dict[str, Any]]:
    builder = FeatureBuilder()
    return [
        prepare_features(builder.build_pipeline_payload(EncuestaInput(**case["payload"])), CAT_COLS, NUM_COLS)
        for case in build_case_payloads(n_cases, seed=seed)
    ]


def rule_positives(features: list[dict[str, Any]], rules: dict[str, list[dict[str, Any]]], thresholds: dict[str, float], mode: str) -> list[set[str]]:
    thresholds = rule_thresholds(rules, thresholds, mode)
    per_case = []
    for row in features:
        positives = set()
        for code, items in rules.items():
            if code not in thresholds:
                continue
            score, families = aggregate_rule_score([r for r in items if rule_matches(row, r)], mode)
            if score >= thresholds[code] and is_corroborated(families, mode):
                positives.add(code)
        per_case.append(positives)
    return per_case


def summarize(per_case: list[set[str]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for positives in per_case:
        for code in positives:
            counts[code] = counts.get(code, 0) + 1
    return {
        "mean_conditions_per_case": round(sum(len(p) for p in per_case) / max(len(per_case), 1), 2),
        "by_condition": dict(sorted(counts.items(), key=lambda item: -item[1])),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Impacto de un cambio de reglas sobre los casos del paquete clinico (sin reentrenar).")
    base = parser.add_mutually_exclusive_group()
    base.add_argument("--base-ref", help="Ref de git con la version anterior de condition_rules.csv (p. ej. HEAD).")
    base.add_argument("--base-file", type=Path, help="CSV con la version anterior.")
    parser.add_argument("--base-aggregation", choices=["family", "sum"], default="family")
    parser.add_argument("--aggregation", choices=["family", "sum"], default="family")
    parser.add_argument("--cases", type=int, default=120)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--out-dir", type=Path, default=REPORT_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    base_rules = parse_rules(read_base_rules(args.base_ref, args.base_file))
    new_rules = parse_rules((ROOT / RULES_PATH).read_text(encoding="utf-8"))
    thresholds = load_thresholds()
    features = case_features(args.cases, args.seed)

    before = rule_positives(features, base_rules, thresholds, args.base_aggregation)
    after = rule_positives(features, new_rules, thresholds, args.aggregation)
    before_summary, after_summary = summarize(before), summarize(after)
    codes = sorted(set(before_summary["by_condition"]) | set(after_summary["by_condition"]))
    delta = {
        code: {
            "before": before_summary["by_condition"].get(code, 0),
            "after": after_summary["by_condition"].get(code, 0),
        }
        for code in codes
    }
    flipped_cases = sum(1 for b, a in zip(before, after) if b != a)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base": args.base_ref or (str(args.base_file) if args.base_file else "working tree"),
        "base_aggregation": args.base_aggregation,
        "aggregation": args.aggregation,
        "cases": len(features),
        "cases_with_any_change": flipped_cases,
        "rule_diff": rule_diff(base_rules, new_rules),
        "before": before_summary,
        "after": after_summary,
        "delta_by_condition": delta,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"impacto_reglas_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    diff = report["rule_diff"]
    print(f"Reglas: +{len(diff['added'])} / -{len(diff['removed'])} / peso cambiado {len(diff['weight_changed'])}")
    for item in diff["removed"]:
        print(f"  QUITADA  {item['condition']} {item['field']} {item['operator']} {item['value']} ({item['weight']})")
    for item in diff["weight_changed"]:
        print(f"  PESO     {item['condition']} {item['field']} {item['operator']} {item['value']}: {item['before']} -> {item['after']}")
    print(f"Condiciones por caso (solo reglas): {before_summary['mean_conditions_per_case']} -> {after_summary['mean_conditions_per_case']}"
          f"  | casos con algun cambio: {flipped_cases}/{len(features)}")
    for code, values in sorted(delta.items(), key=lambda item: -abs(item[1]["after"] - item[1]["before"])):
        if values["before"] != values["after"]:
            print(f"  {code:34s} {values['before']:4d} -> {values['after']:4d}")
    print(f"Informe: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
