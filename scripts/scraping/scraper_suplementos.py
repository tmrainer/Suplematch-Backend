from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import html
import io
import json
import os
import random
import re
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib import robotparser
from urllib.parse import quote_plus, unquote, urljoin, urlparse
from xml.etree import ElementTree

import httpx


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT_DIR / "data/raw/pharmacies/supplements_exhaustive_clean.csv"
DEFAULT_REJECTS = ROOT_DIR / "data/reports/scraping/supplements_rejected.csv"
DEFAULT_DIGEMID = ROOT_DIR / "data/raw/digemid/digemid_limpio.csv"
DEFAULT_COMPONENTS = ROOT_DIR / "data/training/supplement_model/product_components.csv"
DEFAULT_COMPONENT_MASTER = ROOT_DIR / "data/training/supplement_model/Component_Master_Clean.csv"
DEFAULT_IMAGE_DIR = ROOT_DIR / "data/raw/pharmacies/product_images"
REQUEST_TIMEOUT = httpx.Timeout(12.0, connect=5.0, read=8.0, write=5.0, pool=5.0)
USER_AGENT = "SupleMatch research price crawler/1.0 (+weekly catalog validation)"
MAX_RETRIES = 3
RETRY_BASE_SECONDS = 1.0
RETRY_MAX_SLEEP_SECONDS = 60.0
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
ALGOLIA_APP_ID_ENV = "INKAFARMA_ALGOLIA_APP_ID"
ALGOLIA_API_KEY_ENV = "INKAFARMA_ALGOLIA_API_KEY"
DETAIL_TEXT_LIMIT = 6000
OCR_IMAGE_BYTE_LIMIT = 4_000_000
NAME_MATCH_THRESHOLD = 0.94

CSV_FIELDS = [
    "pharmacy",
    "commercial_name",
    "formal_name",
    "registro_sanitario",
    "price",
    "currency",
    "availability",
    "url",
    "sku",
    "brand",
    "source_strategy",
    "scraped_at",
    "stock",
    "component_text",
    "registro_sanitario_source",
    "component_traceable",
    "component_ids_detected",
    "component_names_detected",
    "image_url",
    "image_source",
    "image_local_path",
    "image_downloaded_at",
    "rejection_reason",
]

DEFAULT_SUPPLEMENT_TERMS = [
    "vitamina",
    "vitaminas",
    "suplemento",
    "suplementos",
    "complemento",
    "nutricional",
    "proteina",
    "proteína",
    "whey",
    "colageno",
    "colágeno",
    "magnesio",
    "zinc",
    "calcio",
    "hierro",
    "omega",
    "melatonina",
    "probiótico",
    "probiotico",
    "probióticos",
    "probioticos",
    "multivitaminico",
    "multivitamínico",
    "ensure",
    "glucerna",
    "pediasure",
    "centrum",
    "sunvit",
    "biotina",
    "creatina",
    "carnitina",
    "ashwagandha",
    "withania",
    "valeriana",
    "valerian",
    "teanina",
    "theanine",
    "l-teanina",
    "l theanine",
    "selenio",
    "folico",
    "fólico",
    "b12",
    "vitamin d",
    "vitamin c",
    "vitamin e",
    "vitamin b",
    "vitamin b12",
    "vitamina d",
    "vitamina c",
    "vitamina e",
    "vitamina b",
    "vitamina b12",
    "vitamina d3",
    "vitamina k",
    "vitamina k2",
    "vitamina a",
    "ácido fólico",
    "acido folico",
    "folato",
    "niacina",
    "riboflavina",
    "tiamina",
    "piridoxina",
    "cianocobalamina",
    "calcio citrato",
    "citrato de calcio",
    "citrato de magnesio",
    "óxido de magnesio",
    "oxido de magnesio",
    "sulfato de zinc",
    "gluconato de zinc",
    "colágeno hidrolizado",
    "colageno hidrolizado",
    "glucosamina",
    "condroitina",
    "luteína",
    "luteina",
    "taurina",
    "glutamina",
    "aminoácidos",
    "aminoacidos",
    "bcaa",
    "coenzima q10",
    "q10",
    "probióticos",
    "probioticos",
    "lactobacillus",
    "saccharomyces",
    "fibra",
    "inulina",
    "electrolitos",
    "minerales",
    "formula adultos",
    "fórmula adultos",
    "formulas adultos",
    "suplementos articulares",
    "nutricion",
    "nutrición",
]

SUPPLEMENT_HINTS = {
    "vitamina",
    "suplement",
    "complement",
    "nutric",
    "proteina",
    "proteína",
    "whey",
    "colageno",
    "colágeno",
    "magnesio",
    "zinc",
    "calcio",
    "hierro",
    "omega",
    "melatonina",
    "probi",
    "lactobacillus",
    "bifidobacterium",
    "bacillus clausii",
    "multivit",
    "biotina",
    "creatina",
    "carnitina",
    "ashwagandha",
    "withania",
    "valeriana",
    "valerian",
    "teanina",
    "theanine",
    "selenio",
    "folico",
    "fólico",
    "b12",
    "ensure",
    "glucerna",
    "pediasure",
    "centrum",
    "folato",
    "niacina",
    "riboflavina",
    "tiamina",
    "piridoxina",
    "cianocobalamina",
    "glucosamina",
    "condroitina",
    "luteina",
    "luteína",
    "taurina",
    "glutamina",
    "bcaa",
    "q10",
    "lactobacillus",
    "saccharomyces",
    "fibra",
    "inulina",
    "electrolito",
    "mineral",
    "articular",
}

STOP_TOKENS = {
    "PARA",
    "CON",
    "SIN",
    "LOS",
    "LAS",
    "DEL",
    "POR",
    "COMO",
    "TABLETA",
    "TABLETAS",
    "CAPSULA",
    "CAPSULAS",
    "CÁPSULA",
    "CÁPSULAS",
    "FRASCO",
    "CAJA",
    "POTE",
    "SOBRE",
    "LATA",
    "UNIDAD",
    "UNIDADES",
    "UND",
    "SOLUCION",
    "SOLUCIÓN",
    "PLUS",
    "TOTAL",
    "KIDS",
    "ADULTOS",
    "ADULTO",
}

GENERIC_ALIAS_TOKENS = {
    frozenset({"VITAMINA"}),
    frozenset({"VITAMIN"}),
    frozenset({"ACIDO"}),
    frozenset({"ACID"}),
    frozenset({"POR"}),
    frozenset({"DOSIS"}),
}

