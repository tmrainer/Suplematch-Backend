"""Embudo de la encuesta: eventos por paso y resumen de abandono contra Postgres."""

from uuid import uuid4

from sqlalchemy import delete

from app.db.models import SurveyStepEvent
from app.db.session import SessionLocal
from app.domains.survey.embudo import funnel_summary
from app.main import create_app
from tests.integration.test_health import asgi_request


def _events(session_id: str, steps: list[str], submit: bool) -> list[dict]:
    events = []
    for index, step in enumerate(steps):
        events.append({"survey_session_id": session_id, "step_key": step, "event_type": "view", "position": index, "visible_steps": 5, "contract_version": "2026-10-24.1"})
        if index < len(steps) - 1 or submit:
            events.append({"survey_session_id": session_id, "step_key": step, "event_type": "complete", "position": index})
    if submit:
        events.append({"survey_session_id": session_id, "step_key": "resumen", "event_type": "submit"})
    return events


def test_survey_events_are_saved_and_summarized():
    app = create_app()
    finished = f"sv_{uuid4().hex}"
    dropped = f"sv_{uuid4().hex}"
    try:
        status_code, body = asgi_request(app, "POST", "/api/v1/survey/events", {"events": _events(finished, ["sexo", "tipo_dieta", "fatiga"], True)})
        assert status_code == 200, body
        assert body == {"status": "ok", "accepted": 7}
        status_code, _ = asgi_request(app, "POST", "/api/v1/survey/events", {"events": _events(dropped, ["sexo", "tipo_dieta"], False)})
        assert status_code == 200

        with SessionLocal() as db:
            summary = funnel_summary(db, days=1)
        steps = {item["step_key"]: item for item in summary["steps"]}
        assert summary["sessions"] >= 2 and summary["submitted"] >= 1
        assert steps["tipo_dieta"]["abandoned_here"] >= 1
        assert [item["step_key"] for item in summary["steps"]][:3] == ["sexo", "tipo_dieta", "fatiga"]
    finally:
        with SessionLocal() as db:
            db.execute(delete(SurveyStepEvent).where(SurveyStepEvent.survey_session_id.in_([finished, dropped])))
            db.commit()


def test_survey_events_reject_answers_and_bad_steps():
    app = create_app()
    bad_step = {"events": [{"survey_session_id": "sv_12345678", "step_key": "Fatiga; DROP", "event_type": "view"}]}
    assert asgi_request(app, "POST", "/api/v1/survey/events", bad_step)[0] == 422
    bad_type = {"events": [{"survey_session_id": "sv_12345678", "step_key": "fatiga", "event_type": "answer"}]}
    assert asgi_request(app, "POST", "/api/v1/survey/events", bad_type)[0] == 422


def test_funnel_requires_admin():
    app = create_app()
    status_code, _ = asgi_request(app, "GET", "/api/v1/survey/funnel")
    assert status_code in (401, 403)
