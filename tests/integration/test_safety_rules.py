from app.domains.catalog.repositorio_reglas_seguridad import SafetyRuleRepository
from app.db.session import SessionLocal


def test_seed_default_ingredient_safety_rules_is_idempotent():
    with SessionLocal() as db:
        repo = SafetyRuleRepository(db)
        repo.seed_defaults()
        first_count = len(repo.active_rules())
        repo.seed_defaults()
        second_count = len(repo.active_rules())

    assert first_count >= 5
    assert second_count == first_count
