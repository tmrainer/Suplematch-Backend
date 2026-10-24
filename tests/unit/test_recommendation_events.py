"""Base de eventos de recomendacion: dedupe de impresiones, esquemas, impresiones automaticas y retencion (sin Postgres)."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.db.models import RECOMMENDATION_EVENT_TYPES, RecommendationEvent, RecommendationFeedback
from app.domains.feedback.contexto import dedupe_impressions, impression_key
from app.domains.feedback.esquemas import MAX_EVENTS_PER_BATCH, RecommendationEventInput, RecommendationEventsBatch
from app.domains.feedback.repositorio_eventos import RecommendationEventRepository
from app.domains.feedback.servicio_feedback import FeedbackService
from app.domains.labs.servicio_analisis_examenes import LabAnalysisService

ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- dedupe puro
def _impression(**overrides):
    base = {"recommendation_id": "rec_1", "event_type": "impression", "pack_key": "pack_a", "product_id": None, "position": 1}
    return {**base, **overrides}


def test_impression_key_normalizes_types():
    key = impression_key(_impression(position="2"), session_ref="sess")
    assert key == ("sess", "impression", "pack_a", None, 2)
    # Sin session_ref se usa recommendation_id; product_id se normaliza a str.
    product_id = uuid4()
    key = impression_key(_impression(product_id=product_id))
    assert key == ("rec_1", "impression", "pack_a", str(product_id), 1)


def test_dedupe_impressions_drops_repeats_within_batch_and_against_existing():
    events = [
        _impression(position=1),
        _impression(position=1),  # repetida en el lote
        _impression(position=2),
        _impression(pack_key="pack_b", position=1),
        _impression(event_type="click", position=1),  # los clicks nunca se deduplican
        _impression(event_type="click", position=1),
    ]
    existing = {impression_key(_impression(pack_key="pack_b", position=1))}
    accepted, dropped = dedupe_impressions(events, existing_keys=existing)
    assert dropped == 2
    assert [(e["event_type"], e["pack_key"], e["position"]) for e in accepted] == [
        ("impression", "pack_a", 1),
        ("impression", "pack_a", 2),
        ("click", "pack_a", 1),
        ("click", "pack_a", 1),
    ]


def test_dedupe_impressions_distinguishes_product_and_session():
    events = [
        _impression(product_id="11111111-1111-1111-1111-111111111111"),
        _impression(product_id="22222222-2222-2222-2222-222222222222"),
        _impression(recommendation_id="rec_2"),
    ]
    accepted, dropped = dedupe_impressions(events)
    assert dropped == 0 and len(accepted) == 3


def test_dedupe_impressions_uses_session_resolver():
    events = [_impression(recommendation_id="rec_1"), _impression(recommendation_id="rec_1_alias")]
    accepted, dropped = dedupe_impressions(events, session_ref_for=lambda e: "same-session")
    assert dropped == 1 and len(accepted) == 1


# --------------------------------------------------------------------------- esquemas
def test_event_types_in_schema_match_model_constant():
    for event_type in RECOMMENDATION_EVENT_TYPES:
        RecommendationEventInput(recommendation_id="rec_1", event_type=event_type)
    with pytest.raises(ValidationError):
        RecommendationEventInput(recommendation_id="rec_1", event_type="hover")


def test_batch_limits():
    with pytest.raises(ValidationError):
        RecommendationEventsBatch(events=[])
    too_many = [RecommendationEventInput(recommendation_id="rec_1", event_type="click") for _ in range(MAX_EVENTS_PER_BATCH + 1)]
    with pytest.raises(ValidationError):
        RecommendationEventsBatch(events=too_many)
    ok = RecommendationEventsBatch(events=too_many[:MAX_EVENTS_PER_BATCH])
    assert len(ok.events) == 50
    with pytest.raises(ValidationError):
        RecommendationEventInput(recommendation_id="rec_1", event_type="impression", position=-1)


# --------------------------------------------------------------------------- servicio sin BD
def test_save_events_without_database_is_not_persisted():
    batch = RecommendationEventsBatch(events=[RecommendationEventInput(recommendation_id="rec_1", event_type="click")])
    result = FeedbackService(None).save_events(batch)
    assert result["status"] == "not_persisted"
    assert result["accepted"] == 0 and result["event_ids"] == []


# --------------------------------------------------------------------------- impresiones automaticas
class _FakeDb:
    def __init__(self):
        self.added = []
        self.committed = False
        self.executed = []

    def add(self, row):
        self.added.append(row)

    def commit(self):
        self.committed = True

    def execute(self, statement):
        self.executed.append(statement)
        return SimpleNamespace(all=lambda: [], one=lambda: (None, 0))


def test_add_pack_impressions_records_one_impression_per_pack_with_rank_and_context():
    db = _FakeDb()
    session = SimpleNamespace(id=uuid4(), user_id=None, anonymous_session_id="ses_x")
    packs = [
        {"pack_id": "pack_a", "rank": 1, "component_ids": ["cmp_vit_d", "cmp_calcium"], "score_final": 0.9},
        {"pack_id": "pack_b", "rank": 2, "component_ids": ["cmp_zinc"], "score_final": 0.8},
        {"pack_id": "pack_a", "rank": 1},  # duplicado exacto: no se registra dos veces
    ]
    rows = RecommendationEventRepository(db).add_pack_impressions(
        session=session, packs=packs, conditions=["ESTRES_CRONICO", "DEFICIT_VIT_D", "SALUDABLE"]
    )
    assert len(rows) == 2 and len(db.added) == 2
    assert db.committed is False  # el caller (save_response) hace el commit
    first = rows[0]
    assert isinstance(first, RecommendationEvent)
    assert first.event_type == "impression"
    assert first.pack_key == "pack_a" and first.position == 1
    assert first.context_key == "pack_a|DEFICIT_VIT_D+ESTRES_CRONICO"
    assert first.conditions_context_json == ["ESTRES_CRONICO", "DEFICIT_VIT_D", "SALUDABLE"]
    assert first.payload_json["source"] == "backend"
    assert first.payload_json["component_ids"] == ["cmp_vit_d", "cmp_calcium"]
    assert first.anonymous_session_id == "ses_x"
    assert rows[1].position == 2


# --------------------------------------------------------------------------- modelo + migracion
def test_recommendation_event_and_feedback_columns_exist():
    columns = {column.name for column in RecommendationEvent.__table__.columns}
    assert {
        "id", "recommendation_session_id", "user_id", "anonymous_session_id", "event_type", "pack_key",
        "component_id", "product_id", "position", "conditions_context_json", "context_key", "payload_json", "created_at",
    } <= columns
    feedback_columns = {column.name for column in RecommendationFeedback.__table__.columns}
    assert {"context_key", "outcome_json"} <= feedback_columns
    indexed = {column.name for column in RecommendationEvent.__table__.columns if column.index}
    assert {"recommendation_session_id", "pack_key", "event_type", "created_at"} <= indexed


def test_migration_0013_chains_after_0012_and_is_idempotent_by_construction():
    path = ROOT / "alembic/versions/20261022_0013_recommendation_events.py"
    spec = importlib.util.spec_from_file_location("mig_0013", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "20261022_0013"
    assert module.down_revision == "20260630_0012"
    # La misma clave contextual que app.domains.feedback.contexto (se replica para no importar app/ en la migracion).
    from app.domains.feedback.contexto import build_context_key

    conditions = ["ESTRES_CRONICO", "SALUDABLE", "DEFICIT_VIT_D"]
    assert module._context_key("pack_a", conditions) == build_context_key("pack_a", conditions)
    assert module._context_key(None, conditions) is None


# --------------------------------------------------------------------------- retencion de LabReport
class _FakeLabDb:
    def __init__(self, reports):
        self.reports = reports
        self.deleted_biomarkers = []
        self.committed = False

    def scalars(self, statement):
        return list(self.reports)

    def execute(self, statement):
        self.deleted_biomarkers.append(statement)

    def commit(self):
        self.committed = True


def _report(days_old: int, status: str = "processed"):
    return SimpleNamespace(
        id=uuid4(),
        created_at=datetime.now(timezone.utc) - timedelta(days=days_old),
        raw_text="Hemoglobina 12.1 g/dL",
        parsed_payload_json={"x": 1},
        analysis_json={"biomarkers": [1]},
        status=status,
        deleted_at=None,
    )


def test_purge_expired_redacts_reports_and_returns_count(monkeypatch):
    from app.domains.labs import servicio_analisis_examenes as module

    monkeypatch.setattr(module.settings, "LAB_REPORT_RETENTION_DAYS", 365)
    expired = [_report(400), _report(366)]
    db = _FakeLabDb(expired)  # el fake devuelve lo que la query filtraria en Postgres
    count = LabAnalysisService(db).purge_expired()
    assert count == 2
    assert db.committed is True
    assert len(db.deleted_biomarkers) == 2
    for report in expired:
        assert report.status == "deleted"
        assert report.raw_text is None
        assert report.parsed_payload_json == {}
        assert report.analysis_json["deleted"] is True
        assert report.deleted_at is not None


def test_purge_expired_is_noop_without_db_or_with_zero_retention():
    assert LabAnalysisService(None).purge_expired() == 0
    db = _FakeLabDb([_report(900)])
    assert LabAnalysisService(db).purge_expired(retention_days=0) == 0
    assert db.committed is False


def test_purge_script_exists_with_flags():
    text = (ROOT / "scripts/ops/purgar_lab_reports.py").read_text(encoding="utf-8")
    assert "--dry-run" in text and "--days" in text and "purge_expired" in text
