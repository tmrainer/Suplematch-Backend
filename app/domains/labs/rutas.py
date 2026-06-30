from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.api.v1.dependencies import current_user, db_session, optional_current_user
from app.db.models import User
from app.domains.auth.esquemas import MessageOut
from app.domains.labs.esquemas import LabAnalysisOut, LabDataExportOut, LabManualInput, LabReportHistoryOut, LabTextInput
from app.domains.labs.servicio_analisis_examenes import LabAnalysisService


router = APIRouter()


@router.post("/manual", response_model=LabAnalysisOut)
def analyze_manual_labs(
    data: LabManualInput,
    user: User | None = Depends(optional_current_user),
    db: Session = Depends(db_session),
):
    return LabAnalysisService(db).analyze_manual(
        data.biomarkers,
        user=user,
        persist=data.persist,
        source_note=data.source_note,
    )


@router.post("/text", response_model=LabAnalysisOut)
def analyze_lab_text(
    data: LabTextInput,
    user: User | None = Depends(optional_current_user),
    db: Session = Depends(db_session),
):
    return LabAnalysisService(db).analyze_text(
        data.raw_text,
        source_type=data.source_type,
        user=user,
        persist=data.persist,
        ocr_engine="manual_text",
    )


@router.post("/upload", response_model=LabAnalysisOut)
async def analyze_lab_upload(
    request: Request,
    user: User | None = Depends(optional_current_user),
    db: Session = Depends(db_session),
):
    form = await request.form()
    consent_health_data = str(form.get("consent_health_data") or "").lower() in {"1", "true", "yes", "si", "sí"}
    persist = str(form.get("persist") or "true").lower() in {"1", "true", "yes", "si", "sí"}
    file = form.get("file")
    if not consent_health_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Debe aceptar el consentimiento para procesar datos de salud.",
        )
    if not isinstance(file, UploadFile):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Archivo requerido.")
    return await LabAnalysisService(db).analyze_upload(file, user=user, persist=persist)


@router.get("/me", response_model=list[LabReportHistoryOut])
def my_lab_reports(
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    return LabAnalysisService(db).history(user)


@router.get("/me/export", response_model=LabDataExportOut)
def export_my_lab_reports(
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    return LabAnalysisService(db).export_user_health_data(user)


@router.delete("/me/{report_id}", response_model=MessageOut)
def delete_my_lab_report(
    report_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    deleted = LabAnalysisService(db).delete_report(user, report_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reporte no encontrado.")
    return MessageOut(message="Reporte de salud eliminado.")


@router.delete("/me", response_model=MessageOut)
def delete_all_my_lab_reports(
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    count = LabAnalysisService(db).delete_all_user_health_data(user)
    return MessageOut(message=f"Reportes de salud eliminados: {count}.")
