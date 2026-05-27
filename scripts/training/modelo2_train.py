"""
Modelo 2 — ENTRENAMIENTO (ejecutar una sola vez)
Guarda: modelo2_artifacts.pkl
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

DATA_DIR = "/Users/joaquinsalazar/Desktop/DPD/MODELO"
ARTIFACTS_PATH = f"{DATA_DIR}/modelo2_artifacts.pkl"
SEED = 42
torch.manual_seed(SEED)
np.random.seed(SEED)
device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")

CONDITION_SEEDS = {
    "DEFICIT_VIT_D":        ["Vitamin D", "Calcium", "Vitamin K", "Magnesium"],
    "DEFICIT_B12":          ["Vitamin B12", "Folic Acid", "Folate", "Vitamin B6"],
    "DEFICIT_HIERRO":       ["Iron", "Vitamin C"],
    "DEFICIT_MAGNESIO":     ["Magnesium", "Vitamin D", "Zinc", "Vitamin B6"],
    "BAJA_INMUNIDAD":       ["Vitamin C", "Zinc", "Selenium", "Vitamin D"],
    "RENDIMIENTO_DEPORTIVO":["Carnitine", "Omega-3", "Magnesium", "Vitamin B12", "Zinc"],
    "SALUD_CAPILAR_PIEL":   ["Biotin", "collagen", "Vitamin E", "Zinc", "Selenium"],
    "FATIGA_CRONICA":       ["Vitamin B12", "Iron", "Magnesium", "Ashwagandha", "Vitamin C"],
    "SALUDABLE":            [],
}

USEFUL_CLASSES = {
    "SOPORTE_FUNCIONAL", "INTERACCION_VALIDADA", "BENEFICIOSA",
    "SOPORTE_METABOLICO", "COFACTOR_FUNCIONAL", "SOPORTE_ANTIOXIDANTE",
    "INEFICAZ", "ANULACION",
}

FEATURE_COLS = [
    "source_count", "has_regulatory_signal", "has_safety_signal",
    "regulatory_signal_count", "safety_signal_count",
    "total_ensayos_clinicos", "ensayos_completados",
    "tasa_no_completado", "tasa_riesgo_toxicidad",
    "interaction_degree_drugbank",
]


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


def train():
    print("Cargando datos...")
    master   = pd.read_csv(f"{DATA_DIR}/Component_Master_Clean.csv")
    edges_df = pd.read_csv(f"{DATA_DIR}/Component_Relationship_Edges_Clean.csv")

    edges_clean = edges_df[edges_df["relationship_class"].isin(USEFUL_CLASSES)].copy()

    risky_pairs = set()
    for _, r in edges_df[edges_df["relationship_class"] == "RIESGOSA"].iterrows():
        risky_pairs.add((r["component_id_a"], r["component_id_b"]))
        risky_pairs.add((r["component_id_b"], r["component_id_a"]))

    functional_pairs = set()
    for _, r in edges_df[edges_df["relationship_class"] == "SOPORTE_FUNCIONAL"].iterrows():
        functional_pairs.add((r["component_id_a"], r["component_id_b"]))
        functional_pairs.add((r["component_id_b"], r["component_id_a"]))

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

    valid_edges = edges_clean[
        edges_clean["component_id_a"].isin(comp_to_idx) &
        edges_clean["component_id_b"].isin(comp_to_idx)
    ]
    src = [comp_to_idx[c] for c in valid_edges["component_id_a"]]
    dst = [comp_to_idx[c] for c in valid_edges["component_id_b"]]
    edge_index = torch.tensor([src + dst, dst + src], dtype=torch.long).to(device)
    data = Data(x=x, edge_index=edge_index, num_nodes=x.shape[0])

    perm = torch.randperm(len(src))
    n_train = int(0.7 * len(src))
    train_src = torch.tensor(src)[perm[:n_train]]
    train_dst = torch.tensor(dst)[perm[:n_train]]
    train_edge_index = torch.stack([train_src, train_dst]).to(device)

    model = GraphSAGE(in_ch=len(FEATURE_COLS), hidden_ch=64, out_ch=32).to(device)
    opt   = torch.optim.Adam(model.parameters(), lr=0.005, weight_decay=1e-4)

    print(f"Entrenando GraphSAGE en {device}...")
    best_loss = float("inf")
    patience_count = 0
    PATIENCE = 15
    for epoch in range(300):
        model.train()
        opt.zero_grad()
        neg = negative_sampling(edge_index=data.edge_index,
                                num_nodes=x.shape[0],
                                num_neg_samples=train_edge_index.shape[1]).to(device)
        z = model.encode(x, train_edge_index)
        pos_s = model.decode(z, train_edge_index)
        neg_s = model.decode(z, neg)
        loss = F.binary_cross_entropy_with_logits(
            torch.cat([pos_s, neg_s]),
            torch.cat([torch.ones(pos_s.size(0)),
                       torch.zeros(neg_s.size(0))]).to(device)
        )
        loss.backward()
        opt.step()
        loss_val = loss.item()
        if (epoch + 1) % 20 == 0:
            print(f"  Epoch {epoch+1:3d} | Loss: {loss_val:.4f}")
        # Early stopping
        if loss_val < best_loss - 1e-4:
            best_loss = loss_val
            patience_count = 0
        else:
            patience_count += 1
        if patience_count >= PATIENCE:
            print(f"  Early stop en epoch {epoch+1} | Best loss: {best_loss:.4f}")
            break

    model.eval()
    with torch.no_grad():
        Z = model.encode(x, data.edge_index).cpu().numpy()

    joblib.dump({
        "model_state":     model.state_dict(),
        "embeddings":      Z,
        "comp_to_idx":     comp_to_idx,
        "idx_to_comp":     idx_to_comp,
        "comp_to_name":    comp_to_name,
        "risky_pairs":     risky_pairs,
        "functional_pairs": functional_pairs,
        "feature_cols":    FEATURE_COLS,
        "scaler":          scaler,
        "condition_seeds": CONDITION_SEEDS,
        "master_names":    master[["component_id", "canonical_name"]].copy(),
        "edges_df_subset": edges_df[["component_id_a", "component_id_b",
                                      "relationship_class", "relationship_subclass"]].copy(),
    }, ARTIFACTS_PATH)

    print(f"Artefactos guardados: {ARTIFACTS_PATH}")
    print(f"Embeddings: {Z.shape}  |  Pares riesgosos: {len(risky_pairs)//2}")


if __name__ == "__main__":
    train()
