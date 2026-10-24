"""Cola de revisión humana de RS contra Postgres (requiere DATABASE_URL y migraciones)."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select

from app.db.models import CatalogRsReview, CommercialProduct, CommercialProductComponent, Component, Pharmacy
from app.db.session import SessionLocal
from app.domains.admin.repositorio_revision_rs import CatalogRsReviewRepository
from app.domains.admin.servicio_revision_rs import select_review_items
from app.domains.catalog.repositorio_catalogo import CatalogRepository


def _seed_product(db, *, pharmacy_name: str, sku: str, component_code: str, rs: str) -> CommercialProduct:
    pharmacy = Pharmacy(name=pharmacy_name, slug=f"slug-{uuid4().hex[:10]}", active=True)
    component = Component(component_id=component_code, canonical_name="Componente test RS")
    db.add_all([pharmacy, component])
    db.flush()
    product = CommercialProduct(
        pharmacy_id=pharmacy.id,
        sku=sku,
        commercial_name="Vitamina E 400 UI Capsula Blanda",
        url=f"https://example.test/{sku}",
        registro_sanitario=rs,
        price=25.0,
        currency="PEN",
        availability="available",
        commercial_status="active",
        raw_payload_json={"registro_sanitario_source": "digemid_name_match"},
    )
    db.add(product)
    db.flush()
    db.add(
        CommercialProductComponent(
            product_id=product.id,
            component_id=component.id,
            ingredient="VITAMINA E",
            match_score=95.0,
        )
    )
    db.commit()
    return product


def test_upsert_does_not_overwrite_decisions_and_rejected_products_are_hidden():
    pharmacy_name = f"Farmacia RS {uuid4().hex[:8]}"
    sku = f"sku-{uuid4().hex[:10]}"
    component_code = f"COMP_RS_{uuid4().hex[:10]}"
    rows = [
        {
            "pharmacy": pharmacy_name,
            "sku": sku,
            "url": f"https://example.test/{sku}",
            "commercial_name": "Vitamina E 400 UI Capsula Blanda",
            "registro_sanitario": "DE-4803",
            "registro_sanitario_key": "DE4803",
            "registro_sanitario_source": "digemid_name_match",
            "digemid_producto": "VITAMINA E 400 UI",
            "digemid_composicion": "DL-ALFA ACETATO DE TOCOFEROL 400.000000 UI",
            "component_id": component_code,
        }
    ]

    with SessionLocal() as db:
        _seed_product(db, pharmacy_name=pharmacy_name, sku=sku, component_code=component_code, rs="DE-4803")
        repo = CatalogRsReviewRepository(db)

        stats = repo.upsert_items(select_review_items(rows, sample_ratio=0.0))
        db.commit()
        assert stats["inserted"] == 1

        # pending: el producto se sirve y expone el estado
        products = CatalogRepository(db).products_for_component(component_code)
        assert len(products) == 1
        assert products[0]["rs_review_status"] == "pending"

        review = db.scalar(
            select(CatalogRsReview).where(CatalogRsReview.pharmacy == pharmacy_name, CatalogRsReview.sku == sku)
        )
        assert review is not None
        repo.decide(review.id, status="rejected", reviewer_note="nombre no coincide", reviewer_user_id=None)
        db.commit()

        # re-carga: no pisa la decisión
        stats = repo.upsert_items(select_review_items(rows, sample_ratio=0.0))
        db.commit()
        assert stats == {"inserted": 0, "updated": 0, "skipped_decided": 1, "total": 1}
        db.refresh(review)
        assert review.status == "rejected"
        assert review.decided_at is not None

        # rechazado: el producto deja de servirse
        assert CatalogRepository(db).products_for_component(component_code) == []
        assert (review.pharmacy, review.sku) not in {
            (p.name, prod.sku) for prod, p in CatalogRepository(db).search_products(component_id=component_code)
        }

        summary = repo.summary()
        assert summary["by_status"]["rejected"] >= 1
        assert summary["by_sample_reason"]["inferred"] >= 1

        rows_pending, _total = repo.list_reviews(status="rejected", pharmacy=pharmacy_name)
        assert [r.sku for r in rows_pending] == [sku]

        # volver a pending reabre el producto
        repo.decide(review.id, status="pending", reviewer_note=None, reviewer_user_id=None)
        db.commit()
        assert len(CatalogRepository(db).products_for_component(component_code)) == 1


def test_decision_on_old_rs_does_not_affect_new_rs():
    pharmacy_name = f"Farmacia RS {uuid4().hex[:8]}"
    sku = f"sku-{uuid4().hex[:10]}"
    component_code = f"COMP_RS_{uuid4().hex[:10]}"
    with SessionLocal() as db:
        product = _seed_product(db, pharmacy_name=pharmacy_name, sku=sku, component_code=component_code, rs="DE-0001")
        repo = CatalogRsReviewRepository(db)
        repo.upsert_items(
            [
                {
                    "pharmacy": pharmacy_name,
                    "sku": sku,
                    "url": product.url,
                    "commercial_name": product.commercial_name,
                    "registro_sanitario_key": "DE0001",
                    "digemid_producto": None,
                    "digemid_composicion": None,
                    "registro_sanitario_source": "digemid_name_match",
                    "match_reason": None,
                    "sample_reason": "inferred",
                }
            ]
        )
        db.commit()
        review = db.scalar(
            select(CatalogRsReview).where(CatalogRsReview.pharmacy == pharmacy_name, CatalogRsReview.sku == sku)
        )
        repo.decide(review.id, status="rejected", reviewer_note="RS equivocado", reviewer_user_id=None)
        db.commit()
        assert CatalogRepository(db).products_for_component(component_code) == []

        # El catálogo corrige el RS del producto: la decisión antigua no aplica.
        product.registro_sanitario = "DE-0002"
        db.commit()
        products = CatalogRepository(db).products_for_component(component_code)
        assert len(products) == 1
        assert products[0]["rs_review_status"] == "not_required"
