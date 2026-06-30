"""
Pipeline completo: Encuesta → Modelo 1 → Condición → Modelo 2 → Recomendación
"""

import pandas as pd
import joblib
from app.core.config import settings
from app.ml.explainability import get_condition_scores, build_explainability
from app.ml.runtime.condition_mvp_inference import predict_condition_probabilities
from app.ml.runtime.modelo2_inference import recomendar_suplementos
from app.ml.runtime.feedback_reranker import rerank_packs
from app.ml.runtime.feedback_store import save_recommendation_event

_MODEL_DIR = settings.MODEL_DIR
try:
    _m1 = joblib.load(_MODEL_DIR / "modelo1_pipeline.pkl")
    _pipe_m1 = _m1["pipeline"]
    _labels = _m1["labels"]
    _cat_cols = _m1["cat_cols"]
    _num_cols = _m1["num_cols"]
except Exception:
    _m1 = None
    _pipe_m1 = None
    _labels = []
    _cat_cols = []
    _num_cols = []


def _condition_mvp_available() -> bool:
    return (_MODEL_DIR / "condition_mvp_model.pkl").exists()


_SIGNAL_GROUP_IMPACT: dict[str, str] = {
    "observed_lab":           "alto",
    "medical_safety":         "alto",
    "self_reported_symptoms": "medio",
    "declared_diet":          "medio",
    "profile_context":        "bajo",
    "survey_context":         "bajo",
    "derived_soft_signal":    "bajo",
}


def _explainability_from_condition_mvp(condition_details: list[dict]) -> list[dict]:
    explanations = []
    for item in condition_details:
        if not item.get("positive"):
            continue
        primary_group = item.get("primary_signal_group", "")
        signal_groups = item.get("signal_groups", {})
        drivers = [
            {
                "feature": field,
                "label": field.replace("_", " ").title(),
                "value": "",
                "value_label": signal_groups.get(primary_group, {}).get("strength", ""),
                "impact": _SIGNAL_GROUP_IMPACT.get(primary_group, "bajo"),
            }
            for field in item.get("drivers", [])[:6]
        ]
        explanations.append(
            {
                "condition": item["condition"],
                "probability": item["probability"],
                "drivers": drivers,
            }
        )
    return explanations


def predecir_condicion(usuario: dict) -> tuple[list[str], dict[str, float], pd.DataFrame | None, list[dict]]:
    """Modelo 1: encuesta → condiciones detectadas + probabilidades reales + row_df."""
    if _condition_mvp_available():
        condition_details = predict_condition_probabilities(usuario)
        condition_scores = {
            item["condition"]: float(item["probability"])
            for item in condition_details
        }
        detected = [
            item["condition"]
            for item in condition_details
            if item["positive"]
        ]
        return (detected if detected else ["SALUDABLE"], condition_scores, None, condition_details)

    if _pipe_m1 is None:
        raise RuntimeError("No hay modelo 1 disponible.")

    cols = _cat_cols + _num_cols
    row  = pd.DataFrame([usuario])[cols]

    condition_scores = get_condition_scores(_pipe_m1, _labels, row)

    if condition_scores:
        detected = [label for label, score in condition_scores.items() if score >= 0.45]
    else:
        pred = _pipe_m1.predict(row)[0]
        detected = [_labels[i] for i, v in enumerate(pred) if v == 1]

    return (detected if detected else ["SALUDABLE"]), condition_scores, row, []


