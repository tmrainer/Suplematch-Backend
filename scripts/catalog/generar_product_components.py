"""Genera `product_components.csv` (RS DIGEMID -> ingrediente -> component_id) desde la composicion DIGEMID.

Reconstruye el generador que nunca estuvo en el repo. El CSV legado mezclaba metodos y su
`fuzzy_translated` producia errores graves (93 filas de creatina mapeadas a Vitamina C; VITAMINA B1/B2 a B12).

Reglas:
1. La composicion se parsea con `scripts/catalog/parser_composicion.parse_composition` (dosis, unidad, sal).
2. El ingrediente se resuelve a `component_id` por prioridad:
   manual_alias (scraper) > knowledge_alias (modelo2 COMPONENT_ID_OVERRIDES) > diccionario ES/EN de
   nutrientes > nombre canonico del Component_Master (traducido) > alias legado exacto (score >= 95).
3. Guarda: nunca se asigna un componente si el ingrediente y el alias no comparten ningun token
   comparable (ver `coincidencia_nombres.tokens_comparables`). No hay fuzzy.
4. Lo que no se resuelve queda con component_id vacio y method `unmapped` para auditoria; el builder
   del catalogo ignora filas con score < 85.

Uso:
  python scripts/catalog/generar_product_components.py \
      --digemid data/raw/digemid/digemid_limpio.csv \
      --master data/training/supplement_model/Component_Master_Clean.csv \
      --legacy data/training/supplement_model/product_components.csv \
      --out data/training/supplement_model/product_components.csv --report-out data/reports/catalog/product_components_report.json
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from scripts.catalog.coincidencia_nombres import NUTRIENT_SYNONYMS, tokens_comparables  # noqa: E402
from scripts.catalog.parser_composicion import parse_composition  # noqa: E402

DEFAULT_DIGEMID = ROOT_DIR / "data/raw/digemid/digemid_limpio.csv"
DEFAULT_MASTER = ROOT_DIR / "data/training/supplement_model/Component_Master_Clean.csv"
DEFAULT_LEGACY = ROOT_DIR / "data/training/supplement_model/product_components.csv"
DEFAULT_OUT = ROOT_DIR / "data/training/supplement_model/product_components.csv"
DEFAULT_REPORT = ROOT_DIR / "data/reports/catalog/product_components_report.json"

OUTPUT_FIELDS = ["item", "ingredient", "amount", "unit", "amount_mg", "component_id", "match_score", "match_method", "salt_form"]

# Palabras de sal/forma que no identifican al nutriente.
SALT_WORDS = {
    "CLORHIDRATO", "HIDROCLORURO", "SULFATO", "CITRATO", "GLUCONATO", "OXIDO", "CARBONATO", "BISGLICINATO",
    "GLICINATO", "PICOLINATO", "ASCORBATO", "MONOHIDRATO", "MONOHIDRATADA", "ACETATO", "PALMITATO", "FUMARATO",
    "FOSFATO", "LACTATO", "MALATO", "TAURATO", "TREONATO", "OROTATO", "QUELATO", "AMINOQUELADO", "AMINOQUELATO",
    "PIDOLATO", "SUCCINATO", "NITRATO", "HCL", "DE", "DEL", "LA", "EL", "COMO", "EQUIVALENTE", "A", "EN", "FORMA",
    "POLVO", "EXTRACTO", "SECO", "ESTANDARIZADO", "SODICO", "SODIO", "POTASICO", "CALCICO", "MAGNESICO", "FERROSO",
    "FERRICO", "D", "L", "DL", "ALFA", "BETA", "GAMMA",
}

# Nutriente (ES, sin tildes, mayusculas) -> nombre canonico EN del Component_Master.
NUTRIENT_ES_EN: dict[str, str] = {
    "VITAMINA A": "Vitamin A", "RETINOL": "Vitamin A", "BETACAROTENO": "Vitamin A", "BETA CAROTENO": "Vitamin A",
    "VITAMINA B1": "Thiamin", "TIAMINA": "Thiamin", "VITAMINA B2": "Riboflavin", "RIBOFLAVINA": "Riboflavin",
    "VITAMINA B3": "Niacin", "NIACINA": "Niacin", "NICOTINAMIDA": "Niacin", "NIACINAMIDA": "Niacin",
    "VITAMINA B5": "Pantothenic Acid", "ACIDO PANTOTENICO": "Pantothenic Acid", "PANTOTENATO": "Pantothenic Acid",
    "VITAMINA B6": "Vitamin B6", "PIRIDOXINA": "Vitamin B6", "PIRIDOXAL": "Vitamin B6",
    "VITAMINA B7": "Biotin", "BIOTINA": "Biotin", "VITAMINA H": "Biotin",
    "VITAMINA B9": "Folate", "ACIDO FOLICO": "Folate", "FOLATO": "Folate", "METILFOLATO": "Folate", "FOLACINA": "Folate",
    "VITAMINA B12": "Vitamin B12", "CIANOCOBALAMINA": "Vitamin B12", "METILCOBALAMINA": "Vitamin B12", "COBALAMINA": "Vitamin B12",
    "VITAMINA C": "Vitamin C", "ACIDO ASCORBICO": "Vitamin C", "ACIDO L ASCORBICO": "Vitamin C", "ASCORBATO": "Vitamin C",
    "VITAMINA D": "Vitamin D", "VITAMINA D3": "Vitamin D", "VITAMINA D2": "Vitamin D", "COLECALCIFEROL": "Vitamin D", "ERGOCALCIFEROL": "Vitamin D",
    "VITAMINA E": "Vitamin E", "TOCOFEROL": "Vitamin E", "TOCOFEROLES": "Vitamin E", "ACETATO DE TOCOFEROL": "Vitamin E",
    "VITAMINA K": "Vitamin K", "VITAMINA K1": "Vitamin K", "VITAMINA K2": "Vitamin K", "FITOMENADIONA": "Vitamin K", "MENAQUINONA": "Vitamin K",
    "ZINC": "Zinc", "CINC": "Zinc", "HIERRO": "Iron", "FIERRO": "Iron", "CALCIO": "Calcium", "MAGNESIO": "Magnesium",
    "SELENIO": "Selenium", "YODO": "Iodine", "IODO": "Iodine", "YODURO": "Iodine", "CROMO": "Chromium", "COBRE": "Copper",
    "MANGANESO": "Manganese", "POTASIO": "Potassium", "FOSFORO": "Phosphorus", "MOLIBDENO": "Molybdenum", "BORO": "Boron",
    "OMEGA 3": "Omega-3 Fatty Acids", "ACEITE DE PESCADO": "Omega-3 Fatty Acids", "ACIDOS GRASOS OMEGA 3": "Omega-3 Fatty Acids",
    "EPA": "EPA", "ACIDO EICOSAPENTAENOICO": "EPA", "DHA": "DHA", "ACIDO DOCOSAHEXAENOICO": "DHA",
    "COLAGENO": "Collagen", "COLAGENO HIDROLIZADO": "Collagen", "COENZIMA Q10": "Coenzyme Q10", "UBIQUINONA": "Coenzyme Q10", "UBIQUINOL": "Coenzyme Q10",
    "CREATINA": "Creatine", "CARNITINA": "Carnitine", "L CARNITINA": "Carnitine", "MELATONINA": "Melatonin", "COLINA": "Choline",
    "LUTEINA": "Lutein", "ZEAXANTINA": "Zeaxanthin", "GLUCOSAMINA": "Glucosamine", "CONDROITINA": "Chondroitin",
    "PROBIOTICOS": "Probiotics", "LACTOBACILLUS": "Lactobacillus", "BIFIDOBACTERIUM": "Bifidobacterium",
    "CAFEINA": "Caffeine", "TAURINA": "Taurine", "TEANINA": "L-Theanine", "L TEANINA": "L-Theanine", "ASHWAGANDHA": "Ashwagandha",
    "VALERIANA": "Valerian", "CURCUMA": "Turmeric", "CURCUMINA": "Turmeric", "JENGIBRE": "Ginger", "AJO": "Garlic",
    "PROTEINA": "Protein", "PROTEINA DE SUERO": "Whey Protein", "WHEY": "Whey Protein", "FIBRA": "Fiber", "INULINA": "Inulin",
    "GLUTAMINA": "L-Glutamine", "ARGININA": "L-Arginine", "LISINA": "L-Lysine", "LEUCINA": "L-Leucine", "TRIPTOFANO": "L-Tryptophan",
    "BIOFLAVONOIDES": "Bioflavonoids", "RUTINA": "Rutin", "QUERCETINA": "Quercetin", "RESVERATROL": "Resveratrol",
    "SILICIO": "Silicon", "VANADIO": "Vanadium", "LITIO": "Lithium", "ESPIRULINA": "Spirulina", "MACA": "Maca", "GINSENG": "Ginseng",
}


# Patrones que identifican el nutriente aunque venga como sal con contraion ("IODURO DE POTASIO" es yodo,
# no potasio; "SELENITO DE SODIO" es selenio). Se evaluan antes que cualquier otro alias.
NUTRIENT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(IODURO|YODURO|IODATO|YODATO|YODO|IODO)\b"), "Iodine"),
    (re.compile(r"\b(SELENITO|SELENATO|SELENIO|SELENOMETIONINA|SELENIUM)\b"), "Selenium"),
    (re.compile(r"\b(FERROSO|FERRICO|HIERRO|FIERRO|IRON)\b"), "Iron"),
    (re.compile(r"\b(ZINC|CINC)\b"), "Zinc"),
    (re.compile(r"\b(CUPRICO|CUPROSO|COBRE|COPPER)\b"), "Copper"),
    (re.compile(r"\b(MANGANOSO|MANGANESO|MANGANESE)\b"), "Manganese"),
    (re.compile(r"\b(CROMO|CHROMIUM)\b"), "Chromium"),
    (re.compile(r"\b(MOLIBDATO|MOLIBDENO)\b"), "Molybdenum"),
    (re.compile(r"\bTOCOFER(OL|ILO|OLES|YL)\b|\bVITAMINA E\b"), "Vitamin E"),
    (re.compile(r"\b(COLECALCIFEROL|ERGOCALCIFEROL|CALCIFEROL|VITAMINA D\d?)\b"), "Vitamin D"),
    (re.compile(r"\b(CIANOCOBALAMINA|METILCOBALAMINA|HIDROXOCOBALAMINA|COBALAMINA|VITAMINA B12)\b"), "Vitamin B12"),
    (re.compile(r"\bPIRIDOX\w*|\bVITAMINA B6\b"), "Vitamin B6"),
    (re.compile(r"\b(RIBOFLAVINA|VITAMINA B2)\b"), "Riboflavin"),
    (re.compile(r"\b(TIAMINA|VITAMINA B1)\b"), "Thiamin"),
    (re.compile(r"\b(NICOTINAMIDA|NIACINAMIDA|NIACINA|VITAMINA B3)\b"), "Niacin"),
    (re.compile(r"\bPANTOTEN\w*|\bVITAMINA B5\b"), "Pantothenic Acid"),
    (re.compile(r"\b(BIOTINA|VITAMINA B7|VITAMINA H)\b"), "Biotin"),
    (re.compile(r"\b(FOLICO|FOLATO|METILFOLATO|FOLINICO|VITAMINA B9)\b"), "Folate"),
    (re.compile(r"\b(ASCORBICO|ASCORBATO|VITAMINA C)\b"), "Vitamin C"),
    (re.compile(r"\b(RETINOL|RETINILO|RETINIL|BETACAROTENO|BETA CAROTENO|VITAMINA A)\b"), "Vitamin A"),
    (re.compile(r"\b(FITOMENADIONA|MENAQUINONA|FILOQUINONA|VITAMINA K\d?)\b"), "Vitamin K"),
    (re.compile(r"(?<!PAN)(?<!PANC)CREATIN[AE]\b"), "Creatine"),  # incluye TRICREATINA/DICREATINA; excluye PANCREATINA
    (re.compile(r"\bOMEGA 3\b|\bACEITE DE PESCADO\b"), "Omega-3 Fatty Acids"),
    (re.compile(r"\b(DHA|DOCOSAHEXAENOICO)\b"), "DHA"),
    (re.compile(r"\b(EPA|EICOSAPENTAENOICO)\b"), "EPA"),
    (re.compile(r"\bCOLAGENO\b"), "Collagen"),
    (re.compile(r"\b(MAGNESIO|MAGNESIUM)\b"), "Magnesium"),
    (re.compile(r"\b(CALCIO|CALCICO|DICALCICO|TRICALCICO|CALCIUM)\b"), "Calcium"),
    (re.compile(r"\b(POTASIO|POTASICO|POTASSIUM)\b"), "Potassium"),
]


def _ascii_upper(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).upper()


def normalize_key(value: str) -> str:
    text = _ascii_upper(value)
    text = re.sub(r"\(.*?\)", " ", text)
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def core_nutrient_key(value: str) -> str:
    """Quita sales/formas: 'CLORHIDRATO DE PIRIDOXINA' -> 'PIRIDOXINA'; 'SULFATO FERROSO' -> '' (se resuelve por FERROSO aparte)."""
    tokens = [t for t in normalize_key(value).split() if t not in SALT_WORDS and not t.isdigit()]
    return " ".join(tokens)


def split_camel(value: str) -> list[str]:
    parts = re.split(r"(?<=[a-z0-9\)])(?=[A-Z])", str(value or ""))
    return [p.strip() for p in parts if p and p.strip()]


class ComponentResolver:
    def __init__(self, master_rows: list[dict[str, str]], legacy_rows: list[dict[str, str]], manual_aliases: dict[str, list[str]], knowledge_ids: dict[str, str]):
        self.id_by_canonical: dict[str, str] = {}
        self.alias_to_id: dict[str, tuple[str, str, float]] = {}  # key -> (component_id, method, score)
        self.canonical_by_id: dict[str, str] = {}

        for row in master_rows:
            cid = row["component_id"].strip()
            for name in split_camel(row["canonical_name"]):
                key = normalize_key(name)
                if key and key not in self.id_by_canonical:
                    self.id_by_canonical[key] = cid
                self.canonical_by_id.setdefault(cid, name)

        # 1) alias manuales del scraper
        for cid, aliases in manual_aliases.items():
            for alias in aliases:
                self._add(normalize_key(alias), cid, "manual_alias", 100.0)
        # 2) alias de knowledge (modelo2): clave en espanol normalizado -> id
        for es_name, cid in knowledge_ids.items():
            self._add(normalize_key(es_name), cid, "knowledge_alias", 100.0)
        # Id preferido por nombre canonico EN: el de la knowledge base si existe (el master tiene
        # duplicados: "Vitamin C" y "ascorbic acid", "Folate" y "FolateFolacin"...).
        self.preferred_id_by_en: dict[str, str] = {}
        knowledge_norm = {normalize_key(k): v for k, v in knowledge_ids.items()}
        for es_name, en_name in NUTRIENT_ES_EN.items():
            kid = knowledge_norm.get(normalize_key(es_name))
            if kid and en_name not in self.preferred_id_by_en:
                self.preferred_id_by_en[en_name] = kid
        # 3) diccionario ES/EN -> id preferido (knowledge) o del master por nombre canonico
        for es_name, en_name in NUTRIENT_ES_EN.items():
            cid = self.preferred_id_by_en.get(en_name) or self._id_for_canonical(en_name)
            if cid:
                self.canonical_by_id.setdefault(cid, en_name)
                self._add(normalize_key(es_name), cid, "exact_translated", 98.0)
                self._add(normalize_key(en_name), cid, "exact_translated", 98.0)
        # 4) nombres canonicos EN del master tal cual (solo si no hay id preferido para ese nombre)
        for key, cid in self.id_by_canonical.items():
            self._add(key, cid, "exact_master", 95.0)
        # 5) legado: NO se usa como fuente de alias. Sus metodos exact_translated/fuzzy_translated
        #    mapeaban VITAMINA B1/B2 a B12 y creatina a vitamina C. Solo sirve para el informe de cambios.
        for row in []:
            method = (row.get("match_method") or "").strip()
            try:
                score = float(row.get("match_score") or 0)
            except ValueError:
                score = 0.0
            cid = (row.get("component_id") or "").strip()
            if method not in {"exact_es", "exact_translated", "manual_alias"} or score < 95 or not cid:
                continue
            key = normalize_key(row.get("ingredient") or "")
            if key in self.alias_to_id:
                continue
            if self._shares_tokens(key, cid):
                self._add(key, cid, "legacy_exact", 95.0)

    def _add(self, key: str, cid: str, method: str, score: float) -> None:
        if key and cid and key not in self.alias_to_id:
            self.alias_to_id[key] = (cid, method, score)

    def _id_for_canonical(self, en_name: str) -> str | None:
        key = normalize_key(en_name)
        if key in self.id_by_canonical:
            return self.id_by_canonical[key]
        # tolerar guiones/espacios: "Omega-3 Fatty Acids" vs "OMEGA 3 FATTY ACIDS"
        for canonical, cid in self.id_by_canonical.items():
            if canonical.replace(" ", "") == key.replace(" ", ""):
                return cid
        return None

    def _shares_tokens(self, ingredient_key: str, cid: str) -> bool:
        canonical = self.canonical_by_id.get(cid, "")
        ing_tokens = tokens_comparables(ingredient_key)
        can_tokens = tokens_comparables(canonical)
        # tokens del ingrediente traducidos por el diccionario ES/EN
        translated = set()
        for es_name, en_name in NUTRIENT_ES_EN.items():
            if normalize_key(es_name) in ingredient_key:
                translated |= tokens_comparables(en_name)
        return bool((ing_tokens | translated) & can_tokens)

    def id_for_en(self, en_name: str) -> str | None:
        return self.preferred_id_by_en.get(en_name) or self._id_for_canonical(en_name)

    def resolve(self, ingredient: str, salt_form: str | None) -> tuple[str, str, float]:
        key_full = normalize_key(ingredient)
        for pattern, en_name in NUTRIENT_PATTERNS:
            if pattern.search(f" {key_full} "):
                cid = self.id_for_en(en_name)
                if cid:
                    return cid, "nutrient_pattern", 99.0
        candidates = [key_full, core_nutrient_key(ingredient)]
        if salt_form:
            candidates.append(core_nutrient_key(salt_form))
        # frases largas primero: "ACIDO L ASCORBICO" contiene "ACIDO ASCORBICO"? no; probar subfrases del diccionario
        for key in candidates:
            if key in self.alias_to_id:
                cid, method, score = self.alias_to_id[key]
                if self._shares_tokens(key, cid) or method in {"manual_alias", "knowledge_alias"}:
                    return cid, method, score
        # subfrase: el ingrediente contiene un alias conocido completo (limites de palabra), elegir el mas largo
        text = f" {normalize_key(ingredient)} "
        best: tuple[int, str, str, float] | None = None
        for key, (cid, method, score) in self.alias_to_id.items():
            if len(key) < 4 or f" {key} " not in text:
                continue
            if method in {"legacy_exact", "exact_master"} and not self._shares_tokens(key, cid):
                continue
            if best is None or len(key) > best[0]:
                best = (len(key), cid, "contains_alias", min(score, 90.0))
        if best:
            return best[1], best[2], best[3]
        return "", "unmapped", 0.0


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_manual_aliases() -> dict[str, list[str]]:
    from scripts.scraping.scraper_suplementos import MANUAL_COMPONENT_ALIASES

    return MANUAL_COMPONENT_ALIASES


def load_knowledge_ids() -> dict[str, str]:
    from app.ml.runtime.modelo2_inference import COMPONENT_ID_OVERRIDES

    return COMPONENT_ID_OVERRIDES


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--digemid", type=Path, default=DEFAULT_DIGEMID)
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    parser.add_argument("--legacy", type=Path, default=DEFAULT_LEGACY)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    digemid = read_csv(args.digemid)
    master = read_csv(args.master)
    legacy = read_csv(args.legacy) if args.legacy and args.legacy.exists() else []
    resolver = ComponentResolver(master, legacy, load_manual_aliases(), load_knowledge_ids())

    legacy_by_key: dict[tuple[str, str], str] = {}
    for row in legacy:
        legacy_by_key[(row["item"].strip().upper(), normalize_key(row["ingredient"]))] = (row.get("component_id") or "").strip()

    out_rows: list[dict[str, object]] = []
    methods: Counter[str] = Counter()
    unmapped: Counter[str] = Counter()
    changed: Counter[str] = Counter()
    for row in digemid:
        rs = (row.get("item") or "").strip()
        composition = row.get("Composición") or row.get("Composicion") or ""
        if not rs or not composition.strip():
            continue
        for part in parse_composition(composition):
            ingredient = str(part.get("ingredient") or "").strip()
            if not ingredient:
                continue
            cid, method, score = resolver.resolve(ingredient, part.get("salt_form"))
            methods[method] += 1
            if not cid:
                unmapped[ingredient] += 1
            previous = legacy_by_key.get((rs.upper(), normalize_key(ingredient)))
            if previous is not None and previous and cid and previous != cid:
                changed[f"{ingredient}: {previous} -> {cid}"] += 1
            out_rows.append(
                {
                    "item": rs,
                    "ingredient": ingredient,
                    "amount": part.get("amount") if part.get("amount") is not None else "",
                    "unit": part.get("unit") or "",
                    "amount_mg": part.get("amount_mg") if part.get("amount_mg") is not None else "",
                    "component_id": cid,
                    "match_score": score,
                    "match_method": method,
                    "salt_form": part.get("salt_form") or "",
                }
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(out_rows)

    mapped = sum(1 for r in out_rows if r["component_id"])
    report = {
        "digemid_rows": len(digemid),
        "component_rows": len(out_rows),
        "mapped_rows": mapped,
        "mapped_ratio": round(mapped / max(len(out_rows), 1), 4),
        "rs_with_any_mapping": len({r["item"] for r in out_rows if r["component_id"]}),
        "by_method": dict(methods.most_common()),
        "unmapped_top": unmapped.most_common(40),
        "changed_vs_legacy_top": changed.most_common(40),
        "changed_vs_legacy_total": sum(changed.values()),
        "out": str(args.out),
    }
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in {"unmapped_top", "changed_vs_legacy_top"}}, indent=2, ensure_ascii=False))
    print("unmapped_top:", unmapped.most_common(15))
    print("changed_vs_legacy_top:", changed.most_common(10))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
