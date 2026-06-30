from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import BASE_DIR
from app.db.models import AdminAction, CommercialProduct, CommercialProductComponent, Component, Pharmacy, utcnow
from app.domains.admin.esquemas import CatalogCandidateOut


RELATIONS_PATH = BASE_DIR / "data/reports/scraping/rotation_candidate_priority_relations.csv"
FALLBACK_RELATIONS_PATH = BASE_DIR / "data/reports/scraping/rotation_candidate_relations.csv"
ACTIONS_PATH = BASE_DIR / "data/reports/scraping/catalog_candidate_actions.json"
PROMOTIONS_PATH = BASE_DIR / "data/reports/scraping/catalog_candidate_promotions.csv"

MANUAL_STATUSES = {
    "candidate_needs_rs",
    "candidate_name_match",
    "approved_for_review",
    "rejected_no_rs",
    "rejected_non_oral",
    "manual_rejected",
    "promoted",
}

PROMOTION_FIELDS = [
    "candidate_id",
    "component_id",
    "component_name",
    "pharmacy",
    "commercial_name",
    "price",
    "availability",
    "registro_sanitario",
    "url",
    "sku",
    "component_traceable",
    "reviewed_by",
    "reviewed_at",
    "reason",
    "product_id",
]


def clean(value: Any) -> str:
    return str(value or "").strip()


def parse_float(value: Any) -> float | None:
    try:
        return float(clean(value))
    except (TypeError, ValueError):
        return None


def slugify(value: str) -> str:
    text = clean(value).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "unknown"


def base_url_from_product_url(url: str) -> str | None:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def split_list(value: str) -> list[str]:
    return [item.strip() for item in clean(value).split(";") if item.strip()]


