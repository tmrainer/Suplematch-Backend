from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.dependencies import db_session
from app.repositories.catalog_repository import CatalogRepository


router = APIRouter()


@router.get("")
def list_components(
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(db_session),
):
    components = CatalogRepository(db).list_components(limit=limit, offset=offset, query=q)
    return [
        {
            "id": str(component.id),
            "component_id": component.component_id,
            "canonical_name": component.canonical_name,
            "description": component.description,
            "safety_notes": component.safety_notes,
            "metadata": component.metadata_json or {},
        }
        for component in components
    ]