def pipeline_vitaminas(usuario: dict, verbose: bool = False) -> dict:
    """
    Pipeline completo.

    Retorna dict con:
        condiciones       : list[str]
        condition_scores  : dict[str, float]  ← probabilidades reales del Modelo 1
        explainability    : list[dict]         ← drivers por condición
        recomendaciones   : list[dict]
        sinergias         : list[tuple]
        alertas           : list[tuple]
        combo_seguro      : bool
        packs_ranked      : list[dict]
        mensaje           : str
    """
    condiciones, condition_scores, row_df, condition_details = predecir_condicion(usuario)

    resultado = recomendar_suplementos(
        condiciones,
        condition_scores=condition_scores,
        user_context=usuario,
    )
    resultado["condiciones"]      = condiciones
    resultado["condition_scores"] = condition_scores
    resultado["condition_details"] = condition_details
    if condition_details:
        resultado["explainability"] = _explainability_from_condition_mvp(condition_details)
    else:
        resultado["explainability"] = build_explainability(
            _pipe_m1, _labels, row_df, condition_scores, usuario
        )

    packs_ranked = rerank_packs(
        recomendaciones=resultado.get("recomendaciones", []),
        conditions=condiciones,
        alertas=resultado.get("alertas", []),
    )
    resultado["packs_ranked"] = packs_ranked

    if packs_ranked:
        rec_id = save_recommendation_event(condiciones, packs_ranked)
        resultado["recommendation_id"] = rec_id

    if verbose:
        print("\n" + "═"*60)
        print("  PIPELINE VITAMINAS — RESULTADO")
        print("═"*60)
        print(f"  Condiciones detectadas : {condiciones}")
        if condition_scores:
            print(f"  Probabilidades reales  : { {k: f'{v:.0%}' for k, v in condition_scores.items()} }")
        print()

        recs = resultado["recomendaciones"]
        if not recs:
            print(f"  {resultado['mensaje']}")
        else:
            by_cond: dict[str, list] = {}
            for r in recs:
                by_cond.setdefault(r["condicion"], []).append(r)

            for cond, items in by_cond.items():
                print(f"  ► {cond}")
                for r in items:
                    tipo = "★" if r["tipo"] == "semilla_directa" else "◆"
                    print(f"      {tipo} {r['nombre']}")
                print()

            if resultado["sinergias"]:
                print(f"  Sinergias ({len(resultado['sinergias'])}):")
                for s in resultado["sinergias"][:5]:
                    if isinstance(s, dict):
                        print(f"    ✓ {s['component_a']}  ↔  {s['component_b']}  [{s['type']}]")
                    else:
                        print(f"    ✓ {s[0]}  ↔  {s[1]}  [{s[2]}]")
                print()

            if resultado["alertas"]:
                print(f"  ⚠  ALERTAS DE SEGURIDAD:")
                for a in resultado["alertas"]:
                    if isinstance(a, dict):
                        print(f"    ✗ {a['component_a']}  +  {a['component_b']}  → {a['type']}")
                    else:
                        print(f"    ✗ {a[0]}  +  {a[1]}  → {a[2]}")
                print()

            seguro = "Sí" if resultado["combo_seguro"] else "NO — revisar alertas"
            print(f"  Combo seguro: {seguro}")

        if packs_ranked:
            print()
            print(f"  PACKS RECOMENDADOS (re-ranking por feedback):")
            for p in packs_ranked:
                nombres = " + ".join(p["component_names"])
                print(f"    #{p['rank']}  {nombres}")
                print(f"        score_final={p['score_final']:.3f}  "
                      f"gnn={p['score_gnn']:.3f}  "
                      f"cobertura={p['score_coverage']:.2f}  "
                      f"feedback={p['score_feedback']:.3f}")
            if resultado.get("recommendation_id"):
                print(f"\n  recommendation_id: {resultado['recommendation_id']}")

        print("═"*60)

    return resultado


if __name__ == "__main__":
    usuarios_demo = [
        {
            "nombre_demo": "María, 28, vegana, oficinista, caída cabello",
            "sexo": "F", "tipo_dieta": "vegano", "exposicion_solar": "baja",
            "nivel_actividad": "sedentario", "edad": 28, "peso_kg": 58.0, "altura_cm": 163.0,
            "fatiga_general": 4, "dolor_muscular": 4, "dolor_articular": 3,
            "niebla_mental": 4, "problemas_sueno": 3, "caida_cabello": 4,
            "piel_seca": 3, "unas_quebradizas": 4, "enfermedad_frecuente": 2,
            "calambres": 2, "irritabilidad": 3,
            "meta_energia": 1, "meta_inmunidad": 0, "meta_belleza": 1,
            "meta_rendimiento": 0, "meta_salud_osea": 0, "meta_cognitivo": 1,
        },
    ]

    for u in usuarios_demo:
        nombre = u.pop("nombre_demo")
        print(f"\n{'─'*60}")
        print(f"  Usuario: {nombre}")
        pipeline_vitaminas(u)
