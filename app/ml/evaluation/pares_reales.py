"""Pares (encuesta, examen) de la misma persona desde Postgres, para medir la precision real (precision_real.py).

Dos fuentes:

- ``encuesta``: examenes tipeados o subidos dentro de la encuesta (`lab_results` en `recommendation_sessions`). La
  prediccion se recalcula sin ellos.
- ``examen_subido``: reportes de `lab_reports` (con consentimiento y sin borrar) emparejados con la recomendacion
  del mismo usuario mas cercana en el tiempo, dentro de `window_days`.

Un par por persona (el examen mas reciente): alguien que repite la encuesta diez veces no debe pesar diez veces.
Las sesiones anonimas cuentan cada una como persona distinta (no hay como unirlas).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import LabReport, RecommendationSession
from app.domains.labs.esquemas import LabBiomarkerInput
from app.domains.labs.servicio_analisis_examenes import LabAnalysisService
from app.domains.recommendations.servicio_recomendaciones import (
    _lab_patient_context,
    build_pipeline_input,
)
from app.domains.survey.esquemas_encuesta import EncuestaInput
from app.ml.evaluation.precision_real import ABNORMAL, PrecisionReport, lab_truth, predicted_conditions
from app.ml.feature_builder import FeatureBuilder
from app.ml.runtime.condition_lab_inference import predict_lab_risks
from app.ml.runtime.condition_mvp_inference import apply_second_opinion, predict_condition_probabilities

DEFAULT_WINDOW_DAYS = 90  # la HbA1c refleja ~3 meses; habitos y sol cambian por temporada


def survey_only_details(
    encuesta: EncuestaInput, feature_builder: FeatureBuilder | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Detalle del Modelo 1 (con segunda opinion) y estimaciones NHANES para la encuesta sin examenes."""
    without_labs = encuesta.model_copy(update={"lab_results": []})
    lab_risks = predict_lab_risks(without_labs)
    payload = build_pipeline_input(feature_builder or FeatureBuilder(), without_labs, None, lab_risks)
    return apply_second_opinion(predict_condition_probabilities(payload), payload.get("_second_opinion")), lab_risks


def survey_only_predictions(encuesta: EncuestaInput, feature_builder: FeatureBuilder | None = None) -> dict[str, set[str]]:
    """Lo que el sistema habria marcado con esta encuesta si la persona no hubiera dado examenes."""
    return predicted_conditions(*survey_only_details(encuesta, feature_builder))


def _statuses(biomarkers: list[Any]) -> dict[str, str]:
    """`codigo -> status`; si un examen aparece dos veces, gana el fuera de rango."""
    statuses: dict[str, str] = {}
    for item in biomarkers:
        code = item["code"] if isinstance(item, dict) else item.code
        status = item.get("status") if isinstance(item, dict) else item.status
        if not code or not status:
            continue
        if code not in statuses or (status in ABNORMAL and statuses[code] not in ABNORMAL):
            statuses[code] = str(status)
    return statuses


def _encuesta(payload: dict[str, Any]) -> EncuestaInput | None:
    try:
        return EncuestaInput(**payload)
    except (ValidationError, TypeError):
        return None


def _survey_lab_sessions(db: Session) -> list[RecommendationSession]:
    lab_results = RecommendationSession.input_payload_json["lab_results"]
    rows = db.scalars(
        select(RecommendationSession)
        .where(func.jsonb_typeof(lab_results) == "array", func.jsonb_array_length(lab_results) > 0)
        .order_by(RecommendationSession.created_at.desc())
    ).all()
    latest: dict[str, RecommendationSession] = {}
    for row in rows:
        latest.setdefault(str(row.user_id) if row.user_id else f"anon:{row.id}", row)
    return list(latest.values())


def iter_pairs(
    db: Session,
    report: PrecisionReport,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> Iterator[tuple[str, dict[str, str], EncuestaInput]]:
    """(fuente, statuses del examen, encuesta). Lo que no se puede usar se cuenta en `report.skipped`."""
    analyzer = LabAnalysisService()
    users_done: set[str] = set()

    for session in _survey_lab_sessions(db):
        encuesta = _encuesta(session.input_payload_json or {})
        if encuesta is None:
            report.skip("encuesta_invalida")
            continue
        try:
            values = [LabBiomarkerInput(**item) for item in session.input_payload_json.get("lab_results") or []]
        except (ValidationError, TypeError):
            report.skip("examen_invalido")
            continue
        analysis = analyzer.analyze_manual(values, persist=False, source_note="precision_real", context=_lab_patient_context(encuesta))
        if session.user_id:
            users_done.add(str(session.user_id))
        yield "encuesta", _statuses(analysis.get("biomarkers") or []), encuesta

    reports = db.scalars(
        select(LabReport)
        .options(selectinload(LabReport.biomarkers))
        .where(LabReport.deleted_at.is_(None), LabReport.consent_health_data.is_(True), LabReport.user_id.is_not(None))
        .order_by(LabReport.created_at.desc())
    ).all()
    window = timedelta(days=window_days)
    for lab_report in reports:
        user_key = str(lab_report.user_id)
        if user_key in users_done:
            continue  # ya tiene un par mas directo, o un examen mas reciente
        users_done.add(user_key)
        sessions = db.scalars(
            select(RecommendationSession).where(
                RecommendationSession.user_id == lab_report.user_id,
                RecommendationSession.created_at >= lab_report.created_at - window,
                RecommendationSession.created_at <= lab_report.created_at + window,
            )
        ).all()
        if not sessions:
            report.skip("examen_sin_encuesta_cercana")
            continue
        nearest = min(sessions, key=lambda row: abs((row.created_at - lab_report.created_at).total_seconds()))
        encuesta = _encuesta(nearest.input_payload_json or {})
        if encuesta is None:
            report.skip("encuesta_invalida")
            continue
        yield "examen_subido", _statuses(lab_report.biomarkers), encuesta


def measure(db: Session, window_days: int = DEFAULT_WINDOW_DAYS) -> PrecisionReport:
    report = PrecisionReport()
    feature_builder = FeatureBuilder()
    for source, statuses, encuesta in iter_pairs(db, report, window_days):
        truth = lab_truth(statuses)
        if not truth:
            report.skip("examen_sin_condicion_evaluable")
            continue
        report.add_pair(source, truth, survey_only_predictions(encuesta, feature_builder))
    return report