def candidate_id_for(row: dict[str, Any]) -> str:
    raw = "|".join(
        clean(row.get(key))
        for key in ("component_id", "pharmacy", "sku", "url", "commercial_name")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class CatalogCandidateService:
    def __init__(
        self,
        db: Session | None = None,
        *,
        relations_path: Path = RELATIONS_PATH,
        fallback_relations_path: Path = FALLBACK_RELATIONS_PATH,
        actions_path: Path = ACTIONS_PATH,
        promotions_path: Path = PROMOTIONS_PATH,
    ):
        self.db = db
        self.relations_path = relations_path
        self.fallback_relations_path = fallback_relations_path
        self.actions_path = actions_path
        self.promotions_path = promotions_path

    def list_candidates(
        self,
        *,
        component: str | None = None,
        status_filter: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        actions = self._load_actions()
        rows = [self._candidate_out(row, actions.get(candidate_id_for(row))) for row in self._read_candidate_rows()]
        if component:
            needle = component.strip().lower()
            rows = [
                row
                for row in rows
                if needle in row.component_id.lower() or needle in row.component_name.lower()
            ]
        if status_filter:
            rows = [row for row in rows if row.catalog_status == status_filter]

        status_counts = dict(Counter(row.catalog_status for row in rows))
        return {
            "candidates": rows[offset : offset + limit],
            "total": len(rows),
            "status_counts": status_counts,
            "recommended_actions": self._recommended_actions(rows, status_counts),
        }

    def update_candidate_status(
        self,
        candidate_id: str,
        *,
        next_status: str,
        reason: str,
        admin_user_id: UUID | str | None,
    ) -> CatalogCandidateOut:
        if next_status not in MANUAL_STATUSES - {"promoted"}:
            raise ValueError("Estado de candidato no soportado.")
        row = self._find_row(candidate_id)
        actions = self._load_actions()
        before = actions.get(candidate_id, {})
        actions[candidate_id] = {
            "status": next_status,
            "reason": reason,
            "reviewed_by": str(admin_user_id) if admin_user_id else None,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_actions(actions)
        self._audit(
            "catalog_candidate_status_updated",
            candidate_id,
            before,
            actions[candidate_id],
            admin_user_id,
        )
        return self._candidate_out(row, actions[candidate_id])

    def promote_candidate(
        self,
        candidate_id: str,
        *,
        reason: str,
        admin_user_id: UUID | str | None,
    ) -> tuple[CatalogCandidateOut, UUID]:
        row = self._find_row(candidate_id)
        candidate = self._candidate_out(row, self._load_actions().get(candidate_id))
        if not candidate.promotable:
            raise ValueError("El candidato no cumple reglas mínimas: requiere RS y componente trazable.")
        if self.db is None:
            raise RuntimeError("Se requiere sesión de base de datos para promover candidatos.")

        pharmacy = self._get_or_create_pharmacy(row)
        component = self._get_or_create_component(row)
        product = self._get_or_create_product(row, pharmacy, candidate_id, reason, admin_user_id)
        self._link_component(product, component, row)

        actions = self._load_actions()
        before = actions.get(candidate_id, {})
        actions[candidate_id] = {
            "status": "promoted",
            "reason": reason,
            "reviewed_by": str(admin_user_id) if admin_user_id else None,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "product_id": str(product.id),
        }
        self._write_actions(actions)
        self._append_promotion(row, candidate_id, reason, admin_user_id, product.id)
        self._audit(
            "catalog_candidate_promoted",
            candidate_id,
            before,
            actions[candidate_id],
            admin_user_id,
        )
        self.db.commit()
        self.db.refresh(product)
        return self._candidate_out(row, actions[candidate_id]), product.id

    def _read_candidate_rows(self) -> list[dict[str, str]]:
        path = self.relations_path if self.relations_path.exists() else self.fallback_relations_path
        if not path.exists():
            return []
        rows: list[dict[str, str]] = []
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                if clean(row.get("commercial_name")):
                    rows.append(row)
        return rows

    def _find_row(self, candidate_id: str) -> dict[str, str]:
        for row in self._read_candidate_rows():
            if candidate_id_for(row) == candidate_id:
                return row
        raise LookupError("Candidato no encontrado.")

    def _candidate_out(self, row: dict[str, str], action: dict[str, Any] | None = None) -> CatalogCandidateOut:
        candidate_id = candidate_id_for(row)
        status = self._derive_status(row, action)
        rs = clean(row.get("registro_sanitario")) or None
        component_traceable = clean(row.get("component_traceable")) or None
        promotable = bool(rs) and component_traceable == "true_rs_component" and status not in {
            "rejected_no_rs",
            "rejected_non_oral",
            "manual_rejected",
        }
        notes = self._confidence_notes(row, status)
        return CatalogCandidateOut(
            candidate_id=candidate_id,
            component_id=clean(row.get("component_id")),
            component_name=clean(row.get("component_name")),
            pharmacy=clean(row.get("pharmacy")),
            commercial_name=clean(row.get("commercial_name")),
            price=parse_float(row.get("price")),
            availability=clean(row.get("availability")) or None,
            registro_sanitario=rs,
            url=clean(row.get("url")) or None,
            sku=clean(row.get("sku")) or None,
            component_traceable=component_traceable,
            component_ids_detected=split_list(row.get("component_ids_detected", "")),
            component_names_detected=split_list(row.get("component_names_detected", "")),
            match_basis=clean(row.get("match_basis")) or None,
            needs_catalog_review=clean(row.get("needs_catalog_review")).lower() in {"yes", "true", "1"},
            catalog_status=status,
            promotable=promotable,
            action_reason=clean((action or {}).get("reason")) or None,
            reviewed_by=clean((action or {}).get("reviewed_by")) or None,
            reviewed_at=clean((action or {}).get("reviewed_at")) or None,
            confidence_notes=notes,
        )

    def _derive_status(self, row: dict[str, str], action: dict[str, Any] | None) -> str:
        manual_status = clean((action or {}).get("status"))
        if manual_status in MANUAL_STATUSES:
            return manual_status
        has_rs = bool(clean(row.get("registro_sanitario")))
        traceability = clean(row.get("component_traceable"))
        if not has_rs:
            return "candidate_needs_rs"
        if traceability == "true_rs_component":
            return "approved_verified"
        if "name" in clean(row.get("match_basis")).lower():
            return "candidate_name_match"
        return "approved_inferred"

    def _confidence_notes(self, row: dict[str, str], status: str) -> list[str]:
        notes: list[str] = []
        if clean(row.get("registro_sanitario")):
            notes.append("Tiene RS informado")
        else:
            notes.append("Falta RS trazable")
        if clean(row.get("component_traceable")) == "true_rs_component":
            notes.append("Componente validado por relación trazable")
        elif "no_rs" in clean(row.get("component_traceable")):
            notes.append("Coincidencia de componente sin RS")
        if status == "candidate_name_match":
            notes.append("Requiere explicación de match contra DIGEMID")
        if clean(row.get("availability")) and clean(row.get("availability")) != "available":
            notes.append("Disponibilidad no ideal")
        return notes

    def _recommended_actions(self, rows: list[CatalogCandidateOut], counts: dict[str, int]) -> list[str]:
        actions: list[str] = []
        needs_rs = counts.get("candidate_needs_rs", 0)
        if needs_rs:
            actions.append(f"Revisar RS en ficha o imagen para {needs_rs} candidatos antes de aprobar.")
        promotable = sum(1 for row in rows if row.promotable)
        if promotable:
            actions.append(f"Promover {promotable} candidatos con RS y componente trazable.")
        rejected = counts.get("rejected_no_rs", 0) + counts.get("rejected_non_oral", 0) + counts.get("manual_rejected", 0)
        if rejected:
            actions.append(f"Excluir {rejected} candidatos ya rechazados de futuras rondas.")
        if not actions:
            actions.append("No hay acciones urgentes para los candidatos filtrados.")
        return actions

    def _get_or_create_pharmacy(self, row: dict[str, str]) -> Pharmacy:
        assert self.db is not None
        name = clean(row.get("pharmacy")) or "unknown"
        slug = slugify(name)
        pharmacy = self.db.scalar(select(Pharmacy).where(Pharmacy.slug == slug))
        if pharmacy is None:
            pharmacy = Pharmacy(
                name=name,
                slug=slug,
                base_url=base_url_from_product_url(clean(row.get("url"))),
                active=True,
            )
            self.db.add(pharmacy)
            self.db.flush()
        elif not pharmacy.base_url:
            pharmacy.base_url = base_url_from_product_url(clean(row.get("url")))
        return pharmacy

    def _get_or_create_component(self, row: dict[str, str]) -> Component:
        assert self.db is not None
        component_id = clean(row.get("component_id"))
        if not component_id:
            raise ValueError("component_id vacío.")
        component = self.db.scalar(select(Component).where(Component.component_id == component_id))
        if component is None:
            component = Component(
                component_id=component_id,
                canonical_name=clean(row.get("component_name")) or component_id,
                metadata_json={"source": "catalog_candidate"},
            )
            self.db.add(component)
            self.db.flush()
        return component

    def _get_or_create_product(
        self,
        row: dict[str, str],
        pharmacy: Pharmacy,
        candidate_id: str,
        reason: str,
        admin_user_id: UUID | str | None,
    ) -> CommercialProduct:
        assert self.db is not None
        sku = clean(row.get("sku")) or clean(row.get("url")) or candidate_id
        product = self.db.scalar(
            select(CommercialProduct).where(
                CommercialProduct.pharmacy_id == pharmacy.id,
                CommercialProduct.sku == sku,
            )
        )
        payload = {
            **row,
            "catalog_candidate_id": candidate_id,
            "catalog_candidate_status": "approved_verified",
            "catalog_status": "approved_verified",
            "approved_by": str(admin_user_id) if admin_user_id else None,
            "approved_reason": reason,
            "commercial_confidence_level": "alta",
            "commercial_confidence_score": 0.9,
            "commercial_confidence_reasons": "Promovido manualmente desde candidato con RS y componente trazable.",
        }
        if product is None:
            product = CommercialProduct(
                pharmacy_id=pharmacy.id,
                sku=sku,
                commercial_name=clean(row.get("commercial_name")),
                formal_name=None,
                brand=None,
                url=clean(row.get("url")),
                registro_sanitario=clean(row.get("registro_sanitario")) or None,
                price=parse_float(row.get("price")),
                currency="PEN",
                availability=clean(row.get("availability")) or "unknown",
                stock=None,
                source_strategy="admin_candidate_promotion",
                component_traceable=clean(row.get("component_traceable")) or "true_rs_component",
                commercial_status="active",
                last_seen_at=utcnow(),
                raw_payload_json=payload,
            )
            self.db.add(product)
            self.db.flush()
            return product

        product.commercial_name = clean(row.get("commercial_name")) or product.commercial_name
        product.url = clean(row.get("url")) or product.url
        product.registro_sanitario = clean(row.get("registro_sanitario")) or product.registro_sanitario
        product.price = parse_float(row.get("price"))
        product.availability = clean(row.get("availability")) or product.availability
        product.source_strategy = "admin_candidate_promotion"
        product.component_traceable = clean(row.get("component_traceable")) or product.component_traceable
        product.commercial_status = "active"
        product.last_seen_at = utcnow()
        product.raw_payload_json = {**(product.raw_payload_json or {}), **payload}
        self.db.flush()
        return product

    def _link_component(self, product: CommercialProduct, component: Component, row: dict[str, str]) -> None:
        assert self.db is not None
        ingredient = clean(row.get("component_name")) or component.canonical_name
        existing = self.db.scalar(
            select(CommercialProductComponent).where(
                CommercialProductComponent.product_id == product.id,
                CommercialProductComponent.component_id == component.id,
                CommercialProductComponent.ingredient == ingredient,
            )
        )
        if existing is not None:
            existing.match_score = 1.0
            existing.match_method = "admin_candidate_review"
            return
        self.db.add(
            CommercialProductComponent(
                product_id=product.id,
                component_id=component.id,
                ingredient=ingredient,
                match_score=1.0,
                match_method="admin_candidate_review",
                source="admin_candidate_promotion",
            )
        )

    def _load_actions(self) -> dict[str, dict[str, Any]]:
        if not self.actions_path.exists():
            return {}
        try:
            data = json.loads(self.actions_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _write_actions(self, actions: dict[str, dict[str, Any]]) -> None:
        self.actions_path.parent.mkdir(parents=True, exist_ok=True)
        self.actions_path.write_text(json.dumps(actions, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _append_promotion(
        self,
        row: dict[str, str],
        candidate_id: str,
        reason: str,
        admin_user_id: UUID | str | None,
        product_id: UUID,
    ) -> None:
        self.promotions_path.parent.mkdir(parents=True, exist_ok=True)
        exists = self.promotions_path.exists()
        with self.promotions_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=PROMOTION_FIELDS)
            if not exists:
                writer.writeheader()
            writer.writerow({
                "candidate_id": candidate_id,
                "component_id": clean(row.get("component_id")),
                "component_name": clean(row.get("component_name")),
                "pharmacy": clean(row.get("pharmacy")),
                "commercial_name": clean(row.get("commercial_name")),
                "price": clean(row.get("price")),
                "availability": clean(row.get("availability")),
                "registro_sanitario": clean(row.get("registro_sanitario")),
                "url": clean(row.get("url")),
                "sku": clean(row.get("sku")),
                "component_traceable": clean(row.get("component_traceable")),
                "reviewed_by": str(admin_user_id) if admin_user_id else "",
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
                "reason": reason,
                "product_id": str(product_id),
            })

    def _audit(
        self,
        action_type: str,
        candidate_id: str,
        before: dict[str, Any],
        after: dict[str, Any],
        admin_user_id: UUID | str | None,
    ) -> None:
        if self.db is None:
            return
        self.db.add(
            AdminAction(
                admin_user_id=admin_user_id,
                action_type=action_type,
                entity_type="catalog_candidate",
                entity_id=candidate_id,
                before_json=before,
                after_json=after,
            )
        )
        self.db.flush()
