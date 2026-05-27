def load_all_models() -> dict:
    models = {
        "pipeline_vitaminas": None,
    }

    try:
        from app.ml.runtime.pipeline_completo import pipeline_vitaminas

        models["pipeline_vitaminas"] = pipeline_vitaminas
        print("[OK] pipeline_vitaminas cargado correctamente.")

    except Exception as exc:
        print(f"[WARN] No se pudo cargar pipeline_vitaminas: {exc}")

    return models
