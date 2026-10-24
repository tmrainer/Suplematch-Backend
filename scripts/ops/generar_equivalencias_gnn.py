#!/usr/bin/env python3
"""Genera `data/knowledge/gnn_node_equivalences.csv`: nodos del grafo GNN que representan el mismo componente
canonico de `component_aliases.csv` (plan de fiabilidad, Fase 2/4: "ids duplicados del grafo GNN").

El grafo (Component_Master_Clean.csv) tiene varios nodos por componente real: "Vitamin D",
"Vitamin D (cholecalciferol)", "Vitamin D (unspecified)", "Vitamin D (MedlinePlus Supplements)"... Sin esta
tabla el ranker podia devolver dos "Vitamina D" como candidatos distintos.

Reglas de emparejamiento (conservadoras, cada fila dice cual la genero):
- exact:        nombre normalizado == alias normalizado
- qualified:    "<alias> (<forma>)" sin "in combination"
- source_page:  "<alias> — ... (ODS)", "<alias> (ODS|MedlinePlus Supplements|ClinicalTrials.gov)"
- salt_form:    "<alias> <sal>" para sales de minerales (oxide, citrate, glycinate, ...)

Uso:
  python scripts/ops/generar_equivalencias_gnn.py            # escribe el CSV
  python scripts/ops/generar_equivalencias_gnn.py --check    # falla si el CSV versionado difiere
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
MASTER_PATH = ROOT_DIR / "data/training/supplement_model/Component_Master_Clean.csv"
ALIASES_PATH = ROOT_DIR / "data/knowledge/component_aliases.csv"
OUT_PATH = ROOT_DIR / "data/knowledge/gnn_node_equivalences.csv"

SOURCE_SUFFIXES = ("ods", "medlineplus supplements", "clinicaltrials gov", "quickfacts ods", "health professional fact sheet ods")
SALT_FORMS = {
    "oxide", "chloride", "citrate", "sulfate", "sulphate", "hydroxide", "carbonate", "glycinate", "bisglycinate",
    "gluconate", "phosphate", "lactate", "malate", "picolinate", "orotate", "taurate", "threonate", "aspartate",
    "bicarbonate", "acetate", "fumarate", "succinate", "chelate", "amino acid chelate",
}
MIN_ALIAS_LENGTH = 4
FIELDS = ["gnn_component_id", "gnn_canonical_name", "component_id", "canonical_name_es", "match_rule", "matched_alias"]


def normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    text = re.sub(r"&[a-z]+;", " ", text.lower())
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def alias_index(rows: list[dict[str, str]]) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for row in rows:
        aliases = [row["canonical_name_es"], row["canonical_name_en"], *row["aliases"].split("|")]
        for alias in aliases:
            key = normalize(alias)
            if len(key) >= MIN_ALIAS_LENGTH:
                index.setdefault(key, set()).add(row["component_id"])
    return index


def match_rule(node_name: str, raw_name: str, alias: str) -> str | None:
    if node_name == alias:
        return "exact"
    if not node_name.startswith(alias + " "):
        return None
    rest = node_name[len(alias) + 1 :].strip()
    raw_lower = raw_name.lower()
    if "in combination" in raw_lower or " and " in raw_lower or "," in raw_name:
        return None
    if rest in SOURCE_SUFFIXES or rest.endswith(" ods"):
        return "source_page"
    if re.fullmatch(r"\(.*\)", raw_name[raw_name.lower().find(alias) + len(alias) :].strip()):
        return "qualified"
    if rest in SALT_FORMS:
        return "salt_form"
    return None


def build_rows() -> list[dict[str, str]]:
    with MASTER_PATH.open(encoding="utf-8-sig", newline="") as handle:
        master = list(csv.DictReader(handle))
    with ALIASES_PATH.open(encoding="utf-8-sig", newline="") as handle:
        aliases = list(csv.DictReader(handle))
    names_es = {row["component_id"]: row["canonical_name_es"] for row in aliases}
    index = alias_index(aliases)
    rows: dict[str, dict[str, str]] = {}
    for node in master:
        node_id, raw_name = node["component_id"], node["canonical_name"]
        if node_id in names_es:
            continue  # ya es el id canonico
        node_name = normalize(raw_name)
        best: tuple[int, str, str, str] | None = None  # (len alias, alias, rule, canonical_id)
        for alias, ids in index.items():
            rule = match_rule(node_name, raw_name, alias)
            if rule is None or len(ids) != 1:
                continue
            candidate = (len(alias), alias, rule, next(iter(ids)))
            if best is None or candidate[0] > best[0]:
                best = candidate
        if best is None:
            continue
        _, alias, rule, canonical_id = best
        rows[node_id] = {
            "gnn_component_id": node_id,
            "gnn_canonical_name": raw_name,
            "component_id": canonical_id,
            "canonical_name_es": names_es[canonical_id],
            "match_rule": rule,
            "matched_alias": alias,
        }
    return sorted(rows.values(), key=lambda row: (row["canonical_name_es"], row["match_rule"], row["gnn_canonical_name"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="No escribe; falla si el CSV versionado difiere.")
    args = parser.parse_args()
    rows = build_rows()
    if args.check:
        with OUT_PATH.open(encoding="utf-8-sig", newline="") as handle:
            current = list(csv.DictReader(handle))
        if current != rows:
            print(f"{OUT_PATH} desactualizado: regenerar con scripts/ops/generar_equivalencias_gnn.py", file=sys.stderr)
            return 1
        print("gnn_node_equivalences.csv al dia")
        return 0
    with OUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    by_rule: dict[str, int] = {}
    for row in rows:
        by_rule[row["match_rule"]] = by_rule.get(row["match_rule"], 0) + 1
    print(f"{OUT_PATH}: {len(rows)} nodos equivalentes, canonicos={len({r['component_id'] for r in rows})}, reglas={by_rule}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