MANUAL_COMPONENT_ALIASES = {
    "COMP_7B47CDB437E8": [
        "CREATINA",
        "CREATINA MONOHIDRATO",
        "CREATINA MONOHIDRATADA",
        "CREATINE",
        "CREATINE MONOHYDRATE",
        "CREATINE MONOHYDRATE POWDER",
        "CLORHIDRATO DE CREATINA",
    ],
    "COMP_AE7EE271FD2C": [
        "ASHWAGANDHA",
        "WITHANIA",
        "WITHANIA SOMNIFERA",
        "KSM 66",
        "KSM-66",
        "EXTRACTO DE ASHWAGANDHA",
        "RAIZ DE ASHWAGANDHA",
    ],
    "COMP_D691B9C2718F": [
        "VALERIANA",
        "VALERIAN",
        "VALERIANA OFFICINALIS",
        "VALERIAN ROOT",
        "RAIZ DE VALERIANA",
        "EXTRACTO DE VALERIANA",
    ],
    "COMP_E3D7A2D1C909": [
        "L TEANINA",
        "L-TEANINA",
        "TEANINA",
        "L THEANINE",
        "L-THEANINE",
        "THEANINE",
    ],
    "COMP_5030A6666E7D": [
        "PROBIOTICOS",
        "PROBIÓTICOS",
        "PROBIOTICO",
        "PROBIÓTICO",
        "PROBIOTICS",
        "PROBIOTIC",
        "COMPLEJO PROBIOTICO",
        "COMPLEJO PROBIÓTICO",
    ],
    "COMP_C5CD8E1D6AAE": [
        "LACTOBACILLUS",
        "LACTOBACILLUS ACIDOPHILUS",
        "ACIDOPHILUS",
    ],
    "COMP_4C01A543D40D": [
        "BIFIDOBACTERIUM",
        "BIFIDOBACTERIUM BIFIDUM",
        "BIFIDUS",
    ],
}

# Codigos de registro sanitario DIGEMID. Formatos reales observados:
#   DE-03502, DE4606, N-12345, EE-00123            (letras + digitos)
#   I4100524E/NAABLB, P2802921E/NKPSFR              (letra + digitos + letra + "/" + sufijo)
# La version anterior aceptaba [A-Z0-9]{3,12} con IGNORECASE, de modo que palabras comunes como
# "para" o "Nutricion" se tomaban como RS. Ahora el codigo debe contener al menos 3 digitos y se acepta:
#   a) tras un marcador explicito ("R.S.", "RS:", "Registro Sanitario", "Reg. San."), o
#   b) en mayusculas, sin marcador, siempre que no le siga una unidad de medida
#      (evita "VITAMINA C DE 500 MG" -> "DE500").
RS_PREFIXES = r"(?:DE|EE|PNE|PN|DM|DB|N|I|P|E|Q|A)"
_RS_BODY = r"[-\s]?\d{3,8}[A-Z]{0,3}(?:/[A-Z0-9]{2,8})?"
RS_CODE_RE = re.compile(RS_PREFIXES + _RS_BODY)
REGISTRO_RE = re.compile(
    r"(?:"
    r"(?i:(?:N[°ºo]?\.?\s*)?(?:R\.?\s*S\.?|REG(?:ISTRO)?\.?\s+SAN(?:ITARIO)?\.?)\s*(?:N[°ºo]?\.?)?\s*[:#-]?\s*)"
    + RS_PREFIXES + _RS_BODY + r"\b"
    r"|"
    r"\b" + RS_PREFIXES + r"-?\d{3,8}[A-Z]{0,3}(?:/[A-Z0-9]{2,8})?\b(?!\s*(?:MG|MCG|G|GR|ML|L|KG|UI|IU|%)\b)"
    r")"
)


@dataclass
class ProductRow:
    pharmacy: str
    commercial_name: str
    formal_name: str
    registro_sanitario: str
    price: str
    currency: str
    availability: str
    url: str
    sku: str
    brand: str
    source_strategy: str
    scraped_at: str
    stock: str = ""
    component_text: str = ""
    registro_sanitario_source: str = ""
    component_traceable: str = "unknown"
    component_ids_detected: str = ""
    component_names_detected: str = ""
    image_url: str = ""
    image_source: str = ""
    image_local_path: str = ""
    image_downloaded_at: str = ""
    rejection_reason: str = ""


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_rs(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def normalize_name(value: Any) -> str:
    text = clean_text(value).upper()
    text = re.sub(r"[^A-Z0-9ÁÉÍÓÚÜÑ ]", " ", text)
    text = re.sub(r"\b(TABLETA|CAPSULA|CÁPSULA|FRASCO|CAJA|POTE|SOBRE|LATA|UN|ML|MG|G)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def name_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[A-ZÁÉÍÓÚÜÑ0-9]{2,}", normalize_name(value))
        if token not in STOP_TOKENS and not token.isdigit()
    }


def split_component_aliases(value: str) -> list[str]:
    text = clean_text(value)
    if not text:
        return []

    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", "|", text)
    pieces = re.split(r"[|;/,()]+", spaced)
    aliases = [piece.strip() for piece in pieces if len(piece.strip()) >= 3]
    aliases.append(text)
    return list(dict.fromkeys(aliases))


def contains_alias_phrase(haystack: str, alias_key: str) -> bool:
    if not alias_key:
        return False
    pattern = r"(?<![A-Z0-9])" + r"\s+".join(re.escape(part) for part in alias_key.split()) + r"(?![A-Z0-9])"
    return re.search(pattern, haystack) is not None


def score_name_match(query: str, query_tokens: set[str], digemid_name: str) -> float:
    """Puntua la similitud entre un nombre comercial normalizado y un nombre de producto DIGEMID.

    Reglas (todas exigen coincidencia por tokens completos, nunca substring):
    - Nombre DIGEMID de un solo token ("MAGNESIO", "PRO", "BIOTINA"): solo coincide si el nombre
      comercial, ya normalizado, es exactamente ese token. Antes, `"PRO" in query` asignaba el RS
      de "PRO" a Pantene Pro-V o Babylac Pro.
    - Nombre DIGEMID multi-token contenido como frase completa en el nombre comercial: 1.0.
    - Nombre comercial contenido como frase completa en el nombre DIGEMID (>= 2 tokens): 1.0.
    - Resto: al menos 2 tokens compartidos y ratio de SequenceMatcher.
    """
    digemid_tokens = name_tokens(digemid_name)
    if not digemid_tokens or not query_tokens:
        return 0.0

    if len(digemid_tokens) < 2:
        return 1.0 if query_tokens == digemid_tokens else 0.0

    shared = query_tokens.intersection(digemid_tokens)
    if len(shared) < 2:
        return 0.0

    if contains_alias_phrase(query, digemid_name):
        return 1.0
    if len(query_tokens) >= 2 and contains_alias_phrase(digemid_name, query):
        return 1.0

    return difflib.SequenceMatcher(None, query, digemid_name).ratio()


def parse_price(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}"
    text = str(value)
    text = text.replace(",", ".")
    match = re.search(r"\d+(?:\.\d+)?", text)
    return f"{float(match.group(0)):.2f}" if match else ""


def parse_int(value: Any) -> int:
    try:
        return int(float(str(value or "0").strip()))
    except (TypeError, ValueError):
        return 0


def price_from_minor_units(value: Any, minor_unit: int = 2) -> str:
    try:
        amount = float(value) / (10**minor_unit)
    except (TypeError, ValueError):
        return ""
    return f"{amount:.2f}"


def extract_registro(text: str) -> str:
    """Devuelve el primer codigo RS encontrado en el texto, normalizado (sin guiones ni espacios)."""
    for match in REGISTRO_RE.finditer(text or ""):
        code = RS_CODE_RE.search(match.group(0).upper())
        if code:
            return normalize_rs(code.group(0))
    return ""


def append_text(*values: Any, limit: int = DETAIL_TEXT_LIMIT) -> str:
    text = clean_text(" ".join(str(value or "") for value in values if clean_text(value)))
    return text[:limit]


