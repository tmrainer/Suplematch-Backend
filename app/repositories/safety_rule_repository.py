from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.observability import log_event
from app.db.models import AdminAction, IngredientSafetyRule
from app.services.product_safety import DEFAULT_INGREDIENT_SAFETY_RULES, IngredientSafetyRuleData


class SafetyRuleRepository:
    def __init__(self, db: Session):
        self.db = db

    def seed_defaults(self) -> int:
        created = 0
        for rule_data in DEFAULT_INGREDIENT_SAFETY_RULES:
            existing = self.db.scalar(select(IngredientSafetyRule).where(IngredientSafetyRule.name == rule_data.name))
            if existing is not None:
                continue
            self.db.add(self._from_data(rule_data))
            created += 1
        if created:
            self.db.commit()
            log_event("ingredient_safety_rules_seeded", created=created)
        return created

    def active_rules(self) -> list[IngredientSafetyRule]:
        return list(
            self.db.scalars(
                select(IngredientSafetyRule)
                .where(IngredientSafetyRule.active.is_(True))
                .order_by(IngredientSafetyRule.severity.desc(), IngredientSafetyRule.name.asc())
            )
        )

    def list_rules(self, *, active: bool | None = None, limit: int = 100, offset: int = 0) -> list[IngredientSafetyRule]:
        stmt = select(IngredientSafetyRule).order_by(IngredientSafetyRule.name.asc())
        if active is not None:
            stmt = stmt.where(IngredientSafetyRule.active.is_(active))
        return list(self.db.scalars(stmt.offset(offset).limit(limit)))

    def upsert_rule(
        self,
        *,
        name: str,
        ingredient_pattern: str,
        restriction_code: str | None,
        safety_condition_code: str | None,
        action: str,
        severity: str,
        message: str,
        active: bool,
        source: str,
        admin_user_id: UUID | None,
    ) -> IngredientSafetyRule:
        rule = self.db.scalar(select(IngredientSafetyRule).where(IngredientSafetyRule.name == name))
        before = self._snapshot(rule) if rule is not None else {}
        if rule is None:
            rule = IngredientSafetyRule(name=name)
            self.db.add(rule)

        rule.ingredient_pattern = ingredient_pattern
        rule.restriction_code = restriction_code
        rule.safety_condition_code = safety_condition_code
        rule.action = action
        rule.severity = severity
        rule.message = message
        rule.active = active
        rule.source = source

        self.db.flush()
        self.db.add(
            AdminAction(
                admin_user_id=admin_user_id,
                action_type="upsert_ingredient_safety_rule",
                entity_type="ingredient_safety_rule",
                entity_id=str(rule.id),
                before_json=before,
                after_json=self._snapshot(rule),
            )
        )
        self.db.commit()
        self.db.refresh(rule)
        log_event(
            "ingredient_safety_rule_upserted",
            rule_id=str(rule.id),
            name=rule.name,
            action=rule.action,
            severity=rule.severity,
            admin_user_id=str(admin_user_id) if admin_user_id else None,
        )
        return rule

    def update_rule(self, rule_id: UUID | str, values: dict, *, admin_user_id: UUID | None) -> IngredientSafetyRule | None:
        rule = self.db.get(IngredientSafetyRule, rule_id)
        if rule is None:
            return None
        before = self._snapshot(rule)
        for key, value in values.items():
            setattr(rule, key, value)
        self.db.add(
            AdminAction(
                admin_user_id=admin_user_id,
                action_type="update_ingredient_safety_rule",
                entity_type="ingredient_safety_rule",
                entity_id=str(rule.id),
                before_json=before,
                after_json=self._snapshot(rule),
            )
        )
        self.db.commit()
        self.db.refresh(rule)
        return rule

    def _from_data(self, data: IngredientSafetyRuleData) -> IngredientSafetyRule:
        return IngredientSafetyRule(
            name=data.name,
            ingredient_pattern=data.ingredient_pattern,
            restriction_code=data.restriction_code,
            safety_condition_code=data.safety_condition_code,
            action=data.action,
            severity=data.severity,
            message=data.message,
            active=data.active,
            source=data.source,
        )

    def _snapshot(self, rule: IngredientSafetyRule | None) -> dict:
        if rule is None:
            return {}
        return {
            "name": rule.name,
            "ingredient_pattern": rule.ingredient_pattern,
            "restriction_code": rule.restriction_code,
            "safety_condition_code": rule.safety_condition_code,
            "action": rule.action,
            "severity": rule.severity,
            "message": rule.message,
            "active": rule.active,
            "source": rule.source,
        }
