from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RAW_REQUIRED_COLUMNS = {
    "pharmacy",
    "commercial_name",
    "registro_sanitario",
    "price",
    "currency",
    "availability",
    "url",
    "sku",
    "source_strategy",
}

APPROVED_REQUIRED_COLUMNS = {
    "pharmacy",
    "commercial_name",
    "registro_sanitario",
    "registro_sanitario_key",
    "component_id",
    "ingredient",
    "price",
    "currency",
    "availability",
    "url",
    "sku",
    "regulatory_status",
}


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        raise FileNotFoundError(f"missing_file={path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def parse_float(value: Any) -> float | None:
    try:
        number = float(str(value or "").strip())
    except ValueError:
        return None
    return number


def parse_datetime(value: str) -> datetime | None:
    clean = str(value or "").strip()
    if not clean:
        return None
    try:
        return datetime.fromisoformat(clean.replace("Z", "+00:00"))
    except ValueError:
        return None


def pct(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(part / total, 4)


def by_pharmacy(rows: list[dict[str, str]]) -> dict[str, int]:
    counts = Counter((row.get("pharmacy") or "unknown").strip() or "unknown" for row in rows)
    return dict(sorted(counts.items()))


def duplicate_count(rows: list[dict[str, str]]) -> int:
    seen: set[tuple[str, str, str]] = set()
    duplicates = 0
    for row in rows:
        key = (
            (row.get("pharmacy") or "").strip().lower(),
            (row.get("sku") or row.get("url") or "").strip().lower(),
            (row.get("component_id") or "").strip().lower(),
            (row.get("ingredient") or "").strip().lower(),
        )
        if key in seen:
            duplicates += 1
        seen.add(key)
    return duplicates


def validate_columns(columns: list[str], required: set[str], label: str, errors: list[str]) -> None:
    missing = sorted(required - set(columns))
    if missing:
        errors.append(f"{label}_missing_columns={','.join(missing)}")


def validate_prices(rows: list[dict[str, str]], label: str, errors: list[str], *, max_invalid_ratio: float) -> dict[str, Any]:
    invalid = 0
    for row in rows:
        price = parse_float(row.get("price"))
        if price is None or price <= 0:
            invalid += 1
    ratio = pct(invalid, len(rows))
    if rows and ratio > max_invalid_ratio:
        errors.append(f"{label}_invalid_price_ratio={ratio}")
    return {"invalid": invalid, "invalid_ratio": ratio}


def validate_availability(rows: list[dict[str, str]], errors: list[str]) -> dict[str, Any]:
    invalid = [
        row for row in rows
        if (row.get("availability") or "").strip().lower() != "available"
    ]
    ratio = pct(len(invalid), len(rows))
    if invalid:
        errors.append(f"approved_unavailable_rows={len(invalid)}")
    return {"unavailable": len(invalid), "unavailable_ratio": ratio}


def validate_freshness(rows: list[dict[str, str]], max_age_hours: int, errors: list[str]) -> dict[str, Any]:
    timestamps = [
        parsed for parsed in (parse_datetime(row.get("scraped_at", "")) for row in rows)
        if parsed is not None
    ]
    if not timestamps:
        errors.append("raw_missing_scraped_at")
        return {"latest_scraped_at": None, "age_hours": None}

    latest = max(timestamps)
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    age_hours = round((now - latest.astimezone(timezone.utc)).total_seconds() / 3600, 2)
    if age_hours > max_age_hours:
        errors.append(f"raw_stale_scraped_at_hours={age_hours}")
    return {"latest_scraped_at": latest.isoformat(), "age_hours": age_hours}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Valida outputs del scraping/catalogo de suplementos.")
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--approved", type=Path, required=True)
    parser.add_argument("--rejects", type=Path)
    parser.add_argument("--report-out", type=Path)
    parser.add_argument("--mode", choices=["weekly", "monthly", "manual"], default="manual")
    parser.add_argument("--min-raw-rows", type=int, default=500)
    parser.add_argument("--min-approved-rows", type=int, default=250)
    parser.add_argument("--min-pharmacies", type=int, default=3)
    parser.add_argument("--max-invalid-price-ratio", type=float, default=0.01)
    parser.add_argument("--max-raw-age-hours", type=int, default=48)
    parser.add_argument("--require-pharmacy", action="append", default=[])
    return parser


def main() -> int:
    args = build_parser().parse_args()
    errors: list[str] = []
    warnings: list[str] = []

    raw_columns, raw_rows = read_csv(args.raw)
    approved_columns, approved_rows = read_csv(args.approved)
    rejects_rows: list[dict[str, str]] = []
    if args.rejects and args.rejects.exists():
        _, rejects_rows = read_csv(args.rejects)

    validate_columns(raw_columns, RAW_REQUIRED_COLUMNS, "raw", errors)
    validate_columns(approved_columns, APPROVED_REQUIRED_COLUMNS, "approved", errors)

    raw_pharmacies = by_pharmacy(raw_rows)
    approved_pharmacies = by_pharmacy(approved_rows)
    approved_components = {
        (row.get("component_id") or "").strip()
        for row in approved_rows
        if (row.get("component_id") or "").strip()
    }
    approved_rs = {
        (row.get("registro_sanitario_key") or row.get("registro_sanitario") or "").strip()
        for row in approved_rows
        if (row.get("registro_sanitario_key") or row.get("registro_sanitario") or "").strip()
    }

    if len(raw_rows) < args.min_raw_rows:
        errors.append(f"raw_rows_below_min={len(raw_rows)}<{args.min_raw_rows}")
    if len(approved_rows) < args.min_approved_rows:
        errors.append(f"approved_rows_below_min={len(approved_rows)}<{args.min_approved_rows}")
    if len(raw_pharmacies) < args.min_pharmacies:
        errors.append(f"raw_pharmacies_below_min={len(raw_pharmacies)}<{args.min_pharmacies}")
    if len(approved_pharmacies) < args.min_pharmacies:
        errors.append(f"approved_pharmacies_below_min={len(approved_pharmacies)}<{args.min_pharmacies}")

    for pharmacy in args.require_pharmacy:
        if pharmacy not in raw_pharmacies and pharmacy not in approved_pharmacies:
            errors.append(f"required_pharmacy_missing={pharmacy}")

    duplicate_rows = duplicate_count(approved_rows)
    if duplicate_rows:
        warnings.append(f"approved_duplicate_keys={duplicate_rows}")

    report = {
        "mode": args.mode,
        "status": "failed" if errors else "passed",
        "errors": errors,
        "warnings": warnings,
        "raw": {
            "path": str(args.raw),
            "rows": len(raw_rows),
            "pharmacies": raw_pharmacies,
            "prices": validate_prices(
                raw_rows,
                "raw",
                errors,
                max_invalid_ratio=args.max_invalid_price_ratio,
            ),
            "freshness": validate_freshness(raw_rows, args.max_raw_age_hours, errors),
        },
        "approved": {
            "path": str(args.approved),
            "rows": len(approved_rows),
            "pharmacies": approved_pharmacies,
            "components": len(approved_components),
            "registro_sanitario": len(approved_rs),
            "prices": validate_prices(
                approved_rows,
                "approved",
                errors,
                max_invalid_ratio=args.max_invalid_price_ratio,
            ),
            "availability": validate_availability(approved_rows, errors),
        },
        "rejects": {
            "path": str(args.rejects) if args.rejects else None,
            "rows": len(rejects_rows),
            "reject_ratio_vs_raw": pct(len(rejects_rows), len(raw_rows) + len(rejects_rows)),
        },
    }
    report["status"] = "failed" if errors else "passed"

    payload = json.dumps(report, indent=2, ensure_ascii=False)
    print(payload)
    if args.report_out:
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        args.report_out.write_text(payload + "\n", encoding="utf-8")

    return 1 if errors else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status": "failed", "errors": [str(exc)]}, ensure_ascii=False), file=sys.stderr)
        raise
