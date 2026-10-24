"""Cola de revisión humana de registros sanitarios (RS) inferidos.

Lógica pura (sin BD) para decidir qué productos del catálogo aprobado deben
pasar por revisión humana y con qué contexto. La persistencia vive en
`repositorio_revision_rs.py`; la documentación operativa en docs/catalog_rs_review.md.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections.abc import Iterable
from typing import Any

# Fuentes de `registro_sanitario_source` que significan "RS inferido por nombre
# contra DIGEMID": el RS no se leyó de la página de la farmacia, se dedujo.
INFERRED_RS_SOURCES = frozenset({"digemid_name_match", "digemid_name_inference"})

SAMPLE_REASON_INFERRED = "inferred"
SAMPLE_REASON_RANDOM = "random_sample"
SAMPLE_REASONS = (SAMPLE_REASON_INFERRED, SAMPLE_REASON_RANDOM)

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_NEEDS_INFO = "needs_info"
REVIEW_STATUSES = (STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED, STATUS_NEEDS_INFO)

# Estado que expone un producto que no está (ni necesita estar) en la cola.
RS_REVIEW_NOT_REQUIRED = "not_required"

DEFAULT_SAMPLE_RATIO = 0.05
DEFAULT_SAMPLE_SEED = "suplematch-rs-review-v1"

# Columnas del CSV de la cola, en el orden en que las lee el revisor.
EXPORT_COLUMNS = (
    "id",
    "status",
    "sample_reason",
    "pharmacy",
    "sku",
    "commercial_name",
    "url",
    "registro_sanitario_key",
    "registro_sanitario_source",
    "digemid_producto",
    "digemid_composicion",
    "match_reason",
    "reviewer_note",
    "decided_at",
)
# Celdas que una hoja de calculo interpretaria como formula (inyeccion CSV).
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def clean(value: Any) -> str:
    return str(value or "").strip()


def normalize_rs_key(value: Any) -> str:
    """Misma normalización que `construir_catalogo_aprobado.normalize_rs`: 'DE-1230' -> 'DE1230'."""
    return re.sub(r"[^A-Z0-9]", "", clean(value).upper())


def review_product_key(pharmacy: Any, sku: Any, url: Any = None) -> tuple[str, str]:
    """Identidad del producto en la cola: (farmacia, sku o url), igual que el importador."""
    return (clean(pharmacy), clean(sku) or clean(url))


def is_inferred_source(source: Any) -> bool:
    return clean(source).lower() in INFERRED_RS_SOURCES


def sample_fraction(key: tuple[str, str], seed: str) -> float:
    """Número determinista en [0, 1) derivado de (seed, farmacia, sku).

    Se usa hash en vez de `random.sample` para que la muestra sea estable: añadir
    o quitar productos del catálogo no cambia si un producto ya muestreado sigue
    en la muestra (la cola persiste decisiones por producto).
    """
    digest = hashlib.sha256(f"{seed}|{key[0]}|{key[1]}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


def build_match_reason(row: dict[str, Any]) -> str:
    """Texto libre con el contexto que necesita el revisor para juzgar el match."""
    parts: list[str] = []
    source = clean(row.get("registro_sanitario_source"))
    if source:
        parts.append(f"source={source}")
    explicit = clean(row.get("registro_sanitario_match_reason")) or clean(row.get("match_reason"))
    if explicit:
        parts.append(f"match={explicit}")
    forma = clean(row.get("digemid_forma_farmaceutica"))
    if forma:
        parts.append(f"forma_digemid={forma}")
    brand = clean(row.get("brand"))
    if brand:
        parts.append(f"marca={brand}")
    fabricante = clean(row.get("digemid_fabricante"))
    if fabricante:
        parts.append(f"fabricante_digemid={fabricante}")
    level = clean(row.get("commercial_confidence_level"))
    if level:
        parts.append(f"confianza_comercial={level}")
    reasons = clean(row.get("commercial_confidence_reasons"))
    if reasons:
        parts.append(f"motivos={reasons}")
    return "; ".join(parts)


def _review_item(row: dict[str, Any], key: tuple[str, str], sample_reason: str) -> dict[str, Any]:
    return {
        "pharmacy": key[0],
        "sku": key[1],
        "url": clean(row.get("url")) or None,
        "commercial_name": clean(row.get("commercial_name")) or None,
        "registro_sanitario_key": normalize_rs_key(row.get("registro_sanitario_key") or row.get("registro_sanitario")),
        "digemid_producto": clean(row.get("digemid_producto")) or None,
        "digemid_composicion": clean(row.get("digemid_composicion")) or None,
        "registro_sanitario_source": clean(row.get("registro_sanitario_source")) or None,
        "match_reason": build_match_reason(row) or None,
        "sample_reason": sample_reason,
    }


def select_review_items(
    rows: Iterable[dict[str, Any]],
    sample_ratio: float = DEFAULT_SAMPLE_RATIO,
    seed: str = DEFAULT_SAMPLE_SEED,
) -> list[dict[str, Any]]:
    """Devuelve una entrada de revisión por producto (farmacia+sku) del catálogo.

    - `sample_reason="inferred"`: el 100% de los productos con alguna fila cuyo
      `registro_sanitario_source` sea inferido por nombre (ver INFERRED_RS_SOURCES).
    - `sample_reason="random_sample"`: muestra aleatoria determinista (~`sample_ratio`)
      del resto de productos con RS, como control de calidad del RS leído.

    Productos sin registro sanitario se omiten: no hay RS que revisar. El orden de
    salida es estable (farmacia, sku) para que la carga sea reproducible.
    """
    if not 0.0 <= sample_ratio <= 1.0:
        raise ValueError("sample_ratio debe estar entre 0 y 1")

    first_row: dict[tuple[str, str], dict[str, Any]] = {}
    inferred_keys: set[tuple[str, str]] = set()
    for row in rows:
        key = review_product_key(row.get("pharmacy"), row.get("sku"), row.get("url"))
        if not key[0] or not key[1]:
            continue
        if not normalize_rs_key(row.get("registro_sanitario_key") or row.get("registro_sanitario")):
            continue
        current = first_row.get(key)
        if current is None or (is_inferred_source(row.get("registro_sanitario_source")) and not is_inferred_source(current.get("registro_sanitario_source"))):
            # Preferimos como fila representativa la que explica la inferencia.
            first_row[key] = row
        if is_inferred_source(row.get("registro_sanitario_source")):
            inferred_keys.add(key)

    items: list[dict[str, Any]] = []
    for key in sorted(first_row):
        row = first_row[key]
        if key in inferred_keys:
            items.append(_review_item(row, key, SAMPLE_REASON_INFERRED))
        elif sample_ratio > 0 and sample_fraction(key, seed) < sample_ratio:
            items.append(_review_item(row, key, SAMPLE_REASON_RANDOM))
    return items


def summarize_items(items: Iterable[dict[str, Any]]) -> dict[str, int]:
    summary = {SAMPLE_REASON_INFERRED: 0, SAMPLE_REASON_RANDOM: 0}
    for item in items:
        reason = item.get("sample_reason")
        summary[reason] = summary.get(reason, 0) + 1
    return summary


def is_valid_transition(current_status: str, next_status: str) -> bool:
    """Cualquier estado puede cambiar a cualquier otro (incluido volver a pending)
    siempre que ambos sean conocidos. Se mantiene como función para endurecerla
    después sin tocar rutas."""
    return current_status in REVIEW_STATUSES and next_status in REVIEW_STATUSES


def _csv_cell(value: Any) -> str:
    text = "" if value is None else (value.isoformat() if hasattr(value, "isoformat") else str(value))
    return f"'{text}" if text.startswith(_FORMULA_PREFIXES) else text


def reviews_to_csv(rows: Iterable[Any]) -> str:
    """CSV de la cola (filas ORM o dicts) con BOM UTF-8 para que Excel respete tildes y sin formulas ejecutables."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(EXPORT_COLUMNS)
    for row in rows:
        get = row.get if isinstance(row, dict) else (lambda name, _row=row: getattr(_row, name, None))
        writer.writerow([_csv_cell(get(column)) for column in EXPORT_COLUMNS])
    return "\ufeff" + buffer.getvalue()
