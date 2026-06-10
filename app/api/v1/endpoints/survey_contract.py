from fastapi import APIRouter

from app.schemas.survey_contract import survey_contract


router = APIRouter()


@router.get("")
def get_survey_contract():
    return survey_contract()
