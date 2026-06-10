from uuid import uuid4

from app.db.models import CommercialProduct, CommercialProductComponent, Component, Pharmacy
from app.db.session import SessionLocal
from app.repositories.admin_repository import AdminRepository
from app.repositories.catalog_repository import CatalogRepository
from app.schemas.admin import ProductAdminUpdate


def test_preferred_override_does_not_remove_product_from_ranking():
    component_code = f"COMP_TEST_{uuid4().hex[:10]}"

    with SessionLocal() as db:
        pharmacy = Pharmacy(name=f"Farmacia {uuid4().hex[:8]}", slug=f"farmacia-{uuid4().hex[:8]}", active=True)
        component = Component(component_id=component_code, canonical_name="Componente test")
        db.add_all([pharmacy, component])
        db.flush()
        product = CommercialProduct(
            pharmacy_id=pharmacy.id,
            sku=f"sku-{uuid4().hex}",
            commercial_name="Producto preferido test",
            url="https://example.test/preferred",
            registro_sanitario="RS-PREF",
            price=25.0,
            currency="PEN",
            availability="available",
            commercial_status="active",
            raw_payload_json={},
        )
        db.add(product)
        db.flush()
        db.add(
            CommercialProductComponent(
                product_id=product.id,
                component_id=component.id,
                ingredient="Componente test",
                match_score=95.0,
            )
        )
        db.commit()

        updated = AdminRepository(db).update_product(
            product.id,
            ProductAdminUpdate(status="active", preferred=True, blocked=False, reason="test preferred"),
            admin_user_id=None,
        )
        assert updated is not None
        assert updated.commercial_status == "active"

        products = CatalogRepository(db).products_for_component(component_code)
        assert len(products) == 1
        assert products[0]["catalog_preferred"] is True

        AdminRepository(db).update_product(
            product.id,
            ProductAdminUpdate(status="blocked", preferred=False, blocked=True, reason="test blocked"),
            admin_user_id=None,
        )
        assert CatalogRepository(db).products_for_component(component_code) == []

        db.delete(product)
        db.delete(component)
        db.delete(pharmacy)
        db.commit()