def flattened_json_text(value: Any, *, limit: int = DETAIL_TEXT_LIMIT) -> str:
    pieces: list[str] = []

    def walk(item: Any) -> None:
        if len(" ".join(pieces)) > limit:
            return
        if isinstance(item, dict):
            for key, child in item.items():
                if any(skip in str(key).lower() for skip in ("image", "thumb", "url", "link")):
                    continue
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)
        elif isinstance(item, (str, int, float)):
            text = clean_text(item)
            if text:
                pieces.append(text)

    walk(value)
    return append_text(*pieces, limit=limit)


def extract_image_urls(value: Any, base_url: str = "") -> list[str]:
    urls: list[str] = []

    def add(url: Any) -> None:
        text = clean_text(url)
        if not text or len(text) > 500:
            return
        full = urljoin(base_url + "/", text) if base_url and not text.startswith(("http://", "https://")) else text
        parsed = urlparse(full)
        lower_path = parsed.path.lower()
        lower_query = parsed.query.lower()
        if not (
            any(lower_path.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp"))
            or any(marker in lower_query for marker in ("format=jpg", "format=jpeg", "format=png", "format=webp", "fm=jpg", "fm=webp"))
        ):
            return
        if full not in urls:
            urls.append(full)

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                key_text = str(key).lower()
                if any(marker in key_text for marker in ("image", "thumb", "url", "src", "link")):
                    add(child)
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)
        elif isinstance(item, str):
            add(item)

    walk(value)
    if isinstance(value, str):
        for src in re.findall(r'(?:src|data-src)=["\']([^"\']+)["\']', value, flags=re.IGNORECASE):
            add(src)
        for src in re.findall(r'https?://[^\s"\']+\.(?:jpg|jpeg|png|webp)', value, flags=re.IGNORECASE):
            add(src)
    return urls[:8]


def first_image_url(image_urls: list[str]) -> str:
    for image_url in image_urls:
        parsed = urlparse(image_url)
        host = parsed.netloc.lower()
        path = parsed.path.lower()
        if not parsed.scheme.startswith("http"):
            continue
        if any(skip in path for skip in ("placeholder", "default", "no-image", "no_image", "logo")):
            continue
        if any(skip in host for skip in ("facebook", "google", "analytics", "tagmanager")):
            continue
        return image_url
    return ""


def image_extension(image_url: str, content_type: str = "") -> str:
    path = urlparse(image_url).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    return ".jpg"


def image_ocr_text(client: httpx.Client, image_url: str, http: "PoliteHttp | None" = None) -> str:
    if shutil.which("tesseract") is None:
        return ""
    try:
        from PIL import Image, ImageOps
        import pytesseract

        http = http or PoliteHttp(client, delay=0.0)
        response = http.request(image_url)
        if response.status_code != 200 or not response.content or len(response.content) > OCR_IMAGE_BYTE_LIMIT:
            return ""
        image = Image.open(io.BytesIO(response.content))
        prepared = ImageOps.autocontrast(image.convert("L"))
        width, height = prepared.size
        if max(width, height) < 900:
            scale = 900 / max(width, height)
            prepared = prepared.resize((int(width * scale), int(height * scale)))
        return clean_text(pytesseract.image_to_string(prepared, lang="spa+eng", config="--psm 6"))
    except Exception:
        return ""


def first_registro_from_images(client: httpx.Client, image_urls: list[str], http: "PoliteHttp | None" = None) -> str:
    for image_url in image_urls:
        try:
            text = image_ocr_text(client, image_url, http=http)
        except RobotsDisallowed:
            continue
        registro = extract_registro(text)
        if registro:
            return registro
    return ""


def is_supplement(row: ProductRow) -> bool:
    haystack = f"{row.commercial_name} {row.formal_name} {row.brand} {row.component_text}".lower()
    return any(term in haystack for term in SUPPLEMENT_HINTS)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


class RegistryMatcher:
    def __init__(self, digemid_path: Path, components_path: Path, component_master_path: Path):
        self.digemid_rows = read_csv(digemid_path)
        self.components_by_rs = self._load_components(components_path)
        self.component_aliases = self._load_component_aliases(components_path, component_master_path)
        self.component_token_index: dict[str, set[int]] = {}
        for idx, (_component_id, alias_key, _display_name) in enumerate(self.component_aliases):
            for token in name_tokens(alias_key):
                self.component_token_index.setdefault(token, set()).add(idx)
        self.digemid_by_rs = {
            normalize_rs(row.get("item")): row
            for row in self.digemid_rows
            if normalize_rs(row.get("item"))
        }
        self.names = [
            (normalize_rs(row.get("item")), normalize_name(row.get("Producto")))
            for row in self.digemid_rows
            if normalize_rs(row.get("item")) and normalize_name(row.get("Producto"))
        ]
        self.name_token_index: dict[str, set[int]] = {}
        for idx, (_rs_key, digemid_name) in enumerate(self.names):
            for token in name_tokens(digemid_name):
                self.name_token_index.setdefault(token, set()).add(idx)

    def _load_components(self, path: Path) -> dict[str, list[dict[str, str]]]:
        rows = read_csv(path)
        grouped: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            rs_key = normalize_rs(row.get("item"))
            component_id = clean_text(row.get("component_id"))
            method = clean_text(row.get("match_method"))
            try:
                score = float(row.get("match_score") or 0)
            except ValueError:
                score = 0
            if not rs_key or not component_id or method in {"", "noise"} or score < 85:
                continue
            grouped.setdefault(rs_key, []).append(row)
        return grouped

    def _load_component_aliases(
        self,
        components_path: Path,
        component_master_path: Path,
    ) -> list[tuple[str, str, str]]:
        aliases: dict[tuple[str, str], str] = {}

        for component_id, manual_aliases in MANUAL_COMPONENT_ALIASES.items():
            for alias in manual_aliases:
                alias_key = normalize_name(alias)
                if len(alias_key) >= 4:
                    aliases[(component_id, alias_key)] = alias

        for row in read_csv(components_path):
            component_id = clean_text(row.get("component_id"))
            ingredient = clean_text(row.get("ingredient"))
            if not component_id or not ingredient:
                continue
            alias_key = normalize_name(ingredient)
            if len(alias_key) >= 4 and frozenset(name_tokens(alias_key)) not in GENERIC_ALIAS_TOKENS:
                aliases[(component_id, alias_key)] = ingredient

        for row in read_csv(component_master_path):
            component_id = clean_text(row.get("component_id"))
            canonical = clean_text(row.get("canonical_name"))
            if not component_id or not canonical:
                continue
            for alias in split_component_aliases(canonical):
                alias_key = normalize_name(alias)
                if len(alias_key) >= 4 and frozenset(name_tokens(alias_key)) not in GENERIC_ALIAS_TOKENS:
                    aliases[(component_id, alias_key)] = alias

        return [
            (component_id, alias_key, display_name)
            for (component_id, alias_key), display_name in aliases.items()
            if alias_key and len(alias_key) >= 3 and alias_key not in STOP_TOKENS
        ]

    def enrich(self, row: ProductRow, infer_missing_rs: bool) -> ProductRow:
        rs_key = normalize_rs(row.registro_sanitario)
        if rs_key and rs_key not in self.digemid_by_rs:
            row.rejection_reason = f"rs_no_en_digemid:{rs_key}"
            row.registro_sanitario = ""
            row.registro_sanitario_source = ""
            rs_key = ""

        if not rs_key and infer_missing_rs:
            inferred = self.infer_rs(row)
            if inferred:
                row.registro_sanitario = inferred
                row.registro_sanitario_source = "digemid_name_match"
                rs_key = normalize_rs(inferred)

        detected_components = self.detect_components(row)
        if detected_components:
            row.component_ids_detected = ";".join(component_id for component_id, _name in detected_components[:12])
            row.component_names_detected = ";".join(name for _component_id, name in detected_components[:12])

        if rs_key and rs_key in self.components_by_rs:
            row.component_traceable = "true_rs_component"
            if not row.component_text:
                row.component_text = "; ".join(
                    clean_text(component.get("ingredient"))
                    for component in self.components_by_rs[rs_key][:5]
                    if clean_text(component.get("ingredient"))
                )
        elif detected_components and rs_key:
            row.component_traceable = "true_component_name_with_rs_unmapped"
        elif detected_components:
            row.component_traceable = "true_component_name_no_rs"
        elif rs_key:
            row.component_traceable = "false_no_component_match"
            row.rejection_reason = row.rejection_reason or "rs_sin_component_map"
        else:
            row.component_traceable = "false_no_registro_sanitario"
            row.rejection_reason = row.rejection_reason or "sin_rs_y_sin_component_match"

        return row

    def detect_components(self, row: ProductRow) -> list[tuple[str, str]]:
        haystack = normalize_name(
            " ".join(
                [
                    row.commercial_name,
                    row.formal_name,
                    row.brand,
                    row.component_text,
                ]
            )
        )
        if not haystack:
            return []

        found: dict[str, str] = {}
        haystack_tokens = name_tokens(haystack)
        candidate_indexes: set[int] = set()
        for token in haystack_tokens:
            candidate_indexes.update(self.component_token_index.get(token, set()))

        for idx in candidate_indexes:
            component_id, alias_key, display_name = self.component_aliases[idx]
            alias_tokens = name_tokens(alias_key)
            if not alias_tokens:
                continue
            if contains_alias_phrase(haystack, alias_key) or alias_tokens.issubset(haystack_tokens):
                found.setdefault(component_id, display_name)
        return sorted(found.items(), key=lambda item: item[1].lower())

    def infer_rs(self, row: ProductRow) -> str:
        query = normalize_name(" ".join([row.commercial_name, row.brand, row.formal_name]))
        if not query:
            return ""

        tokens = name_tokens(query)
        candidate_indexes: set[int] = set()
        for token in tokens:
            candidate_indexes.update(self.name_token_index.get(token, set()))

        if not candidate_indexes:
            return ""

        best_rs = ""
        best_score = 0.0
        for idx in candidate_indexes:
            rs_key, digemid_name = self.names[idx]
            if not digemid_name:
                continue
            score = score_name_match(query, tokens, digemid_name)
            if score > best_score:
                best_rs = rs_key
                best_score = score

        return self.digemid_by_rs.get(best_rs, {}).get("item", "") if best_score >= NAME_MATCH_THRESHOLD else ""


