from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CURRENT = ROOT_DIR / "data/raw/digemid/digemid_limpio.csv"
DEFAULT_SNAPSHOT_DIR = ROOT_DIR / "data/reports/digemid"
DEFAULT_REPORT = ROOT_DIR / "data/reports/digemid/digemid_update_report.json"
DEFAULT_COMPONENTS = ROOT_DIR / "data/training/supplement_model/product_components.csv"

REQUIRED_COLUMNS = ("item", "Producto", "Composición")
OUTPUT_COLUMNS = [
    "item",
    "Distribuidor",
    "Producto",
    "Fabricante",
    "composicion_por",
    "Forma Farmacéutica",
    "Procedencia",
    "Liberación",
    "Composición",
    "Vías de Administración",
    "Presentación",
    "codigo_atc",
    "descripcion_clasificacion",
    "grupo_atc_3",
    "grupo_atc_4",
]

COLUMN_ALIASES = {
    "item": {
        "item",
        "n_registro_sanitario",
        "registro_sanitario",
        "nro_registro_sanitario",
        "numero_registro_sanitario",
        "n_rs",
        "rs",
    },
    "Distribuidor": {"distribuidor", "titular", "representante", "solicitante"},
    "Producto": {"producto", "nombre_producto", "nombre_de_producto", "nombre"},
    "Fabricante": {"fabricante", "laboratorio_fabricante", "laboratorio"},
    "composicion_por": {"composicion_por", "composición_por", "por", "forma_de_composicion"},
    "Forma Farmacéutica": {
        "forma_farmaceutica",
        "forma_farmacéutica",
        "forma",
        "forma_farmaceutica_descripcion",
    },
    "Procedencia": {"procedencia", "pais", "país", "pais_de_fabricacion", "país_de_fabricación"},
    "Liberación": {"liberacion", "liberación"},
    "Composición": {"composicion", "composición", "principio_activo", "principios_activos"},
    "Vías de Administración": {
        "vias_de_administracion",
        "vías_de_administración",
        "via_administracion",
        "vía_administración",
    },
    "Presentación": {"presentacion", "presentación"},
    "codigo_atc": {"codigo_atc", "código_atc", "atc"},
    "descripcion_clasificacion": {
        "descripcion_clasificacion",
        "descripción_clasificación",
        "clasificacion",
        "clasificación",
    },
    "grupo_atc_3": {"grupo_atc_3", "atc_3"},
    "grupo_atc_4": {"grupo_atc_4", "atc_4"},
}


class DigemidUpdateError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def clean(value: Any) -> str:
    return str(value or "").strip()


def normalize_key(value: Any) -> str:
    text = clean(value).lower()
    text = (
        text.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ü", "u")
        .replace("ñ", "n")
    )
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def normalize_rs(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", clean(value).upper())


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def fetch_url(url: str, timeout: int) -> tuple[bytes, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 SupleMatchCatalogBot/1.0 "
            "(university project; contact: local-admin)"
        ),
        "Accept": "text/csv,application/vnd.ms-excel,application/json,text/html;q=0.8,*/*;q=0.5",
    }
    with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
        response = client.get(url)

    body = response.content
    text_head = body[:6000].decode("utf-8", errors="ignore").lower()
    if response.status_code >= 400:
        raise DigemidUpdateError(f"source_url_http_{response.status_code}")
    if "just a moment" in text_head and "cloudflare" in text_head:
        raise DigemidUpdateError("source_url_blocked_by_cloudflare")
    if "cf-error" in text_head or "challenge-platform" in text_head:
        raise DigemidUpdateError("source_url_blocked_by_cloudflare")
    return body, clean(response.headers.get("content-type")).lower()


