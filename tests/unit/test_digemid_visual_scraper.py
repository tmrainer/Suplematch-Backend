from __future__ import annotations

from scripts.digemid.scrapear_digemid_visual import (
    detect_blocked_html,
    load_queries,
    normalize_records,
)


def test_normalize_records_maps_visual_table_headers() -> None:
    raw_records = [
        {
            "Registro Sanitario": "DE-1234",
            "Nombre Producto": "VALERIANA 500 mg",
            "Forma Farmacéutica": "CAPSULA",
            "Composición": "VALERIANA OFFICINALIS 500 mg",
        }
    ]

    rows = normalize_records(
        raw_records,
        query="valeriana",
        source_url="https://digemid.example/query",
        scraped_at="2026-06-25T00:00:00+00:00",
    )

    assert rows[0]["item"] == "DE1234"
    assert rows[0]["Producto"] == "VALERIANA 500 mg"
    assert rows[0]["Composición"] == "VALERIANA OFFICINALIS 500 mg"
    assert rows[0]["extraction_status"] == "complete"


def test_normalize_records_extracts_registry_from_row_text_when_header_missing() -> None:
    raw_records = [
        {
            "Producto": "L-THEANINE",
            "_row_text": "Registro Sanitario DE 4889 Producto L-THEANINE Composición L-TEANINA 100 mg",
            "Principios activos": "L-TEANINA 100 mg",
        }
    ]

    rows = normalize_records(
        raw_records,
        query="teanina",
        source_url="https://digemid.example/query",
        scraped_at="2026-06-25T00:00:00+00:00",
    )

    assert rows[0]["item"] == "DE4889"
    assert rows[0]["Composición"] == "L-TEANINA 100 mg"


def test_detect_blocked_html_identifies_cloudflare_page() -> None:
    assert detect_blocked_html("<html><title>Just a moment...</title><p>Cloudflare</p></html>")


def test_load_queries_dedupes_inline_and_file_values(tmp_path) -> None:
    query_file = tmp_path / "queries.txt"
    query_file.write_text("Valeriana\n# comentario\nL-teanina\n", encoding="utf-8")

    queries = load_queries(["Valeriana, Ashwagandha"], query_file)

    assert queries == ["Valeriana", "Ashwagandha", "L-teanina"]


def test_user_agent_is_honest_and_does_not_impersonate_a_browser() -> None:
    from scripts.digemid.scrapear_digemid_visual import USER_AGENT

    assert USER_AGENT.startswith("SupleMatch DIGEMID reader/")
    assert "contacto" in USER_AGENT
    for token in ("Mozilla", "Chrome", "Safari", "AppleWebKit"):
        assert token not in USER_AGENT


def test_parser_has_no_cookie_reuse_or_challenge_wait_options() -> None:
    from scripts.digemid.scrapear_digemid_visual import build_parser

    options = {action.dest for action in build_parser()._actions}
    assert "storage_state" not in options
    assert "save_storage_state" not in options
    assert "challenge_wait_ms" not in options


def test_updater_user_agent_is_honest() -> None:
    from scripts.digemid.actualizar_digemid import USER_AGENT

    assert USER_AGENT.startswith("SupleMatch DIGEMID reader/")
    assert "Mozilla" not in USER_AGENT
