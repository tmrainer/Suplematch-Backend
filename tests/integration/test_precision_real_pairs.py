"""Pares (encuesta, examen) reales desde Postgres: las dos fuentes y que la prediccion ignora los examenes."""

from __future__ import annotations

from sqlalchemy import delete, select

from app.db.models import LabReport, RecommendationSession, User
from app.db.session import SessionLocal
from app.main import create_app
from app.ml.evaluation.pares_reales import measure
from tests.integration.test_health import asgi_request
from tests.integration.test_recommend_endpoint import _auth_headers, _survey_payload, needs_models

EMAILS = ("precision-encuesta@suplematch.test", "precision-examen@suplematch.test")


def _counts(report: dict) -> tuple[dict, int, int]:
    vit_d = report["conditions"].get("DEFICIT_VIT_D", {"n": 0, "prevalence": 0.0})
    return report["sources"], vit_d["n"], round(vit_d["n"] * vit_d["prevalence"])


def _cleanup(recommendation_ids: list[str]) -> None:
    with SessionLocal() as db:
        user_ids = list(db.scalars(select(User.id).where(User.email.in_(EMAILS))))
        db.execute(delete(RecommendationSession).where(RecommendationSession.recommendation_id.in_(recommendation_ids)))
        if user_ids:
            db.execute(delete(LabReport).where(LabReport.user_id.in_(user_ids)))
            db.execute(delete(User).where(User.id.in_(user_ids)))
        db.commit()


@needs_models
def test_both_sources_are_paired_and_predicted_without_the_labs():
    from app.ml.model_loader import load_all_models

    app = create_app()
    app.state.models = load_all_models()
    with SessionLocal() as db:
        before = measure(db).to_dict()

    created = []
    try:
        # Fuente 1: vitamina D baja tipeada dentro de la encuesta.
        headers = _auth_headers(EMAILS[0])
        payload = {**_survey_payload(), "lab_results": [{"code": "vitamin_d", "value": 12, "unit": "ng/mL"}]}
        status_code, body = asgi_request(app, "POST", "/api/v1/recommend", payload, headers=headers)
        assert status_code == 200, body
        created.append(body["recommendation_id"])

        # Fuente 2: examen subido aparte (vitamina D normal) y encuesta sin examenes del mismo usuario.
        headers = _auth_headers(EMAILS[1])
        lab = {"consent_health_data": True, "persist": True, "biomarkers": [{"code": "vitamin_d", "value": 35, "unit": "ng/mL"}]}
        status_code, body = asgi_request(app, "POST", "/api/v1/labs/manual", lab, headers=headers)
        assert status_code == 200, body
        status_code, body = asgi_request(app, "POST", "/api/v1/recommend", _survey_payload(), headers=headers)
        assert status_code == 200, body
        created.append(body["recommendation_id"])

        with SessionLocal() as db:
            after = measure(db).to_dict()
    finally:
        _cleanup(created)

    sources_before, n_before, pos_before = _counts(before)
    sources_after, n_after, pos_after = _counts(after)
    assert sources_after.get("encuesta", 0) == sources_before.get("encuesta", 0) + 1
    assert sources_after.get("examen_subido", 0) == sources_before.get("examen_subido", 0) + 1
    assert (n_after, pos_after) == (n_before + 2, pos_before + 1)


@needs_models
def test_prediction_is_the_same_with_or_without_the_labs():
    from app.domains.survey.esquemas_encuesta import EncuestaInput
    from app.ml.evaluation.pares_reales import survey_only_predictions

    with_lab = EncuestaInput(**_survey_payload(), lab_results=[{"code": "vitamin_d", "value": 8, "unit": "ng/mL"}])
    assert survey_only_predictions(with_lab) == survey_only_predictions(EncuestaInput(**_survey_payload()))
