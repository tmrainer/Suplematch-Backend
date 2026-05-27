"""
Modelo 2 — Recomendador GNN de suplementos
Input  : lista de condiciones de Modelo 1 (ej: ['DEFICIT_VIT_D', 'DEFICIT_MAGNESIO'])
Output : combinación óptima de vitaminas/suplementos con sinergias y alertas
Guarda : modelo2_artifacts.pkl (embeddings + grafo + mappings)
"""

import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import joblib
import warnings
warnings.filterwarnings("ignore")

from torch_geometric.data import Data
from torch_geometric.nn import SAGEConv
from torch_geometric.utils import negative_sampling
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score

DATA_DIR = "/Users/joaquinsalazar/Desktop/DPD/MODELO"
SEED = 42
torch.manual_seed(SEED)
np.random.seed(SEED)
device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")

# ─── Mapeo condición → vitaminas semilla ──────────────────────────────────────
# Nombres parciales que se buscan en master['canonical_name'] con str.contains
CONDITION_SEEDS = {
    "DEFICIT_VIT_D": [
        "Vitamin D", "Calcium", "Vitamin K", "Magnesium",
    ],
    "DEFICIT_B12": [
        "Vitamin B12", "Folic Acid", "Folate", "Vitamin B6",
    ],
    "DEFICIT_HIERRO": [
        "Iron", "Vitamin C",
    ],
    "DEFICIT_MAGNESIO": [
        "Magnesium", "Vitamin D", "Zinc", "Vitamin B6",
    ],
    "BAJA_INMUNIDAD": [
        "Vitamin C", "Zinc", "Selenium", "Vitamin D",
    ],
    "RENDIMIENTO_DEPORTIVO": [
        "Carnitine", "Omega-3", "Magnesium", "Vitamin B12", "Zinc",
    ],
    "SALUD_CAPILAR_PIEL": [
        "Biotin", "collagen", "Vitamin E", "Zinc", "Selenium",
    ],
    "FATIGA_CRONICA": [
        "Vitamin B12", "Iron", "Magnesium", "Ashwagandha", "Vitamin C",
    ],
    "SALUDABLE": [],
}

# ─── 1. Cargar datos ───────────────────────────────────────────────────────────
print("Cargando datos...")
master   = pd.read_csv(f"{DATA_DIR}/Component_Master_Clean.csv")
edges_df = pd.read_csv(f"{DATA_DIR}/Component_Relationship_Edges_Clean.csv")

# ─── 2. Filtrar solo edges relevantes (excluye normalización/ruido) ────────────
USEFUL_CLASSES = {
    "SOPORTE_FUNCIONAL", "INTERACCION_VALIDADA",
    "BENEFICIOSA", "SOPORTE_METABOLICO", "COFACTOR_FUNCIONAL",
    "SOPORTE_ANTIOXIDANTE", "INEFICAZ", "ANULACION",
}
edges_clean = edges_df[edges_df["relationship_class"].isin(USEFUL_CLASSES)].copy()

# Pares riesgosos (bidireccional)
risky_pairs = set()
for _, r in edges_df[edges_df["relationship_class"] == "RIESGOSA"].iterrows():
    risky_pairs.add((r["component_id_a"], r["component_id_b"]))
    risky_pairs.add((r["component_id_b"], r["component_id_a"]))

# Pares con soporte funcional (para filtrar recomendaciones)
functional_pairs = set()
for _, r in edges_df[edges_df["relationship_class"] == "SOPORTE_FUNCIONAL"].iterrows():
    functional_pairs.add((r["component_id_a"], r["component_id_b"]))
    functional_pairs.add((r["component_id_b"], r["component_id_a"]))

print(f"Componentes: {len(master)}  |  Edges útiles: {len(edges_clean)}  |  Pares riesgosos: {len(risky_pairs)//2}")

# ─── 3. Feature matrix ────────────────────────────────────────────────────────
FEATURE_COLS = [
    "source_count", "has_regulatory_signal", "has_safety_signal",
    "regulatory_signal_count", "safety_signal_count",
    "total_ensayos_clinicos", "ensayos_completados",
    "tasa_no_completado", "tasa_riesgo_toxicidad",
    "interaction_degree_drugbank",
]
node_feat = master[["component_id"] + FEATURE_COLS].copy()
node_feat["has_regulatory_signal"] = node_feat["has_regulatory_signal"].astype(int)
node_feat["has_safety_signal"]     = node_feat["has_safety_signal"].astype(int)
node_feat = node_feat.fillna(0).reset_index(drop=True)

