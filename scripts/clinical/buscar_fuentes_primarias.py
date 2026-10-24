"""Candidatos de fuentes primarias (PubMed) por cada claim de `component_claim_evidence.csv`.

Plan de fiabilidad, Fase 2: las fuentes actuales son fichas generales (NIH ODS, NCCIH, MedlinePlus). Este script busca
en PubMed, con la API oficial E-utilities de NCBI, revisiones Cochrane, revisiones sistematicas/metaanalisis y
ensayos aleatorizados en humanos para cada claim, y deja los candidatos en un CSV para que el nutricionista los
acepte o descarte. **No modifica las tablas clinicas**: aceptar una fuente es una decision humana que pasa por
`scripts/clinical/manifiesto_reglas.py --approve`.

Salida: data/reports/clinical_review/fuentes_primarias_candidatas.csv (una fila por claim y candidato, con columnas
vacias `revision_acepta` y `revision_nota`). Las respuestas de NCBI se guardan en data/raw/pubmed_cache para no
repetir consultas.

Uso:
  python scripts/clinical/buscar_fuentes_primarias.py                 # todos los claims, 3 candidatos por claim
  python scripts/clinical/buscar_fuentes_primarias.py --per-claim 5 --component "Vitamina D"
  NCBI_API_KEY=... python scripts/clinical/buscar_fuentes_primarias.py   # opcional: 10 consultas/s en vez de 3
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT_DIR = Path(__file__).resolve().parents[2]
CLAIMS_PATH = ROOT_DIR / "data/knowledge/component_claim_evidence.csv"
OUT_PATH = ROOT_DIR / "data/reports/clinical_review/fuentes_primarias_candidatas.csv"
CACHE_DIR = ROOT_DIR / "data/raw/pubmed_cache"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TOOL = "suplematch-fuentes-primarias"

# Termino de busqueda en ingles por componente (Title/Abstract). Cepas y extractos van con su nombre cientifico.
COMPONENT_TERMS: dict[str, str] = {
    "Vitamina D": '"vitamin D" OR cholecalciferol', "Vitamina B12": '"vitamin B12" OR cobalamin OR cyanocobalamin',
    "Hierro": '"iron supplementation" OR "oral iron"', "Magnesio": "magnesium", "Zinc": "zinc", "Calcio": '"calcium supplementation" OR "calcium supplements" OR "calcium intake"',
    "Vitamina C": '"vitamin C" OR "ascorbic acid"', "Ácido fólico": '"folic acid" OR folate', "Proteína": '"protein supplementation" OR "whey protein"',
    "Selenio": "selenium", "Vitamina K": '"vitamin K" OR phylloquinone OR menaquinone', "Omega 3": '"omega-3" OR "fish oil"',
    "Biotina": "biotin", "Melatonina": "melatonin", "Yodo": "iodine", "Vitamina A": '"vitamin A" OR retinol', "Vitamina E": '"vitamin E" OR tocopherol',
    "Cromo": "chromium", "Cobre": "copper", "Potasio": "potassium", "Probióticos": "probiotic*", "Colágeno": '"collagen peptides" OR "hydrolyzed collagen"',
    "Coenzima Q10": '"coenzyme Q10" OR ubiquinone', "Ashwagandha": '"Withania somnifera" OR ashwagandha', "Valeriana": "valerian*",
    "L-teanina": '"L-theanine" OR theanine', "Vitamina B6": '"vitamin B6" OR pyridoxine', "Riboflavina": "riboflavin", "Tiamina": "thiamine",
    "Niacina": 'niacin OR "nicotinic acid"', "Ácido pantoténico": '"pantothenic acid"', "Carnitina": "carnitine", "Cafeína": "caffeine",
    "Té verde": '"green tea extract" OR EGCG', "EPA": '"eicosapentaenoic acid"', "DHA": '"docosahexaenoic acid"', "Creatina": '"creatine supplementation"',
    "Luteína": "lutein", "Zeaxantina": "zeaxanthin", "Colina": '"choline supplementation" OR "dietary choline" OR citicoline', "Sodio": '"sodium intake"', "Taurina": "taurine", "Inositol": "inositol",
    "Bacillus coagulans": '"Bacillus coagulans"', "Bifidobacterium longum": '"Bifidobacterium longum"',
}
# Desenlace en ingles por claim_code. Los claims de seguridad buscan efectos adversos o interacciones.
CLAIM_OUTCOMES: dict[str, str] = {
    "supports_vitamin_d_status": '"vitamin D deficiency" OR "25-hydroxyvitamin D"', "supports_b12_status": '"vitamin B12 deficiency"',
    "supports_iron_status": '"iron deficiency" OR anemia OR ferritin', "supports_magnesium_intake": '"magnesium deficiency" OR "serum magnesium"',
    "supports_zinc_status": '"zinc deficiency" OR immune OR infection', "supports_bone_health": '"bone mineral density" OR fracture',
    "supports_vitamin_c_status": '"vitamin C deficiency" OR "plasma ascorbate"', "supports_folate_status": '"folate deficiency" OR "neural tube"',
    "supports_protein_gap": '"muscle mass" OR "lean mass" OR sarcopenia', "antioxidant_immune_context": "immune OR antioxidant",
    "bone_clotting_context": '"bone mineral density" OR fracture OR osteoporosis', "supports_dietary_gap": "cardiovascular OR triglycerides",
    "hair_skin_nails_context": "hair OR nail OR skin", "sleep_timing_context": '"sleep onset" OR insomnia OR "jet lag"',
    "thyroid_sensitive": "thyroid", "skin_vision_context": "vision OR skin", "antioxidant_context": "antioxidant OR mortality",
    "glucose_context": '"glycemic control" OR HbA1c OR glucose', "mineral_balance": '"copper deficiency" OR zinc', "electrolyte_context": '"blood pressure"',
    "strain_specific": "diarrhea OR \"gut microbiota\"", "skin_structure_context": '"skin elasticity" OR "skin hydration" OR wrinkles',
    "energy_cardiometabolic_context": 'fatigue OR "heart failure" OR statin', "stress_context": 'stress OR anxiety OR cortisol', "sleep_context": "sleep OR insomnia",
    "relaxation_context": "stress OR anxiety OR sleep", "metabolism_context": "homocysteine OR deficiency", "energy_metabolism": "deficiency OR fatigue OR migraine",
    "energy_lipid_safety": "lipids OR flushing OR \"adverse effects\"", "coenzyme_context": "deficiency OR lipids", "performance_context": '"exercise performance" OR "muscle strength"',
    "alertness_context": '"cognitive performance" OR alertness OR "exercise performance"', "herbal_extract_safety": 'hepatotoxicity OR "liver injury"',
    "omega3_subcomponent": "cardiovascular OR triglycerides OR cognition", "iron_absorption_support": '"iron absorption"',
    "folate_b12_context": '"folic acid" AND "vitamin B12 deficiency"', "b12_masking_context": '"vitamin B12 deficiency" OR "masking"',
    "bone_anticoagulant_context": "warfarin OR anticoagulant", "lipid_antioxidant_context": '"vitamin E" AND (bleeding OR mortality OR "adverse effects")',
    "immune_thyroid_context": "thyroid OR immune", "gut_immune_context": '"respiratory infection" OR "gut microbiota"',
    "hair_skin_lab_context": '"hair loss" OR alopecia', "renal_bone_safety_context": '"kidney stones" OR "cardiovascular events"',
    "thyroid_safety_context": '"thyroid dysfunction" OR hyperthyroidism', "stress_thyroid_liver_context": 'hepatotoxicity OR thyroid OR "liver injury"',
    "visual_carotenoid_context": '"macular degeneration" OR "visual function"', "nervous_system_context": "cognition OR \"liver\"",
    "electrolyte_safety_context": '"blood pressure" OR hypertension', "nutritional_context": '"exercise performance" OR metabolic OR "polycystic ovary"',
    "probiotic_strain_context": '"irritable bowel" OR diarrhea OR "gut microbiota"',
}
STUDY_FILTER = '(systematic[sb] OR "meta-analysis"[pt] OR "randomized controlled trial"[pt]) AND humans[mh]'
CANDIDATE_COLUMNS = (
    "component", "claim_code", "claim", "evidence_level", "fuente_actual", "query", "rank", "pmid", "doi", "title", "journal", "year",
    "tipo_estudio", "url", "revision_acepta", "revision_nota",
)


def tag_terms(expression: str, tag: str = "[tiab]") -> str:
    """PubMed no aplica una etiqueta a un grupo entre parentesis: se etiqueta cada termino de un OR."""
    if " AND " in expression:  # expresion ya compuesta (p. ej. dos conceptos): se deja en todos los campos
        return f"({expression})"
    return "(" + " OR ".join(f"{part.strip()}{tag}" for part in expression.split(" OR ")) + ")"


def build_query(component: str, claim_code: str, claim_type: str = "", component_tag: str = "[tiab]") -> str | None:
    """Consulta PubMed. ``component_tag="[ti]"`` exige el componente en el titulo (mas preciso, menos resultados)."""
    term, outcome = COMPONENT_TERMS.get(component), CLAIM_OUTCOMES.get(claim_code)
    if not term or not outcome:
        return None
    query = f"{tag_terms(term, component_tag)} AND {tag_terms(outcome)}"
    if claim_type.startswith("deficiency"):  # reposicion: estudios de suplementacion, no solo de prevalencia
        query += " AND (supplement*[tiab] OR repletion[tiab] OR treatment[tiab])"
    return f"{query} AND {STUDY_FILTER}"


def study_type(pub_types: list[str], journal: str) -> str:
    """Nivel de la evidencia segun el tipo de publicacion: Cochrane > revision sistematica/metaanalisis > ECA."""
    types = {item.lower() for item in pub_types}
    if "cochrane" in journal.lower():
        return "cochrane"
    if "meta-analysis" in types or "systematic review" in types:
        return "revision_sistematica"
    if "randomized controlled trial" in types:
        return "eca"
    return "otro"


def parse_summary(uid: str, item: dict[str, Any]) -> dict[str, Any]:
    doi = next((a.get("value") for a in item.get("articleids", []) if a.get("idtype") == "doi"), "")
    journal = item.get("fulljournalname") or item.get("source") or ""
    return {
        "pmid": uid,
        "doi": doi,
        "title": (item.get("title") or "").strip(),
        "journal": journal,
        "year": (item.get("pubdate") or "")[:4],
        "tipo_estudio": study_type(item.get("pubtype") or [], journal),
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{uid}/",
    }


TYPE_ORDER = {"cochrane": 0, "revision_sistematica": 1, "eca": 2, "otro": 3}


def rank_candidates(candidates: list[dict[str, Any]], per_claim: int) -> list[dict[str, Any]]:
    """Relevancia de PubMed primero: entre los 2*per_claim mas relevantes, Cochrane > revision > ECA (estable)."""
    window = candidates[: 2 * per_claim]
    return sorted(window, key=lambda c: TYPE_ORDER[c["tipo_estudio"]])[:per_claim]


class PubMed:
    """Cliente minimo de E-utilities con cache en disco y limite de 3 consultas/s (10 con NCBI_API_KEY)."""

    def __init__(self, cache_dir: Path = CACHE_DIR, fetch: Callable[[str], bytes] | None = None):
        self.cache_dir = cache_dir
        self.api_key = os.environ.get("NCBI_API_KEY", "")
        self.delay = 0.12 if self.api_key else 0.4
        self._fetch = fetch or self._http
        self._last = 0.0

    def _http(self, url: str) -> bytes:
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        with urlopen(Request(url, headers={"User-Agent": TOOL}), timeout=60) as response:
            return response.read()

    def _get(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        params = {**params, "retmode": "json", "tool": TOOL, **({"api_key": self.api_key} if self.api_key else {})}
        url = f"{EUTILS}/{endpoint}.fcgi?{urlencode(params)}"
        key = hashlib.sha256(f"{endpoint}?{urlencode({k: v for k, v in params.items() if k != 'api_key'})}".encode()).hexdigest()[:24]
        cached = self.cache_dir / f"{key}.json"
        if cached.exists():
            return json.loads(cached.read_text(encoding="utf-8"))
        data = json.loads(self._fetch(url))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(data), encoding="utf-8")
        return data

    def search(self, query: str, retmax: int) -> list[dict[str, Any]]:
        ids = self._get("esearch", {"db": "pubmed", "term": query, "retmax": str(retmax), "sort": "relevance"})["esearchresult"].get("idlist", [])
        if not ids:
            return []
        result = self._get("esummary", {"db": "pubmed", "id": ",".join(ids)})["result"]
        return [parse_summary(uid, result[uid]) for uid in result.get("uids", ids) if uid in result]


def read_claims(path: Path = CLAIMS_PATH) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def collect(claims: list[dict[str, str]], pubmed: PubMed, per_claim: int, pool: int) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    unmapped: list[str] = []
    for claim in claims:
        query = build_query(claim["component"], claim["claim_code"], claim.get("claim_type", ""), "[ti]")
        if query is None:
            unmapped.append(f"{claim['component']}|{claim['claim_code']}")
            continue
        base = {
            "component": claim["component"], "claim_code": claim["claim_code"], "claim": claim["claim"],
            "evidence_level": claim["evidence_level"], "fuente_actual": claim["source_ids"], "query": query,
        }
        candidates = rank_candidates(pubmed.search(query, pool), per_claim)
        if len(candidates) < per_claim:  # pocos con el componente en el titulo: se amplia a titulo o resumen
            query = build_query(claim["component"], claim["claim_code"], claim.get("claim_type", ""))
            seen = {c["pmid"] for c in candidates}
            extra = [c for c in rank_candidates(pubmed.search(query, pool), per_claim) if c["pmid"] not in seen]
            candidates += extra[: per_claim - len(candidates)]
            base["query"] = query
        if not candidates:
            rows.append({**base, "rank": 0, "title": "(sin resultados: revisar la consulta)"})
        for rank, candidate in enumerate(candidates, start=1):
            rows.append({**base, "rank": rank, **candidate})
    return rows, unmapped


def write_rows(rows: list[dict[str, Any]], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANDIDATE_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({column: row.get(column, "") for column in CANDIDATE_COLUMNS} for row in rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--per-claim", type=int, default=3, help="Candidatos por claim en el CSV.")
    parser.add_argument("--pool", type=int, default=20, help="Resultados de PubMed entre los que se elige (por relevancia).")
    parser.add_argument("--component", help="Solo los claims de este componente (nombre como en el CSV).")
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args(argv)

    claims = read_claims()
    if args.component:
        claims = [c for c in claims if c["component"] == args.component]
    rows, unmapped = collect(claims, PubMed(), args.per_claim, args.pool)
    write_rows(rows, args.out)
    found = {(r["component"], r["claim_code"]) for r in rows if r.get("pmid")}
    by_type: dict[str, int] = {}
    for row in rows:
        if row.get("pmid"):
            by_type[row["tipo_estudio"]] = by_type.get(row["tipo_estudio"], 0) + 1
    print(json.dumps({"claims": len(claims), "claims_con_candidatos": len(found), "candidatos": sum(1 for r in rows if r.get("pmid")),
                      "por_tipo": by_type, "sin_mapeo": unmapped, "salida": str(args.out)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
