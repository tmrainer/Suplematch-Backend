from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_domain_structure_has_documented_runtime_boundaries() -> None:
    expected_domains = {
        "admin",
        "auth",
        "catalog",
        "feedback",
        "history",
        "labs",
        "recommendations",
        "reviews",
        "survey",
        "users",
    }

    domains_dir = ROOT / "app" / "domains"
    assert (domains_dir / "README.md").exists()
    assert expected_domains.issubset({path.name for path in domains_dir.iterdir() if path.is_dir()})

    for domain in expected_domains:
        assert (domains_dir / domain / "__init__.py").exists()


def test_no_runtime_imports_point_to_removed_global_layers() -> None:
    forbidden_fragments = (
        "app.services",
        "app.repositories",
        "app.schemas",
        "app.core.logging",
        "app.core.middleware",
        "app.core.constants",
        "app.data.data_loader",
        "app.ml.model_registry",
        "app.utils.",
    )

    checked_roots = [ROOT / "app", ROOT / "scripts"]
    offenders: list[str] = []

    for base in checked_roots:
        for path in base.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for fragment in forbidden_fragments:
                if fragment in text:
                    offenders.append(f"{path.relative_to(ROOT)}: {fragment}")

    assert offenders == []


def test_notebook_placeholders_are_valid_ipynb_files() -> None:
    expected = {
        "00_overview/00_backend_pipeline_overview.ipynb",
        "01_data_sources/01_fuentes_oficiales_y_catalogo.ipynb",
        "02_scraping/02_scraping_farmacias.ipynb",
        "03_cleaning/03_limpieza_catalogo.ipynb",
        "04_synthetic_data/04_generacion_casos_sinteticos.ipynb",
        "05_training/05_entrenamiento_modelos.ipynb",
        "06_evaluation/06_evaluacion_benchmarks.ipynb",
        "07_model_export/07_exportacion_modelos.ipynb",
    }

    for relative_path in expected:
        path = ROOT / "notebooks" / relative_path
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["nbformat"] == 4
        assert payload["cells"]
        assert payload["cells"][0]["cell_type"] == "markdown"


def test_legacy_script_wrappers_still_exist() -> None:
    wrappers = [
        "scripts/build_approved_catalog.py",
        "scripts/import_catalog_to_postgres.py",
        "scripts/init_postgres_schema.py",
        "scripts/ensure_test_database.py",
        "scripts/export_survey_contract.py",
        "scripts/seed_database.py",
        "scripts/validate_data_contracts.py",
        "scripts/validate_postgres_persistence.py",
        "scripts/validate_recommendation_quality.py",
        "scripts/warmup_models.py",
        "scripts/scraping/run_weekly_supplement_update.sh",
        "scripts/scraping/supplements_exhaustive_scraper.py",
        "scripts/etl/parser_composicion.py",
    ]

    missing = [path for path in wrappers if not (ROOT / path).exists()]
    assert missing == []