def table_from_bytes(payload: bytes, suffix: str) -> tuple[list[str], list[dict[str, Any]]]:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(payload)
        tmp_path = Path(tmp.name)
    try:
        return table_from_file(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def table_from_file(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".txt", ""}:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            return list(reader.fieldnames or []), list(reader)

    if suffix in {".xlsx", ".xls"}:
        try:
            import pandas as pd
        except ModuleNotFoundError as exc:
            raise DigemidUpdateError("pandas_required_for_excel_source") from exc

        df = pd.read_excel(path, dtype=str)
        return [str(column) for column in df.columns], df.fillna("").to_dict("records")

    if suffix == ".json":
        try:
            import pandas as pd
        except ModuleNotFoundError as exc:
            raise DigemidUpdateError("pandas_required_for_json_source") from exc

        df = pd.read_json(path, dtype=str)
        return [str(column) for column in df.columns], df.fillna("").to_dict("records")

    if suffix in {".html", ".htm"}:
        try:
            import pandas as pd
        except ModuleNotFoundError as exc:
            raise DigemidUpdateError("pandas_required_for_html_source") from exc

        tables = pd.read_html(path)
        if not tables:
            raise DigemidUpdateError("html_without_tables")
        df = max(tables, key=len).astype(str)
        return [str(column) for column in df.columns], df.fillna("").to_dict("records")

    raise DigemidUpdateError(f"unsupported_source_extension:{suffix}")


def canonical_column_map(columns: list[str]) -> dict[str, str]:
    normalized_to_original = {normalize_key(column): column for column in columns}
    mapping: dict[str, str] = {}

    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            normalized_alias = normalize_key(alias)
            if normalized_alias in normalized_to_original:
                mapping[canonical] = normalized_to_original[normalized_alias]
                break

    return mapping


def normalize_table(columns: list[str], records: list[dict[str, Any]]) -> list[dict[str, str]]:
    mapping = canonical_column_map([str(column) for column in columns])
    missing = [column for column in REQUIRED_COLUMNS if column not in mapping]
    if missing:
        raise DigemidUpdateError(f"missing_required_columns:{','.join(missing)}")

    rows: list[dict[str, str]] = []
    seen_rs: set[str] = set()
    for record in records:
        normalized: dict[str, str] = {}
        for column in OUTPUT_COLUMNS:
            source = mapping.get(column)
            normalized[column] = clean(record.get(source, "")) if source else ""

        rs = normalize_rs(normalized["item"])
        if not rs:
            continue
        if rs in seen_rs:
            continue
        seen_rs.add(rs)
        normalized["item"] = rs
        rows.append(normalized)

    return rows


def normalize_dataframe(df: Any) -> list[dict[str, str]]:
    columns = [str(column) for column in getattr(df, "columns", [])]
    if not columns or not hasattr(df, "fillna"):
        raise DigemidUpdateError("invalid_dataframe")
    return normalize_table(columns, df.fillna("").to_dict("records"))


def quality_report(rows: list[dict[str, str]], components_path: Path) -> dict[str, Any]:
    rs_values = {normalize_rs(row.get("item")) for row in rows if normalize_rs(row.get("item"))}
    with_composition = sum(1 for row in rows if clean(row.get("Composición")))
    with_product = sum(1 for row in rows if clean(row.get("Producto")))
    with_atc = sum(1 for row in rows if clean(row.get("codigo_atc")))

    mapped_rs: set[str] = set()
    if components_path.exists():
        for row in read_csv_rows(components_path):
            rs = normalize_rs(row.get("item"))
            component_id = clean(row.get("component_id"))
            score = clean(row.get("match_score"))
            if rs and component_id and score != "0.0":
                mapped_rs.add(rs)

    missing_component_map = sorted(rs_values - mapped_rs)
    return {
        "rows": len(rows),
        "unique_rs": len(rs_values),
        "with_product": with_product,
        "with_composition": with_composition,
        "with_atc": with_atc,
        "component_mapped_rs": len(rs_values.intersection(mapped_rs)),
        "missing_component_map_rs": len(missing_component_map),
        "missing_component_map_sample": missing_component_map[:50],
    }


def current_report(path: Path, components_path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "rows": 0,
            "unique_rs": 0,
        }
    rows = read_csv_rows(path)
    report = quality_report(rows, components_path)
    report["exists"] = True
    report["path"] = str(path)
    return report


def atomic_replace_csv(out_path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", delete=False, dir=out_path.parent) as tmp:
        writer = csv.DictWriter(tmp, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
        tmp_path = Path(tmp.name)
    tmp_path.replace(out_path)


def update_from_source(
    *,
    source_file: Path | None,
    source_url: str | None,
    out_path: Path,
    snapshot_dir: Path,
    components_path: Path,
    min_rows: int,
    timeout: int,
) -> dict[str, Any]:
    if source_file:
        columns, records = table_from_file(source_file)
        source = str(source_file)
    elif source_url:
        payload, content_type = fetch_url(source_url, timeout)
        path_suffix = Path(source_url.split("?", 1)[0]).suffix.lower()
        if not path_suffix and "text/html" in content_type:
            raise DigemidUpdateError("source_url_is_search_html_not_export")
        if path_suffix:
            suffix = path_suffix
        elif "json" in content_type:
            suffix = ".json"
        elif "excel" in content_type or "spreadsheet" in content_type:
            suffix = ".xlsx"
        else:
            suffix = ".csv"
        columns, records = table_from_bytes(payload, suffix)
        source = source_url
    else:
        raise DigemidUpdateError("no_source_configured")

    rows = normalize_table(columns, records)
    if len(rows) < min_rows:
        raise DigemidUpdateError(f"too_few_rows:{len(rows)}<min_rows:{min_rows}")

    now = utc_now()
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    snapshot_path = snapshot_dir / f"digemid_limpio_{stamp}.csv"
    backup_path = snapshot_dir / f"digemid_limpio_previous_{stamp}.csv"

    if out_path.exists():
        shutil.copy2(out_path, backup_path)

    atomic_replace_csv(out_path, rows, OUTPUT_COLUMNS)
    shutil.copy2(out_path, snapshot_path)

    report = quality_report(rows, components_path)
    report.update(
        {
            "status": "updated",
            "source": source,
            "updated_at": now.isoformat(),
            "out": str(out_path),
            "snapshot": str(snapshot_path),
            "backup": str(backup_path) if backup_path.exists() else None,
        }
    )
    return report


def write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Actualiza y valida el CSV base de DIGEMID.")
    parser.add_argument("--source-file", type=Path, default=os.getenv("DIGEMID_SOURCE_FILE"))
    parser.add_argument("--source-url", default=os.getenv("DIGEMID_SOURCE_URL"))
    parser.add_argument("--out", type=Path, default=DEFAULT_CURRENT)
    parser.add_argument("--snapshot-dir", type=Path, default=DEFAULT_SNAPSHOT_DIR)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--components", type=Path, default=DEFAULT_COMPONENTS)
    parser.add_argument("--min-rows", type=int, default=int(os.getenv("DIGEMID_MIN_ROWS", "1000")))
    parser.add_argument("--timeout", type=int, default=int(os.getenv("DIGEMID_TIMEOUT_SECONDS", "45")))
    parser.add_argument("--fail-on-no-source", action="store_true")
    parser.add_argument("--fail-on-fetch-error", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = update_from_source(
            source_file=args.source_file,
            source_url=args.source_url,
            out_path=args.out,
            snapshot_dir=args.snapshot_dir,
            components_path=args.components,
            min_rows=args.min_rows,
            timeout=args.timeout,
        )
        write_report(args.report_out, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except DigemidUpdateError as exc:
        current = current_report(args.out, args.components)
        report = {
            "status": "retained_previous",
            "reason": str(exc),
            "generated_at": utc_now().isoformat(),
            "out": str(args.out),
            "current": current,
        }
        write_report(args.report_out, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if str(exc) == "no_source_configured" and not args.fail_on_no_source:
            return 0
        return 1 if args.fail_on_fetch_error or args.fail_on_no_source else 0


if __name__ == "__main__":
    raise SystemExit(main())