comp_to_idx = {cid: i for i, cid in enumerate(node_feat["component_id"])}
idx_to_comp = {i: cid for cid, i in comp_to_idx.items()}
comp_to_name = dict(zip(master["component_id"], master["canonical_name"]))

scaler = StandardScaler()
X_np = scaler.fit_transform(node_feat[FEATURE_COLS].values)
x = torch.tensor(X_np, dtype=torch.float).to(device)

# ─── 4. Construir grafo PyG ────────────────────────────────────────────────────
valid_edges = edges_clean[
    edges_clean["component_id_a"].isin(comp_to_idx) &
    edges_clean["component_id_b"].isin(comp_to_idx)
]
src = [comp_to_idx[c] for c in valid_edges["component_id_a"]]
dst = [comp_to_idx[c] for c in valid_edges["component_id_b"]]
edge_index = torch.tensor([src + dst, dst + src], dtype=torch.long).to(device)
data = Data(x=x, edge_index=edge_index, num_nodes=x.shape[0])

# Split 70/30 para train/test
perm = torch.randperm(len(src))
n_train = int(0.7 * len(src))
train_src = torch.tensor(src)[perm[:n_train]]
train_dst = torch.tensor(dst)[perm[:n_train]]
train_edge_index = torch.stack([train_src, train_dst]).to(device)

# ─── 5. GraphSAGE ─────────────────────────────────────────────────────────────
class GraphSAGE(nn.Module):
    def __init__(self, in_ch, hidden_ch, out_ch):
        super().__init__()
        self.conv1 = SAGEConv(in_ch, hidden_ch)
        self.conv2 = SAGEConv(hidden_ch, out_ch)

    def encode(self, x, edge_index):
        x = self.conv1(x, edge_index).relu()
        x = F.dropout(x, p=0.3, training=self.training)
        return self.conv2(x, edge_index)

    def decode(self, z, ei):
        return (z[ei[0]] * z[ei[1]]).sum(dim=-1)


def train_step(model, opt):
    model.train()
    opt.zero_grad()
    neg = negative_sampling(edge_index=data.edge_index,
                            num_nodes=x.shape[0],
                            num_neg_samples=train_edge_index.shape[1]).to(device)
    z = model.encode(x, train_edge_index)
    pos_score = model.decode(z, train_edge_index)
    neg_score = model.decode(z, neg)
    loss = F.binary_cross_entropy_with_logits(
        torch.cat([pos_score, neg_score]),
        torch.cat([torch.ones(pos_score.size(0)),
                   torch.zeros(neg_score.size(0))]).to(device)
    )
    loss.backward()
    opt.step()
    return loss.item()


model = GraphSAGE(in_ch=len(FEATURE_COLS), hidden_ch=64, out_ch=32).to(device)
opt   = torch.optim.Adam(model.parameters(), lr=0.005, weight_decay=1e-4)

print("\nEntrenando GraphSAGE...")
for epoch in range(150):
    loss = train_step(model, opt)
    if (epoch + 1) % 30 == 0:
        print(f"  Epoch {epoch+1:3d} | Loss: {loss:.4f}")

# Embeddings finales
model.eval()
with torch.no_grad():
    Z = model.encode(x, data.edge_index).cpu().numpy()

print(f"Embeddings: {Z.shape}")

# ─── 6. Lookup de semillas por nombre parcial ──────────────────────────────────
def find_component_ids(name_query: str) -> list[str]:
    """Retorna component_ids cuyo canonical_name contiene name_query (case-insensitive)."""
    mask = master["canonical_name"].str.contains(name_query, case=False, na=False)
    ids = master.loc[mask, "component_id"].tolist()
    # Preferir exactos primero
    exact_mask = master["canonical_name"].str.lower() == name_query.lower()
    exact_ids = master.loc[exact_mask, "component_id"].tolist()
    return exact_ids if exact_ids else ids


def get_seed_ids(conditions: list[str]) -> dict[str, list[str]]:
    """Para cada condición retorna dict {seed_name: [component_ids]}."""
    result = {}
    for cond in conditions:
        seeds = CONDITION_SEEDS.get(cond, [])
        for seed in seeds:
            if seed not in result:
                ids = find_component_ids(seed)
                if ids:
                    result[seed] = ids
    return result


