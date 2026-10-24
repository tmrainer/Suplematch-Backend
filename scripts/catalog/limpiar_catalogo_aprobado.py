"""Limpieza del catalogo aprobado ya construido.

Se usa cuando no estan disponibles los insumos brutos (scraping, DIGEMID, product_components)
para reconstruir el catalogo, pero el CSV aprobado tiene filas que no deberian servirse:

1. Productos que no son suplementos orales (cosmeticos, topicos, higiene).
2. Registros sanitarios cuyo nombre DIGEMID es de un solo token ("MAGNESIO .", "PRO .") y que
   quedaron asociados a mas de `--max-rs-fanout` nombres comerciales distintos: el RS fue
   inferido por substring y la composicion/dosis asociada pertenece a otro producto.
3. Filas cuyo nombre comercial no comparte ningun token con el nombre DIGEMID asociado.

Por defecto es un dry-run; con `--apply` sobrescribe el catalogo y guarda las filas removidas.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from scripts.catalog.filtros_categoria import categoria_no_suplemento  # noqa: E402
from scripts.catalog.coincidencia_nombres import nombres_coinciden  # noqa: E402

DEFAULT_CATALOG = ROOT_DIR / "data/catalog/approved_catalog.csv"
DEFAULT_REMOVED_DIR = ROOT_DIR / "data/reports/catalog"

STOP = {"CON", "PARA", "LOS", "LAS", "DEL", "POR", "THE", "AND", "PLUS", "FRASCO", "CAJA", "TABLETAS", "CAPSULAS", "SOFTGELS", "UNIDADES"}


def tokens(value: str) -> set[str]:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).upper()
    return {token for token in re.findall(r"[A-Z]{3,}", text) if token not in STOP}


def digemid_name_tokens(value: str) -> set[str]:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).upper()
    return {token for token in re.findall(r"[A-Z0-9]{2,}", text) if not token.isdigit()}


def classify(rows: list[dict[str, str]], max_fanout: int) -> dict[int, str]:
    reasons: dict[int, str] = {}

    names_by_rs: dict[str, set[str]] = defaultdict(set)
    digemid_by_rs: dict[str, str] = {}
    for row in rows:
        rs = row.get("registro_sanitario_key") or row.get("registro_sanitario") or ""
        names_by_rs[rs].add((row.get("commercial_name") or "").lower())
        digemid_by_rs.setdefault(rs, row.get("digemid_producto") or "")

    fanout_rs = {
        rs
        for rs, names in names_by_rs.items()
        if len(names) > max_fanout and len(digemid_name_tokens(digemid_by_rs.get(rs, ""))) < 2
    }

    for index, row in enumerate(rows):
        category = categoria_no_suplemento(row.get("commercial_name"), row.get("formal_name"), row.get("brand"))
        if category:
            reasons[index] = f"categoria_no_suplemento:{category}"
            continue
        rs = row.get("registro_sanitario_key") or row.get("registro_sanitario") or ""
        if rs in fanout_rs:
            reasons[index] = f"rs_generico_fanout:{rs}:{digemid_by_rs.get(rs, '').strip()}:{len(names_by_rs[rs])}"
            continue
        digemid_name = row.get("digemid_producto") or ""
        if not nombres_coinciden(row.get("commercial_name"), digemid_name):
            reasons[index] = f"nombre_sin_coincidencia_digemid:{digemid_name.strip()}"
    return reasons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--max-rs-fanout", type=int, default=5)
    parser.add_argument("--apply", action="store_true", help="Sobrescribe el catalogo y guarda las filas removidas.")
    parser.add_argument("--removed-dir", type=Path, default=DEFAULT_REMOVED_DIR)
    args = parser.parse_args()

    with args.catalog.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        rows = list(reader)

    reasons = classify(rows, args.max_rs_fanout)
    kept = [row for index, row in enumerate(rows) if index not in reasons]
    removed = [{**rows[index], "cleanup_reason": reason} for index, reason in sorted(reasons.items())]

    def products(subset: list[dict[str, str]]) -> int:
        return len({(r.get("pharmacy"), r.get("sku") or r.get("url")) for r in subset})

    summary = {
        "catalog": str(args.catalog),
        "rows_before": len(rows),
        "rows_after": len(kept),
        "products_before": products(rows),
        "products_after": products(kept),
        "removed_rows": len(removed),
        "removed_products": products(removed),
        "removed_by_reason": dict(Counter(reason.split(":")[0] for reason in reasons.values())),
        "removed_rs_fanout_groups": sorted({r.split(":", 1)[1] for r in reasons.values() if r.startswith("rs_generico_fanout")}),
        "removed_examples": [r["commercial_name"] for r in removed[:15]],
        "applied": args.apply,
    }

    if args.apply:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        args.removed_dir.mkdir(parents=True, exist_ok=True)
        removed_path = args.removed_dir / f"approved_catalog_removed_{stamp}.csv"
        with removed_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns + ["cleanup_reason"], lineterminator="\n")
            writer.writeheader()
            writer.writerows(removed)
        with args.catalog.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(kept)
        summary["removed_path"] = str(removed_path)

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
