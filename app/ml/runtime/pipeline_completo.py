"""
Pipeline completo: Encuesta → Modelo 1 → Condición → Modelo 2 → Recomendación

Uso:
    python pipeline_completo.py
    from pipeline_completo import pipeline_vitaminas
"""

import pandas as pd
import joblib
from pathlib import Path
from app.ml.runtime.modelo2_inference import recomendar_suplementos
from app.ml.runtime.feedback_reranker import rerank_packs
from app.ml.runtime.feedback_store import save_recommendation_event

# ─── Cargar Modelo 1 ──────────────────────────────────────────────────────────
_DIR = Path(__file__).parent
_m1 = joblib.load(_DIR / "modelo1_pipeline.pkl")
_pipe_m1 = _m1["pipeline"]
_labels   = _m1["labels"]
_cat_cols = _m1["cat_cols"]
_num_cols = _m1["num_cols"]


def predecir_condicion(usuario: dict) -> list[str]:
    """Modelo 1: encuesta → lista de condiciones."""
    cols = _cat_cols + _num_cols
    row  = pd.DataFrame([usuario])[cols]
    pred = _pipe_m1.predict(row)[0]
    detected = [_labels[i] for i, v in enumerate(pred) if v == 1]
    return detected if detected else ["SALUDABLE"]


def pipeline_vitaminas(usuario: dict, verbose: bool = True) -> dict:
    """
    Pipeline completo.

    Parámetros
    ----------
    usuario : dict con todos los campos de la encuesta
    verbose : imprime resumen en consola

    Retorna
    -------
    dict con:
        condiciones       : list[str]
        recomendaciones   : list[dict]
        sinergias         : list[tuple]
        alertas           : list[tuple]
        combo_seguro      : bool
        mensaje           : str
    """
    # ── Modelo 1: clasificar condiciones ─────────────────────────────────────
    condiciones = predecir_condicion(usuario)

    # ── Modelo 2: recomendar suplementos ─────────────────────────────────────
    resultado = recomendar_suplementos(condiciones)
    resultado["condiciones"] = condiciones

    # ── Re-ranking por feedback ───────────────────────────────────────────────
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
        print()

        recs = resultado["recomendaciones"]
        if not recs:
            print(f"  {resultado['mensaje']}")
        else:
            # Agrupar por condición
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
                    print(f"    ✓ {s[0]}  ↔  {s[1]}  [{s[2]}]")
                if len(resultado["sinergias"]) > 5:
                    print(f"    ... y {len(resultado['sinergias'])-5} más")
                print()

            if resultado["alertas"]:
                print(f"  ⚠  ALERTAS DE SEGURIDAD:")
                for a in resultado["alertas"]:
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


# ─── Demo ─────────────────────────────────────────────────────────────────────
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
        {
            "nombre_demo": "Carlos, 35, omnívoro, deportista, calambres",
            "sexo": "M", "tipo_dieta": "omnivoro", "exposicion_solar": "media",
            "nivel_actividad": "muy_activo", "edad": 35, "peso_kg": 82.0, "altura_cm": 178.0,
            "fatiga_general": 3, "dolor_muscular": 4, "dolor_articular": 2,
            "niebla_mental": 2, "problemas_sueno": 4, "caida_cabello": 2,
            "piel_seca": 2, "unas_quebradizas": 2, "enfermedad_frecuente": 2,
            "calambres": 4, "irritabilidad": 3,
            "meta_energia": 1, "meta_inmunidad": 0, "meta_belleza": 0,
            "meta_rendimiento": 1, "meta_salud_osea": 0, "meta_cognitivo": 0,
        },
        {
            "nombre_demo": "Ana, 45, omnívora, enferma frecuente",
            "sexo": "F", "tipo_dieta": "omnivoro", "exposicion_solar": "media",
            "nivel_actividad": "sedentario", "edad": 45, "peso_kg": 67.0, "altura_cm": 162.0,
            "fatiga_general": 3, "dolor_muscular": 2, "dolor_articular": 2,
            "niebla_mental": 2, "problemas_sueno": 2, "caida_cabello": 2,
            "piel_seca": 2, "unas_quebradizas": 2, "enfermedad_frecuente": 4,
            "calambres": 2, "irritabilidad": 2,
            "meta_energia": 0, "meta_inmunidad": 1, "meta_belleza": 0,
            "meta_rendimiento": 0, "meta_salud_osea": 1, "meta_cognitivo": 0,
        },
    ]

    for u in usuarios_demo:
        nombre = u.pop("nombre_demo")
        print(f"\n\n{'─'*60}")
        print(f"  Usuario: {nombre}")
        pipeline_vitaminas(u)