# ─── 7. Función principal de recomendación ────────────────────────────────────
def recomendar_suplementos(
    conditions: list[str],
    top_k: int = 6,
    min_similarity: float = 0.3,
) -> dict:
    """
    Input:
        conditions   : lista de condiciones de Modelo 1
        top_k        : máximo suplementos a recomendar por condición
        min_similarity: umbral mínimo cosine similarity con seed

    Output dict:
        recomendaciones : [{nombre, condicion, score, component_id}]
        sinergias       : [(nombre_a, nombre_b, tipo_relacion)]
        alertas         : [(nombre_a, nombre_b, 'RIESGOSA')]
        combo_seguro    : bool
    """
    if "SALUDABLE" in conditions and len(conditions) == 1:
        return {
            "recomendaciones": [],
            "sinergias": [],
            "alertas": [],
            "combo_seguro": True,
            "mensaje": "Perfil saludable. No se detectaron déficits. Mantener dieta balanceada.",
        }

    conditions = [c for c in conditions if c != "SALUDABLE"]
    seed_ids_map = get_seed_ids(conditions)

    if not seed_ids_map:
        return {"recomendaciones": [], "sinergias": [], "alertas": [],
                "combo_seguro": True, "mensaje": "Sin semillas disponibles."}

    # Aplanar todos los IDs semilla únicos
    all_seed_ids = list({cid for ids in seed_ids_map.values() for cid in ids})
    seed_name_to_cond = {}
    for cond in conditions:
        for seed in CONDITION_SEEDS.get(cond, []):
            if seed not in seed_name_to_cond:
                seed_name_to_cond[seed] = cond

    # Embeddings de semillas
    seed_valid = [sid for sid in all_seed_ids if sid in comp_to_idx]
    if not seed_valid:
        return {"recomendaciones": [], "sinergias": [], "alertas": [],
                "combo_seguro": True, "mensaje": "Semillas no encontradas en grafo."}

    seed_idxs = [comp_to_idx[sid] for sid in seed_valid]
    seed_embs  = Z[seed_idxs]                          # (n_seeds, dim)
    all_embs   = Z                                      # (N, dim)

    # Cosine similarity de cada componente contra centroide de semillas
    centroid   = seed_embs.mean(axis=0, keepdims=True)  # (1, dim)
    norms_all  = np.linalg.norm(all_embs, axis=1, keepdims=True) + 1e-8
    norm_cent  = np.linalg.norm(centroid) + 1e-8
    cos_sim    = (all_embs @ centroid.T).squeeze() / (norms_all.squeeze() * norm_cent)

    # Excluir las propias semillas del ranking
    seed_idx_set = set(seed_idxs)
    candidate_mask = np.ones(len(all_embs), dtype=bool)
    candidate_mask[list(seed_idx_set)] = False

    # Ordenar candidatos por similitud
    ranked = np.argsort(-cos_sim)
    ranked = [i for i in ranked if candidate_mask[i] and cos_sim[i] >= min_similarity]

    # Construir recomendaciones
    recomendaciones = []

    # Primero agregar semillas directas (siempre recomendadas)
    for seed_name, ids in seed_ids_map.items():
        if ids:
            cid = ids[0]  # tomar el primero (más exacto)
            cond_for_seed = seed_name_to_cond.get(seed_name, "multiple")
            recomendaciones.append({
                "nombre": comp_to_name.get(cid, seed_name),
                "condicion": cond_for_seed,
                "score": 1.0,
                "component_id": cid,
                "tipo": "semilla_directa",
            })

    # Luego agregar candidatos similares con SOPORTE_FUNCIONAL hacia alguna semilla
    added_ids = {r["component_id"] for r in recomendaciones}
    extras_added = 0

    for cand_idx in ranked:
        if extras_added >= 3:
            break
        cand_id = idx_to_comp[cand_idx]
        if cand_id in added_ids:
            continue
        # Verificar que tiene SOPORTE_FUNCIONAL con al menos una semilla
        has_support = any(
            (cand_id, sid) in functional_pairs or (sid, cand_id) in functional_pairs
            for sid in seed_valid
        )
        if has_support:
            recomendaciones.append({
                "nombre": comp_to_name.get(cand_id, cand_id),
                "condicion": "soporte_funcional",
                "score": float(cos_sim[cand_idx]),
                "component_id": cand_id,
                "tipo": "candidato_gnn",
            })
            added_ids.add(cand_id)
            extras_added += 1

    # Deduplicar por component_id
    seen = set()
    recomendaciones_dedup = []
    for r in recomendaciones:
        if r["component_id"] not in seen:
            seen.add(r["component_id"])
            recomendaciones_dedup.append(r)

    # ─── Sinergias entre recomendados ─────────────────────────────────────────
    sinergias = []
    rec_ids = [r["component_id"] for r in recomendaciones_dedup]
    for i in range(len(rec_ids)):
        for j in range(i + 1, len(rec_ids)):
            a, b = rec_ids[i], rec_ids[j]
            if (a, b) in functional_pairs:
                rel = edges_df[
                    ((edges_df["component_id_a"] == a) & (edges_df["component_id_b"] == b)) |
                    ((edges_df["component_id_a"] == b) & (edges_df["component_id_b"] == a))
                ]["relationship_subclass"].values
                rel_str = rel[0] if len(rel) > 0 else "soporte_funcional"
                sinergias.append((
                    comp_to_name.get(a, a),
                    comp_to_name.get(b, b),
                    rel_str,
                ))

    # ─── Alertas: pares riesgosos dentro del combo ────────────────────────────
    alertas = []
    for i in range(len(rec_ids)):
        for j in range(i + 1, len(rec_ids)):
            a, b = rec_ids[i], rec_ids[j]
            if (a, b) in risky_pairs:
                alertas.append((
                    comp_to_name.get(a, a),
                    comp_to_name.get(b, b),
                    "INTERACCION_RIESGOSA",
                ))

    combo_seguro = len(alertas) == 0

    return {
        "recomendaciones": recomendaciones_dedup,
        "sinergias": sinergias,
        "alertas": alertas,
        "combo_seguro": combo_seguro,
        "mensaje": "OK" if combo_seguro else f"{len(alertas)} interacción(es) riesgosa(s) detectada(s).",
    }