class RobotsDisallowed(Exception):
    """robots.txt del host prohíbe la URL para nuestro User-Agent."""

    def __init__(self, url: str):
        super().__init__(f"robots_disallow url={url}")
        self.url = url


def retry_after_seconds(response: httpx.Response | None) -> float | None:
    """Interpreta `Retry-After` (segundos o fecha HTTP). None si no viene o no se entiende."""
    if response is None:
        return None
    raw = clean_text(response.headers.get("retry-after"))
    if not raw:
        return None
    if raw.isdigit():
        return float(raw)
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


class PoliteHttp:
    """Capa HTTP compartida por todos los scrapers.

    - Respeta robots.txt por host (cacheado) para nuestro User-Agent.
    - Reintenta con backoff exponencial + jitter ante 429, 5xx y errores de red.
    - Respeta `Retry-After` cuando el servidor lo envía.
    - Pausa `delay` segundos tras cada request real.
    """

    def __init__(
        self,
        client: httpx.Client,
        *,
        delay: float,
        user_agent: str = USER_AGENT,
        ignore_robots: bool = False,
        max_retries: int = MAX_RETRIES,
        base_backoff: float = RETRY_BASE_SECONDS,
    ):
        self.client = client
        self.delay = max(0.0, float(delay))
        self.user_agent = user_agent
        self.ignore_robots = ignore_robots
        self.max_retries = max(1, int(max_retries))
        self.base_backoff = max(0.0, float(base_backoff))
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}
        self.robots_skipped: list[str] = []
        self.retries = 0

    # robots.txt -----------------------------------------------------------
    def _robots_for(self, url: str) -> robotparser.RobotFileParser | None:
        parsed = urlparse(url)
        host = f"{parsed.scheme}://{parsed.netloc}"
        if host in self._robots:
            return self._robots[host]
        parser = robotparser.RobotFileParser()
        parser.set_url(f"{host}/robots.txt")
        try:
            response = self.client.get(f"{host}/robots.txt", timeout=REQUEST_TIMEOUT)
            status = response.status_code
            if status == 200:
                parser.parse(response.text.splitlines())
            elif status in (401, 403):
                parser.disallow_all = True
            elif 400 <= status < 500:
                parser.allow_all = True
            else:
                # 5xx: igual que urllib, no asumimos permiso hasta poder leer robots.txt.
                parser.disallow_all = True
                print(f"warning robots_txt_unavailable host={host} status={status}", flush=True)
        except Exception as exc:
            # Sin robots.txt alcanzable por red: no bloqueamos la corrida, pero lo dejamos registrado.
            parser.allow_all = True
            print(f"warning robots_txt_fetch_failed host={host} error={exc}", flush=True)
        parser.modified()
        self._robots[host] = parser
        return parser

    def allowed(self, url: str) -> bool:
        if self.ignore_robots:
            return True
        parser = self._robots_for(url)
        if parser is None:
            return True
        return parser.can_fetch(self.user_agent, url)

    # requests -------------------------------------------------------------
    def backoff_seconds(self, attempt: int, response: httpx.Response | None) -> float:
        retry_after = retry_after_seconds(response)
        if retry_after is not None:
            return min(retry_after, RETRY_MAX_SLEEP_SECONDS)
        wait = self.base_backoff * (2 ** attempt) + random.uniform(0, self.base_backoff)
        return min(wait, RETRY_MAX_SLEEP_SECONDS)

    def request(self, url: str, method: str = "GET", **kwargs: Any) -> httpx.Response:
        if not self.allowed(url):
            self.robots_skipped.append(url)
            print(f"warning robots_disallow url={url}", flush=True)
            raise RobotsDisallowed(url)

        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        response: httpx.Response | None = None
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            response = None
            try:
                response = self.client.request(method, url, **kwargs)
            except httpx.HTTPError as exc:
                last_error = exc
            finally:
                if self.delay:
                    time.sleep(self.delay)
            if response is not None and response.status_code not in RETRY_STATUS_CODES:
                return response
            if attempt + 1 >= self.max_retries:
                break
            self.retries += 1
            wait = self.backoff_seconds(attempt, response)
            reason = f"status={response.status_code}" if response is not None else f"error={last_error}"
            print(f"warning http_retry attempt={attempt + 1} wait={wait:.1f}s {reason} url={url}", flush=True)
            time.sleep(wait)

        if response is not None:
            return response
        assert last_error is not None
        raise last_error

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request(url, "GET", **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request(url, "POST", **kwargs)


class BaseScraper:
    def __init__(
        self,
        client: httpx.Client,
        limit: int,
        delay: float,
        terms: list[str] | None = None,
        http: PoliteHttp | None = None,
    ):
        self.client = client
        self.limit = limit
        self.delay = delay
        self.terms = terms or DEFAULT_SUPPLEMENT_TERMS
        self.fetch_detail_pages = False
        self.ocr_product_images = False
        self.http = http or PoliteHttp(client, delay=delay)

    def fetch(self) -> list[ProductRow]:
        raise NotImplementedError

    def _request(self, url: str, **kwargs: Any) -> httpx.Response:
        """Único punto de salida HTTP: robots.txt, reintentos, Retry-After y pausa."""
        return self.http.request(url, **kwargs)

    def get_json(self, url: str, **kwargs: Any) -> Any:
        response = self._request(url, **kwargs)
        response.raise_for_status()
        return response.json()

    def get_text(self, url: str, **kwargs: Any) -> str:
        response = self._request(url, **kwargs)
        response.raise_for_status()
        return response.text

    def enrich_row_from_text_and_images(
        self,
        row: ProductRow,
        *,
        text: str = "",
        image_urls: list[str] | None = None,
        detail_source: str = "detail",
    ) -> ProductRow:
        if image_urls:
            self.attach_product_image(row, image_urls, detail_source)
        if text:
            row.component_text = append_text(row.component_text, text)
            if not row.registro_sanitario:
                registro = extract_registro(text)
                if registro:
                    row.registro_sanitario = registro
                    row.registro_sanitario_source = detail_source
        if self.ocr_product_images and not row.registro_sanitario and image_urls:
            registro = first_registro_from_images(self.client, image_urls, http=self.http)
            if registro:
                row.registro_sanitario = registro
                row.registro_sanitario_source = "image_ocr"
        return row

    def attach_product_image(
        self,
        row: ProductRow,
        image_urls: list[str],
        source: str = "card",
    ) -> ProductRow:
        if row.image_url:
            return row
        image_url = first_image_url(image_urls)
        if image_url:
            row.image_url = image_url
            row.image_source = source
        return row


def download_product_images(
    rows: list[ProductRow],
    image_dir: Path,
    client: httpx.Client,
    http: PoliteHttp | None = None,
) -> dict[str, int]:
    """Descarga opt-in (`--download-product-images`) de la imagen principal para revisión interna.

    Las imágenes no se redistribuyen ni se sirven desde la API; ver docs/supplement_scraping.md.
    """
    if not image_dir.is_absolute():
        image_dir = ROOT_DIR / image_dir
    image_dir.mkdir(parents=True, exist_ok=True)
    stats = {"attempted": 0, "downloaded": 0, "failed": 0, "robots_disallow": 0}
    seen_urls: dict[str, str] = {}
    http = http or PoliteHttp(client, delay=0.0)

    for row in rows:
        if not row.image_url:
            continue
        stats["attempted"] += 1
        if row.image_url in seen_urls:
            row.image_local_path = seen_urls[row.image_url]
            row.image_downloaded_at = now_iso()
            stats["downloaded"] += 1
            continue
        try:
            response = http.request(
                row.image_url,
                headers={
                    "Accept": "image/avif,image/webp,image/png,image/jpeg,*/*;q=0.8",
                    "Referer": row.url or row.image_url,
                },
            )
            content_type = response.headers.get("content-type", "")
            if response.status_code != 200 or not response.content or len(response.content) > OCR_IMAGE_BYTE_LIMIT:
                stats["failed"] += 1
                continue
            path = urlparse(row.image_url).path.lower()
            has_image_extension = any(path.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp"))
            if not content_type.startswith("image/") and not has_image_extension:
                stats["failed"] += 1
                continue
            digest = hashlib.sha256(row.image_url.encode("utf-8")).hexdigest()[:18]
            ext = image_extension(row.image_url, content_type)
            filename = f"{slugify_filename(row.pharmacy)}_{slugify_filename(row.sku or row.commercial_name)}_{digest}{ext}"
            target = image_dir / filename
            target.write_bytes(response.content)
            local_path = str(target.relative_to(ROOT_DIR))
            seen_urls[row.image_url] = local_path
            row.image_local_path = local_path
            row.image_downloaded_at = now_iso()
            stats["downloaded"] += 1
        except RobotsDisallowed:
            stats["robots_disallow"] += 1
        except Exception:
            stats["failed"] += 1

    return stats


def slugify_filename(value: str) -> str:
    text = clean_text(value).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:60] or "product"


class InretailAlgoliaScraper(BaseScraper):
    """Inkafarma/Mifarma (InRetail) vía el índice Algolia que usa su frontend.

    Las credenciales NO van en el código: se leen de `INKAFARMA_ALGOLIA_APP_ID` y
    `INKAFARMA_ALGOLIA_API_KEY` (ver .env.example). Son credenciales públicas del
    frontend de un tercero; antes de usarlas deben revisarse sus términos de uso.
    Sin ellas, el scraper se salta con un log claro y no tumba la corrida.
    """

    index_name = "products"
    product_api = "https://5doa19p9r7.execute-api.us-east-1.amazonaws.com/MMPROD/product/"

    def __init__(
        self,
        client: httpx.Client,
        limit: int,
        delay: float,
        pharmacy: str,
        base_url: str,
        terms: list[str] | None = None,
        http: PoliteHttp | None = None,
        app_id: str | None = None,
        api_key: str | None = None,
    ):
        super().__init__(client, limit, delay, terms, http=http)
        self.pharmacy = pharmacy
        self.base_url = base_url.rstrip("/")
        self.app_id = clean_text(app_id if app_id is not None else os.getenv(ALGOLIA_APP_ID_ENV, ""))
        self.api_key = clean_text(api_key if api_key is not None else os.getenv(ALGOLIA_API_KEY_ENV, ""))

    @property
    def configured(self) -> bool:
        return bool(self.app_id and self.api_key)

    def fetch(self) -> list[ProductRow]:
        rows: list[ProductRow] = []
        seen = set()
        if not self.configured:
            print(
                f"warning scraper_skipped={self.pharmacy} reason=missing_algolia_credentials "
                f"env={ALGOLIA_APP_ID_ENV},{ALGOLIA_API_KEY_ENV}",
                flush=True,
            )
            return rows
        for term in self.terms:
            page = 0
            while len(rows) < self.limit:
                payload = {
                    "query": term,
                    "hitsPerPage": 100,
                    "page": page,
                    "attributesToRetrieve": ["*"],
                }
                response = self._request(
                    f"https://{self.app_id}-dsn.algolia.net/1/indexes/{self.index_name}/query",
                    method="POST",
                    headers={
                        "X-Algolia-API-Key": self.api_key,
                        "X-Algolia-Application-Id": self.app_id,
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                hits = data.get("hits") or []
                if not hits:
                    break
                for hit in hits:
                    row = self._row_from_hit(hit)
                    if not row or not is_supplement(row):
                        continue
                    key = (row.pharmacy, row.sku or row.url)
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(row)
                    if len(rows) % 100 == 0:
                        print(f"{self.pharmacy}: rows={len(rows)}", flush=True)
                    if len(rows) >= self.limit:
                        break
                page += 1
                if page >= int(data.get("nbPages") or 0):
                    break
            if len(rows) >= self.limit:
                break
        return rows

    def _row_from_hit(self, hit: dict[str, Any]) -> ProductRow | None:
        sku = clean_text(hit.get("objectID"))
        if self.pharmacy.lower().startswith("mifarma"):
            sku = clean_text(hit.get("skuMifarma")) or sku
        if not sku:
            return None

        name = clean_text(hit.get("name"))
        slug = clean_text(hit.get("uri"))
        price = parse_price(
            hit.get("priceWithCard")
            or hit.get("pricePromo")
            or hit.get("priceList")
        )
        stock = ""
        availability = "unavailable" if hit.get("publishWithOutStock") is True else "available"
        texts = [
            hit.get("activePrinciples"),
            hit.get("ingredients"),
            hit.get("composition"),
            hit.get("longDescription"),
            " ".join(hit.get("category") or []),
            " ".join(hit.get("subCategory") or []),
        ]
        component_text = clean_text(" ".join(str(text or "") for text in texts))
        registro = extract_registro(component_text)
        row = ProductRow(
            pharmacy=self.pharmacy,
            commercial_name=name,
            formal_name=name,
            registro_sanitario=registro,
            price=price,
            currency="PEN",
            availability=availability,
            url=f"{self.base_url}/producto/{slug}/{sku}" if slug else self.base_url,
            sku=sku,
            brand=clean_text(hit.get("brand") or hit.get("lab")),
            source_strategy="algolia_public_search",
            scraped_at=now_iso(),
            stock=str(stock or ""),
            component_text=component_text,
            registro_sanitario_source="card" if registro else "",
        )
        self.attach_product_image(row, extract_image_urls(hit, self.base_url), "card")
        if self.fetch_detail_pages:
            detail = self._product_detail(sku)
            detail_text = flattened_json_text(detail)
            detail_images = extract_image_urls(detail, self.base_url)
            self.enrich_row_from_text_and_images(
                row,
                text=detail_text,
                image_urls=[*detail_images, *extract_image_urls(hit, self.base_url)],
                detail_source="detail",
            )
        elif self.ocr_product_images:
            self.enrich_row_from_text_and_images(row, image_urls=extract_image_urls(hit, self.base_url))
        return row

    def _product_detail(self, sku: str) -> dict[str, Any]:
        if not sku:
            return {}
        try:
            response = self._request(self.product_api + quote_plus(sku))
            if response.status_code != 200 or not response.content:
                return {}
            data = response.json()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}


class VtexScraper(BaseScraper):
    def __init__(
        self,
        client: httpx.Client,
        limit: int,
        delay: float,
        pharmacy: str,
        base_url: str,
        terms: list[str] | None = None,
        http: PoliteHttp | None = None,
    ):
        super().__init__(client, limit, delay, terms, http=http)
        self.pharmacy = pharmacy
        self.base_url = base_url.rstrip("/")

    def fetch(self) -> list[ProductRow]:
        rows: list[ProductRow] = []
        seen = set()
        for term in self.terms:
            start = 0
            while len(rows) < self.limit:
                end = start + 49
                url = f"{self.base_url}/api/catalog_system/pub/products/search/{quote_plus(term)}?_from={start}&_to={end}"
                try:
                    products = self.get_json(url)
                except Exception:
                    break
                if not isinstance(products, list) or not products:
                    break
                for product in products:
                    row = self._row_from_product(product)
                    if not row or not is_supplement(row):
                        continue
                    key = (row.pharmacy, row.sku or row.url)
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(row)
                    if len(rows) % 100 == 0:
                        print(f"{self.pharmacy}: rows={len(rows)}", flush=True)
                    if len(rows) >= self.limit:
                        break
                start += 50
                if len(products) < 50:
                    break
            if len(rows) >= self.limit:
                break
        return rows

    def _row_from_product(self, product: dict[str, Any]) -> ProductRow | None:
        items = product.get("items") or []
        item = items[0] if items else {}
        sellers = item.get("sellers") or []
        offer = ((sellers[0] if sellers else {}).get("commertialOffer") or {})
        price = parse_price(offer.get("Price") or offer.get("ListPrice"))
        stock = offer.get("AvailableQuantity", "")
        availability = "available" if parse_int(stock) > 0 else "unavailable"
        specs = []
        for key, value in product.items():
            if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
                specs.extend(value)
        spec_text = clean_text(" ".join(specs + [product.get("description", "")]))
        registro = clean_text((product.get("Registro Sanitario") or [""])[0])
        registro = registro or extract_registro(spec_text)
        sku = clean_text(item.get("itemId") or product.get("productId"))
        name = clean_text(product.get("productName"))
        row = ProductRow(
            pharmacy=self.pharmacy,
            commercial_name=name,
            formal_name=clean_text(product.get("productTitle") or name),
            registro_sanitario=registro,
            price=price,
            currency="PEN",
            availability=availability,
            url=clean_text(product.get("link")) or self.base_url,
            sku=sku,
            brand=clean_text(product.get("brand")),
            source_strategy="vtex_catalog_search",
            scraped_at=now_iso(),
            stock=str(stock or ""),
            component_text=spec_text,
            registro_sanitario_source="card" if registro else "",
        )
        self.attach_product_image(row, extract_image_urls(product, self.base_url), "card")
        if self.fetch_detail_pages and row.url:
            try:
                detail_text = clean_text(self.get_text(row.url))
            except Exception:
                detail_text = ""
            self.enrich_row_from_text_and_images(
                row,
                text=detail_text,
                image_urls=[*extract_image_urls(product, self.base_url), *extract_image_urls(detail_text, self.base_url)],
                detail_source="detail",
            )
        elif self.ocr_product_images:
            self.enrich_row_from_text_and_images(row, image_urls=extract_image_urls(product, self.base_url))
        return row


class WooStoreScraper(BaseScraper):
    def __init__(
        self,
        client: httpx.Client,
        limit: int,
        delay: float,
        pharmacy: str,
        base_url: str,
        terms: list[str] | None = None,
        http: PoliteHttp | None = None,
    ):
        super().__init__(client, limit, delay, terms, http=http)
        self.pharmacy = pharmacy
        self.base_url = base_url.rstrip("/")

    def fetch(self) -> list[ProductRow]:
        rows: list[ProductRow] = []
        seen = set()
        for term in self.terms:
            page = 1
            while len(rows) < self.limit:
                url = (
                    f"{self.base_url}/wp-json/wc/store/v1/products"
                    f"?search={quote_plus(term)}&per_page=100&page={page}"
                )
                try:
                    products = self.get_json(url)
                except Exception:
                    break
                if not isinstance(products, list) or not products:
                    break
                for product in products:
                    row = self._row_from_product(product)
                    if not row or not is_supplement(row):
                        continue
                    key = (row.pharmacy, row.sku or row.url)
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(row)
                    if len(rows) % 100 == 0:
                        print(f"{self.pharmacy}: rows={len(rows)}", flush=True)
                    if len(rows) >= self.limit:
                        break
                page += 1
            if len(rows) >= self.limit:
                break
        return rows

    def _row_from_product(self, product: dict[str, Any]) -> ProductRow | None:
        prices = product.get("prices") or {}
        minor_unit = int(prices.get("currency_minor_unit") or 2)
        text = clean_text(
            " ".join(
                [
                    product.get("name", ""),
                    product.get("short_description", ""),
                    product.get("description", ""),
                ]
            )
        )
        registro = extract_registro(text)
        row = ProductRow(
            pharmacy=self.pharmacy,
            commercial_name=clean_text(product.get("name")),
            formal_name=clean_text(product.get("name")),
            registro_sanitario=registro,
            price=price_from_minor_units(prices.get("price"), minor_unit),
            currency=clean_text(prices.get("currency_code") or "PEN"),
            availability="available" if product.get("is_in_stock", True) else "unavailable",
            url=clean_text(product.get("permalink")),
            sku=clean_text(product.get("sku") or product.get("id")),
            brand="",
            source_strategy="woocommerce_store_api",
            scraped_at=now_iso(),
            component_text=text,
            registro_sanitario_source="card" if registro else "",
        )
        self.attach_product_image(row, extract_image_urls(product, self.base_url), "card")
        if self.ocr_product_images:
            self.enrich_row_from_text_and_images(row, image_urls=extract_image_urls(product, self.base_url))
        return row


class HtmlSearchScraper(BaseScraper):
    def __init__(
        self,
        client: httpx.Client,
        limit: int,
        delay: float,
        pharmacy: str,
        base_url: str,
        terms: list[str] | None = None,
        http: PoliteHttp | None = None,
    ):
        super().__init__(client, limit, delay, terms, http=http)
        self.pharmacy = pharmacy
        self.base_url = base_url.rstrip("/")

    def fetch(self) -> list[ProductRow]:
        rows: list[ProductRow] = []
        seen_urls = set()
        for term in self.terms:
            if len(rows) >= self.limit:
                break
            search_urls = [
                f"{self.base_url}/search?q={quote_plus(term)}&start=0&sz=100",
                f"{self.base_url}/catalogsearch/result/?q={quote_plus(term)}",
                f"{self.base_url}/?s={quote_plus(term)}&post_type=product",
            ]
            for search_url in search_urls:
                try:
                    html_text = self.get_text(search_url)
                except Exception:
                    continue
                for link in extract_product_links(html_text, self.base_url):
                    if link in seen_urls:
                        continue
                    seen_urls.add(link)
                    row = self._row_from_page(link)
                    if row and is_supplement(row):
                        rows.append(row)
                        if len(rows) % 100 == 0:
                            print(f"{self.pharmacy}: rows={len(rows)}", flush=True)
                    if len(rows) >= self.limit:
                        break
                if len(rows) >= self.limit:
                    break
        return rows

    def _row_from_page(self, url: str) -> ProductRow | None:
        try:
            text = self.get_text(url)
        except RobotsDisallowed:
            # Ya quedó registrado en http.robots_skipped; no se crea fila para esa URL.
            return None
        except Exception:
            return None
        title = first_match(text, r"<h1[^>]*>(.*?)</h1>") or first_match(text, r"<title[^>]*>(.*?)</title>")
        price = first_match(text, r"(?:S/|S\/|PEN)\s*([0-9]+(?:[.,][0-9]+)?)")
        sku = first_match(text, r"(?:SKU|sku|data-pid)[^A-Za-z0-9]{1,20}([A-Za-z0-9._-]{3,})")
        page_text = clean_text(text)
        registro = extract_registro(page_text)
        row = ProductRow(
            pharmacy=self.pharmacy,
            commercial_name=clean_text(title),
            formal_name=clean_text(title),
            registro_sanitario=registro,
            price=parse_price(price),
            currency="PEN",
            availability="unavailable" if "agotado" in page_text.lower() else "available",
            url=url,
            sku=clean_text(sku),
            brand="",
            source_strategy="html_search_and_product_page",
            scraped_at=now_iso(),
            component_text=page_text[:2000],
            registro_sanitario_source="detail" if registro else "",
        )
        self.attach_product_image(row, extract_image_urls(text, self.base_url), "detail")
        if self.ocr_product_images:
            self.enrich_row_from_text_and_images(row, image_urls=extract_image_urls(text, self.base_url))
        return row


class BoticasPeruScraper(BaseScraper):
    base_url = "https://www.boticasperu.pe"

    def fetch(self) -> list[ProductRow]:
        rows: list[ProductRow] = []
        seen = set()
        for term in self.terms:
            start = 0
            while len(rows) < self.limit:
                url = (
                    f"{self.base_url}/on/demandware.store/Sites-BoticasPeru-Site/es_PE/"
                    f"Search-UpdateGrid?q={quote_plus(term)}&start={start}&sz=24"
                )
                try:
                    text = self.get_text(url)
                except Exception:
                    break

                page_rows = self._rows_from_grid(text)
                if not page_rows:
                    break

                for row in page_rows:
                    if not is_supplement(row):
                        continue
                    key = (row.pharmacy, row.sku or row.url)
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(row)
                    if len(rows) % 100 == 0:
                        print(f"Boticas Peru: rows={len(rows)}", flush=True)
                    if len(rows) >= self.limit:
                        break

                if len(page_rows) < 24:
                    break
                start += 24

            if len(rows) >= self.limit:
                break

        return rows

    def _rows_from_grid(self, text: str) -> list[ProductRow]:
        rows: list[ProductRow] = []
        product_blocks = re.split(r'(?=<[^>]+data-pid=")', text or "")
        for block in product_blocks:
            sku = first_match(block, r'data-pid=["\']([^"\']+)["\']')
            href = first_match(block, r'href=["\']([^"\']+/(?:[^/"\']+/)?[^/"\']+\.html)["\']')
            price = first_match(block, r"S/\s*([0-9]+[.,][0-9]{2})")
            if not sku or not href:
                continue
            url = urljoin(self.base_url, href)
            name = name_from_url(url)
            page_text = clean_text(block)
            row = ProductRow(
                    pharmacy="Boticas Peru",
                    commercial_name=name,
                    formal_name=name,
                    registro_sanitario=extract_registro(page_text),
                    price=parse_price(price),
                    currency="PEN",
                    availability="unavailable" if "agotado" in page_text.lower() else "available",
                    url=url,
                    sku=sku,
                    brand="",
                    source_strategy="sfcc_search_update_grid",
                    scraped_at=now_iso(),
                    component_text=page_text[:1500],
                    registro_sanitario_source="card" if extract_registro(page_text) else "",
                )
            self.attach_product_image(row, extract_image_urls(block, self.base_url), "card")
            if self.fetch_detail_pages:
                try:
                    detail_text = clean_text(self.get_text(url))
                except Exception:
                    detail_text = ""
                self.enrich_row_from_text_and_images(
                    row,
                    text=detail_text,
                    image_urls=extract_image_urls(detail_text, self.base_url),
                    detail_source="detail",
                )
            elif self.ocr_product_images:
                self.enrich_row_from_text_and_images(row, image_urls=extract_image_urls(block, self.base_url))
            rows.append(row)
        return rows


def name_from_url(url: str) -> str:
    slug = url.rstrip("/").split("/")[-2] if "/" in url.rstrip("/") else url
    # Decodificar percent-encoding antes de construir el nombre (%2B -> +, %26 -> &, %2C -> ,).
    slug = unquote(slug)
    slug = re.sub(r"[_-]+", " ", slug)
    slug = re.sub(r"\s+,", ",", slug)
    slug = re.sub(r"\s+", " ", slug)
    return slug.strip().title()


def extract_product_links(text: str, base_url: str) -> list[str]:
    links = []
    for href in re.findall(r'href=["\']([^"\']+)["\']', text or ""):
        if not any(marker in href.lower() for marker in ["/producto/", ".html", "/p"]):
            continue
        full = urljoin(base_url + "/", href)
        if full not in links:
            links.append(full)
    return links


def first_match(text: str, pattern: str) -> str:
    match = re.search(pattern, text or "", re.IGNORECASE | re.DOTALL)
    return clean_text(match.group(1)) if match else ""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_scrapers(
    client: httpx.Client,
    selected: set[str],
    limit: int,
    delay: float,
    terms: list[str] | None = None,
    http: PoliteHttp | None = None,
) -> list[BaseScraper]:
    http = http or PoliteHttp(client, delay=delay)
    definitions: dict[str, BaseScraper] = {
        "inkafarma": InretailAlgoliaScraper(client, limit, delay, "Inkafarma", "https://inkafarma.pe", terms, http=http),
        "mifarma": InretailAlgoliaScraper(client, limit, delay, "Mifarma", "https://www.mifarma.com.pe", terms, http=http),
        "boticasperu": BoticasPeruScraper(client, limit, delay, terms, http=http),
        "farmaciauniversal": VtexScraper(client, limit, delay, "Farmacia Universal", "https://www.farmaciauniversal.com", terms, http=http),
        "hogarysalud": WooStoreScraper(client, limit, delay, "Hogar y Salud", "https://www.hogarysalud.com.pe", terms, http=http),
        "boticasysalud": HtmlSearchScraper(client, limit, delay, "Boticas y Salud", "https://www.boticasysalud.com", terms, http=http),
    }
    if not selected:
        return list(definitions.values())
    return [scraper for key, scraper in definitions.items() if key in selected]


def dedupe(rows: list[ProductRow]) -> list[ProductRow]:
    result = []
    seen = set()
    for row in rows:
        key = (
            row.pharmacy.lower(),
            row.sku or normalize_name(row.commercial_name),
            normalize_rs(row.registro_sanitario),
            row.url,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def write_rows(path: Path, rows: list[ProductRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: asdict(row).get(field, "") for field in CSV_FIELDS})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Recolecta suplementos de farmacias peruanas y genera supplements_exhaustive_clean.csv."
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--rejects-out", type=Path, default=DEFAULT_REJECTS)
    parser.add_argument("--digemid", type=Path, default=DEFAULT_DIGEMID)
    parser.add_argument("--components", type=Path, default=DEFAULT_COMPONENTS)
    parser.add_argument("--component-master", type=Path, default=DEFAULT_COMPONENT_MASTER)
    parser.add_argument("--limit-per-pharmacy", type=int, default=1000)
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument(
        "--pharmacy",
        action="append",
        choices=["inkafarma", "mifarma", "boticasperu", "farmaciauniversal", "hogarysalud", "boticasysalud"],
        help="Puede repetirse. Si se omite, procesa todas.",
    )
    parser.add_argument(
        "--term",
        action="append",
        help="Término de búsqueda dirigido. Puede repetirse. Si se omite, usa la lista general de suplementos.",
    )
    parser.add_argument(
        "--allow-unverified",
        action="store_true",
        help="Incluye productos sin RS o sin componente rastreable. Por defecto se descartan.",
    )
    parser.add_argument(
        "--infer-registro",
        action="store_true",
        help="Intenta inferir registro sanitario por similitud contra digemid_limpio.csv cuando la web no lo publica.",
    )
    parser.add_argument(
        "--fetch-detail-pages",
        action="store_true",
        help="Consulta detalle de producto cuando la fuente lo permite para recuperar RS, composición o metadatos.",
    )
    parser.add_argument(
        "--ocr-product-images",
        action="store_true",
        help="Usa OCR sobre imágenes de producto como fallback para recuperar registro sanitario visible en etiqueta.",
    )
    parser.add_argument(
        "--download-product-images",
        action="store_true",
        default=False,
        help=(
            "Opt-in explícito: descarga la imagen principal detectada para revisión interna. "
            "Por defecto desactivado; las imágenes no se redistribuyen."
        ),
    )
    parser.add_argument(
        "--ignore-robots",
        action="store_true",
        default=False,
        help="SOLO para pruebas locales: no consulta robots.txt. Por defecto se respeta.",
    )
    parser.add_argument(
        "--image-dir",
        type=Path,
        default=DEFAULT_IMAGE_DIR,
        help="Directorio local para imágenes descargadas cuando se usa --download-product-images.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    selected = set(args.pharmacy or [])
    terms = [clean_text(term) for term in (args.term or []) if clean_text(term)]
    matcher = RegistryMatcher(args.digemid, args.components, args.component_master)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    }
    if args.ignore_robots:
        print("warning ignore_robots=1 (solo para pruebas; robots.txt no se consulta)", flush=True)

    all_rows: list[ProductRow] = []
    with httpx.Client(headers=headers, follow_redirects=True) as client:
        http = PoliteHttp(client, delay=args.delay, ignore_robots=bool(args.ignore_robots))
        scrapers = build_scrapers(client, selected, args.limit_per_pharmacy, args.delay, terms or None, http=http)
        for scraper in scrapers:
            scraper.fetch_detail_pages = bool(args.fetch_detail_pages)
            scraper.ocr_product_images = bool(args.ocr_product_images)
            print(f"scraping={scraper.__class__.__name__}", flush=True)
            try:
                rows = scraper.fetch()
            except Exception as exc:
                print(f"warning scraper_failed={scraper.__class__.__name__} error={exc}", flush=True)
                rows = []
            print(f"rows_found={len(rows)}", flush=True)
            all_rows.extend(rows)

        accepted: list[ProductRow] = []
        rejected: list[ProductRow] = []
        for row in dedupe(all_rows):
            matcher.enrich(row, infer_missing_rs=args.infer_registro)
            if args.allow_unverified or row.component_traceable.startswith("true"):
                accepted.append(row)
            else:
                rejected.append(row)

        image_stats = {"attempted": 0, "downloaded": 0, "failed": 0, "robots_disallow": 0}
        if args.download_product_images:
            image_stats = download_product_images([*accepted, *rejected], args.image_dir, client, http=http)

    write_rows(args.out, accepted)
    write_rows(args.rejects_out, rejected)

    by_pharmacy: dict[str, int] = {}
    for row in accepted:
        by_pharmacy[row.pharmacy] = by_pharmacy.get(row.pharmacy, 0) + 1

    print(json.dumps({
        "accepted": len(accepted),
        "rejected": len(rejected),
        "by_pharmacy": by_pharmacy,
        "images": {
            "with_url": sum(1 for row in [*accepted, *rejected] if row.image_url),
            **image_stats,
        },
        "http": {
            "retries": http.retries,
            "robots_disallow_skipped": len(http.robots_skipped),
            "ignore_robots": bool(args.ignore_robots),
        },
        "out": str(args.out),
        "rejects_out": str(args.rejects_out),
    }, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
