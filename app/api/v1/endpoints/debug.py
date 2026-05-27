from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/model-status")
def model_status(request: Request):
    models = request.app.state.models

    return {
        "models": {
            name: model is not None
            for name, model in models.items()
        }
    }
