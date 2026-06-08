"""
Modelo 2 — INFERENCIA (importar en producción)
Carga artefactos pre-entrenados. Sin re-entrenamiento.
Requiere: modelo2_artifacts.pkl (generado por modelo2_train.py)
"""

import numpy as np
import pandas as pd
import joblib

from app.core.config import settings

_artifacts = None
_ARTIFACTS_PATH = settings.MODEL_DIR / "modelo2_artifacts.pkl"


def _load():
    global _artifacts
    if _artifacts is None:
        _artifacts = joblib.load(_ARTIFACTS_PATH)


def recomendar_suplementos(
    conditions: list,
    min_similarity: float = 0.3,
) -> dict:
    """
    Input : condiciones de Modelo 1  (ej: ['DEFICIT_VIT_D', 'BAJA_INMUNIDAD'])
    Output: dict con recomendaciones, sinergias, alertas, combo_seguro
    """
    _load()
    a = _artifacts

    if conditions == ["SALUDABLE"] or not conditions:
        return {
            "recomendaciones": [],
            "sinergias": [],
            "alertas": [],
            "combo_seguro": True,
            "mensaje": "Perfil saludable. Mantener dieta balanceada.",
        }

    conditions = [c for c in conditions if c != "SALUDABLE"]

    Z             = a["embeddings"]
    comp_to_idx   = a["comp_to_idx"]
    idx_to_comp   = a["idx_to_comp"]
    comp_to_name  = a["comp_to_name"]
    risky_pairs   = a["risky_pairs"]
    functional_pairs = a["functional_pairs"]
    cond_seeds    = a["condition_seeds"]
    master_names  = a["master_names"]
    edges_df      = a["edges_df_subset"]

    def find_ids(query: str) -> list:
        mask = master_names["canonical_name"].str.contains(query, case=False, na=False)
        ids  = master_names.loc[mask, "component_id"].tolist()
        exact = master_names.loc[
            master_names["canonical_name"].str.lower() == query.lower(), "component_id"
        ].tolist()
        return exact if exact else ids

    # ── Semillas directas ─────────────────────────────────────────────────────
    seed_name_to_cond = {}
    seed_ids_map = {}
    for cond in conditions:
        for seed in cond_seeds.get(cond, []):
            if seed not in seed_name_to_cond:
                seed_name_to_cond[seed] = cond
                ids = find_ids(seed)
                if ids:
                    seed_ids_map[seed] = ids

    all_seed_ids = [ids[0] for ids in seed_ids_map.values()]
    seed_valid   = [sid for sid in all_seed_ids if sid in comp_to_idx]

    if not seed_valid:
        return {"recomendaciones": [], "sinergias": [], "alertas": [],
                "combo_seguro": True, "mensaje": "Semillas no encontradas en grafo."}

    # ── Candidatos por similitud GNN ─────────────────────────────────────────
    seed_idxs = [comp_to_idx[sid] for sid in seed_valid]
    centroid  = Z[seed_idxs].mean(axis=0, keepdims=True)
    norms     = np.linalg.norm(Z, axis=1, keepdims=True) + 1e-8
    cos_sim   = (Z @ centroid.T).squeeze() / (norms.squeeze() * (np.linalg.norm(centroid) + 1e-8))

    seed_idx_set = set(seed_idxs)
    candidate_mask = np.ones(len(Z), dtype=bool)
    candidate_mask[list(seed_idx_set)] = False
    ranked = [i for i in np.argsort(-cos_sim)
              if candidate_mask[i] and cos_sim[i] >= min_similarity]

    # ── Construir lista de recomendaciones ────────────────────────────────────
    recomendaciones = []
    for seed_name, ids in seed_ids_map.items():
        cid = ids[0]
        recomendaciones.append({
            "nombre":       comp_to_name.get(cid, seed_name),
            "condicion":    seed_name_to_cond[seed_name],
            "score":        1.0,
            "component_id": cid,
            "tipo":         "semilla_directa",
        })

    added_ids = {r["component_id"] for r in recomendaciones}
    for cand_idx in ranked[:20]:  # revisar top-20 candidatos GNN
        cand_id = idx_to_comp[cand_idx]
        if cand_id in added_ids:
            continue
        has_support = any(
            (cand_id, sid) in functional_pairs or (sid, cand_id) in functional_pairs
            for sid in seed_valid
        )
        if has_support:
            recomendaciones.append({
                "nombre":       comp_to_name.get(cand_id, cand_id),
                "condicion":    "soporte_funcional",
                "score":        float(cos_sim[cand_idx]),
                "component_id": cand_id,
                "tipo":         "candidato_gnn",
            })
            added_ids.add(cand_id)
            if len([r for r in recomendaciones if r["tipo"] == "candidato_gnn"]) >= 3:
                break

    # Deduplicar
    seen, recs_dedup = set(), []
    for r in recomendaciones:
        if r["component_id"] not in seen:
            seen.add(r["component_id"])
            recs_dedup.append(r)

    rec_ids = [r["component_id"] for r in recs_dedup]

    # ── Sinergias ─────────────────────────────────────────────────────────────
    sinergias = []
    for i in range(len(rec_ids)):
        for j in range(i + 1, len(rec_ids)):
            a_id, b_id = rec_ids[i], rec_ids[j]
            if (a_id, b_id) in functional_pairs:
                rel = edges_df[
                    ((edges_df["component_id_a"] == a_id) & (edges_df["component_id_b"] == b_id)) |
                    ((edges_df["component_id_a"] == b_id) & (edges_df["component_id_b"] == a_id))
                ]["relationship_subclass"].values
                sinergias.append((
                    comp_to_name.get(a_id, a_id),
                    comp_to_name.get(b_id, b_id),
                    rel[0] if len(rel) > 0 else "soporte_funcional",
                ))

    # ── Alertas ───────────────────────────────────────────────────────────────
    alertas = []
    for i in range(len(rec_ids)):
        for j in range(i + 1, len(rec_ids)):
            a_id, b_id = rec_ids[i], rec_ids[j]
            if (a_id, b_id) in risky_pairs:
                alertas.append((
                    comp_to_name.get(a_id, a_id),
                    comp_to_name.get(b_id, b_id),
                    "INTERACCION_RIESGOSA",
                ))

    combo_seguro = len(alertas) == 0
    return {
        "recomendaciones": recs_dedup,
        "sinergias":       sinergias,
        "alertas":         alertas,
        "combo_seguro":    combo_seguro,
        "mensaje":         "OK" if combo_seguro else f"{len(alertas)} interacción(es) riesgosa(s).",
    }
