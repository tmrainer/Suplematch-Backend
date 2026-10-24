"""Candidatos de fuentes primarias en PubMed: consultas, clasificacion y cache (sin red)."""

from __future__ import annotations

import json

from scripts.clinical import buscar_fuentes_primarias as bfp


def test_every_claim_has_a_query() -> None:
    for claim in bfp.read_claims():
        assert bfp.build_query(claim["component"], claim["claim_code"], claim["claim_type"]), claim["component"]


def test_query_tags_each_term_and_filters_study_design() -> None:
    query = bfp.build_query("Zinc", "supports_zinc_status", "functional_support", "[ti]")
    assert query.startswith("(zinc[ti]) AND (")
    assert '"zinc deficiency"[tiab] OR immune[tiab]' in query
    assert "systematic[sb]" in query and "humans[mh]" in query
    replacement = bfp.build_query("Vitamina D", "supports_vitamin_d_status", "deficiency_replacement")
    assert "supplement*[tiab]" in replacement


def test_study_type_prefers_cochrane_then_reviews_then_trials() -> None:
    assert bfp.study_type(["Systematic Review"], "The Cochrane database of systematic reviews") == "cochrane"
    assert bfp.study_type(["Meta-Analysis", "Journal Article"], "Nutrients") == "revision_sistematica"
    assert bfp.study_type(["Randomized Controlled Trial"], "BMJ") == "eca"
    candidates = [
        {"pmid": "1", "tipo_estudio": "eca"}, {"pmid": "2", "tipo_estudio": "cochrane"},
        {"pmid": "3", "tipo_estudio": "revision_sistematica"}, {"pmid": "4", "tipo_estudio": "cochrane"},
    ]
    # Solo reordena dentro de los 2*per_claim mas relevantes: el Cochrane en posicion 4 queda fuera con per_claim=1.
    assert [c["pmid"] for c in bfp.rank_candidates(candidates, 1)] == ["2"]
    assert [c["pmid"] for c in bfp.rank_candidates(candidates, 2)] == ["2", "4"]


def test_pubmed_client_parses_summary_and_caches(tmp_path) -> None:
    calls = []

    def fake_fetch(url: str) -> bytes:
        calls.append(url)
        if "esearch" in url:
            return json.dumps({"esearchresult": {"idlist": ["111"]}}).encode()
        return json.dumps({"result": {"uids": ["111"], "111": {
            "title": "Zinc for the common cold.", "fulljournalname": "The Cochrane database of systematic reviews",
            "pubdate": "2024 May 9", "pubtype": ["Systematic Review"], "articleids": [{"idtype": "doi", "value": "10.1002/x"}],
        }}}).encode()

    client = bfp.PubMed(cache_dir=tmp_path, fetch=fake_fetch)
    [item] = client.search("zinc", 5)
    assert item == {
        "pmid": "111", "doi": "10.1002/x", "title": "Zinc for the common cold.", "journal": "The Cochrane database of systematic reviews",
        "year": "2024", "tipo_estudio": "cochrane", "url": "https://pubmed.ncbi.nlm.nih.gov/111/",
    }
    assert all("tool=suplematch-fuentes-primarias" in url for url in calls)
    client.search("zinc", 5)
    assert len(calls) == 2  # segunda vez desde la cache
