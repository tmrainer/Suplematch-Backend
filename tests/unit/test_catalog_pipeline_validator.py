from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.validation.validar_pipeline_catalogo import main


RAW_FIELDS = [
    "pharmacy",
    "commercial_name",
    "registro_sanitario",
    "price",
    "currency",
    "availability",
    "url",
    "sku",
    "source_strategy",
    "scraped_at",
]

APPROVED_FIELDS = [
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
]


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_catalog_pipeline_validator_passes_for_valid_outputs(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc).isoformat()
    raw = tmp_path / "raw.csv"
    approved = tmp_path / "approved.csv"
    rejects = tmp_path / "rejects.csv"
    report = tmp_path / "report.json"
    raw_rows = [
        {
            "pharmacy": pharmacy,
            "commercial_name": f"{pharmacy} Vitamina D",
            "registro_sanitario": f"RS{i}",
            "price": "42.5",
            "currency": "PEN",
            "availability": "available",
            "url": f"https://example.test/{i}",
            "sku": f"sku-{i}",
            "source_strategy": "test",
            "scraped_at": now,
        }
        for i, pharmacy in enumerate(["Inkafarma", "Mifarma", "Boticas Peru"], start=1)
    ]
    approved_rows = [
        {
            "pharmacy": row["pharmacy"],
            "commercial_name": row["commercial_name"],
            "registro_sanitario": row["registro_sanitario"],
            "registro_sanitario_key": row["registro_sanitario"],
            "component_id": "cmp_vit_d",
            "ingredient": "Vitamina D",
            "price": row["price"],
            "currency": row["currency"],
            "availability": row["availability"],
            "url": row["url"],
            "sku": row["sku"],
            "regulatory_status": "digemid_match",
        }
        for row in raw_rows
    ]
    write_csv(raw, RAW_FIELDS, raw_rows)
    write_csv(approved, APPROVED_FIELDS, approved_rows)
    write_csv(rejects, RAW_FIELDS, [])

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_catalog_pipeline.py",
            "--raw", str(raw),
            "--approved", str(approved),
            "--rejects", str(rejects),
            "--report-out", str(report),
            "--min-raw-rows", "3",
            "--min-approved-rows", "3",
            "--min-pharmacies", "3",
        ],
    )

    assert main() == 0
    assert '"status": "passed"' in report.read_text(encoding="utf-8")


def test_catalog_pipeline_validator_fails_for_low_rows(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc).isoformat()
    raw = tmp_path / "raw.csv"
    approved = tmp_path / "approved.csv"
    row = {
        "pharmacy": "Inkafarma",
        "commercial_name": "Vitamina D",
        "registro_sanitario": "RS1",
        "price": "42.5",
        "currency": "PEN",
        "availability": "available",
        "url": "https://example.test/1",
        "sku": "sku-1",
        "source_strategy": "test",
        "scraped_at": now,
    }
    approved_row = {
        **{field: row.get(field, "") for field in APPROVED_FIELDS},
        "registro_sanitario_key": "RS1",
        "component_id": "cmp_vit_d",
        "ingredient": "Vitamina D",
        "regulatory_status": "digemid_match",
    }
    write_csv(raw, RAW_FIELDS, [row])
    write_csv(approved, APPROVED_FIELDS, [approved_row])

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_catalog_pipeline.py",
            "--raw", str(raw),
            "--approved", str(approved),
            "--min-raw-rows", "2",
            "--min-approved-rows", "2",
            "--min-pharmacies", "2",
        ],
    )

    assert main() == 1
