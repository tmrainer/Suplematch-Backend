"""Re-infiere el registro sanitario (RS) de un CSV de scraping ya existente, sin red.

Las filas cuyo RS fue inferido por nombre con el matcher antiguo (substring) o que no tienen RS se
re-evaluan con `RegistryMatcher.enrich` actual. Los RS leidos de la pagina (vtex_spec_or_regex, card,
detail, image_ocr) se conservan. Permite reconstruir el catalogo con el matching nuevo a partir del raw.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from dataclasses import asdict, fields
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from scripts.scraping.scraper_suplementos import CSV_FIELDS, ProductRow, RegistryMatcher, read_csv  # noqa: E402

INFERRED_SOURCES = {"digemid_name_match", "digemid_name_inference"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--digemid", type=Path, default=ROOT_DIR / "data/raw/digemid/digemid_limpio.csv")
    parser.add_argument("--components", type=Path, default=ROOT_DIR / "data/training/supplement_model/product_components.csv")
    parser.add_argument("--component-master", type=Path, default=ROOT_DIR / "data/training/supplement_model/Component_Master_Clean.csv")
    args = parser.parse_args()

    matcher = RegistryMatcher(args.digemid, args.components, args.component_master)
    allowed = {f.name for f in fields(ProductRow)}
    rows = read_csv(args.raw)
    out: list[ProductRow] = []
    before = Counter()
    after = Counter()
    for raw in rows:
        data = {k: (v or "") for k, v in raw.items() if k in allowed}
        row = ProductRow(**data)
        before[row.registro_sanitario_source or "none"] += 1
        if row.registro_sanitario_source in INFERRED_SOURCES or not row.registro_sanitario:
            row.registro_sanitario = ""
            row.registro_sanitario_source = ""
            row.rejection_reason = ""
        row = matcher.enrich(row, infer_missing_rs=True)
        after[row.registro_sanitario_source or "none"] += 1
        out.append(row)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in out:
            writer.writerow({field: asdict(row).get(field, "") for field in CSV_FIELDS})

    print(json.dumps({"rows": len(out), "rs_source_before": dict(before), "rs_source_after": dict(after), "out": str(args.out)}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