# ─── 8. Guardar artefactos para inferencia ────────────────────────────────────
ARTIFACTS_PATH = f"{DATA_DIR}/modelo2_artifacts.pkl"
joblib.dump({
    "model_state": model.state_dict(),
    "embeddings": Z,
    "comp_to_idx": comp_to_idx,
    "idx_to_comp": idx_to_comp,
    "comp_to_name": comp_to_name,
    "risky_pairs": risky_pairs,
    "functional_pairs": functional_pairs,
    "feature_cols": FEATURE_COLS,
    "scaler": scaler,
    "condition_seeds": CONDITION_SEEDS,
}, ARTIFACTS_PATH)
print(f"\nArtefactos guardados: {ARTIFACTS_PATH}")


# ─── 9. Demo ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "="*60)
    print("DEMO — Integración Modelo 1 → Modelo 2")
    print("="*60)

    casos = [
        {
            "descripcion": "Vegana, baja exposición solar, fatiga alta, caída cabello",
            "condiciones": ["DEFICIT_VIT_D", "DEFICIT_B12", "DEFICIT_HIERRO", "SALUD_CAPILAR_PIEL"],
        },
        {
            "descripcion": "Atleta con calambres, mal sueño, meta rendimiento",
            "condiciones": ["DEFICIT_MAGNESIO", "RENDIMIENTO_DEPORTIVO"],
        },
        {
            "descripcion": "Persona saludable",
            "condiciones": ["SALUDABLE"],
        },
    ]

    for caso in casos:
        print(f"\n── Usuario: {caso['descripcion']}")
        print(f"   Condiciones (Modelo 1): {caso['condiciones']}")
        result = recomendar_suplementos(caso["condiciones"])

        print(f"\n   Recomendaciones ({len(result['recomendaciones'])}):")
        for r in result["recomendaciones"]:
            tipo = "★" if r["tipo"] == "semilla_directa" else "◆"
            print(f"     {tipo} {r['nombre']:<40} | cond: {r['condicion']}")

        if result["sinergias"]:
            print(f"\n   Sinergias detectadas ({len(result['sinergias'])}):")
            for s in result["sinergias"][:5]:
                print(f"     ✓ {s[0]} ↔ {s[1]}  [{s[2]}]")

        if result["alertas"]:
            print(f"\n   ⚠ ALERTAS ({len(result['alertas'])}):")
            for a in result["alertas"]:
                print(f"     ✗ {a[0]} + {a[1]}  [{a[2]}]")

        print(f"\n   Combo seguro: {'Sí' if result['combo_seguro'] else 'NO'}")
        print(f"   Mensaje: {result['mensaje']}")
