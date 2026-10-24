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

import os
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

# Directorio con Component_Master_Clean.csv y Component_Relationship_Edges_Clean.csv.
# Configurable por entorno; por defecto data/training/supplement_model dentro del repo.
DATA_DIR = os.environ.get(
    "SUPPLEMENT_MODEL_DATA_DIR",
    str(Path(__file__).resolve().parents[2] / "data" / "training" / "supplement_model"),
)
ARTIFACTS_PATH = os.environ.get(
    "MODEL2_ARTIFACTS_PATH",
    str(Path(__file__).resolve().parents[2] / "models" / "runtime" / "modelo2_artifacts.pkl"),
)
MODEL_CARD_PATH = Path(ARTIFACTS_PATH).with_name("modelo2_model_card.json")
MODEL2_VERSION = "graphsage_link_v3_2026-10-23"


def _sha256_16(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


MODEL_CARD_LIMITATIONS = [
    "Las aristas provienen de fuentes estructuradas (DrugBank, AACT/ClinicalTrials, NIH ODS): el GNN aprende a "
    "reproducir ese grafo. AUC alto en aristas reservadas NO demuestra utilidad de recomendacion para usuarios; "
    "eso requiere feedback real (plan de fiabilidad, Fase 5).",
    "Solo aporta candidatos complementarios (`candidato_gnn`, score = similitud coseno x 0.45) filtrados por "
    "`functional_pairs`; las recomendaciones principales salen de condition_component_links.csv con fuentes.",
    "Las sinergias (`functional_pairs`) heredan la fuente del grafo pero no tienen source_ids clinicos propios.",
    "Varios nodos del grafo representan el mismo componente (p. ej. 'Vitamin D', 'Vitamin D (cholecalciferol)'); "
    "data/knowledge/gnn_node_equivalences.csv los colapsa al id canonico en inferencia.",
    "Split 70/15/15 de aristas con negativos muestreados al azar: los negativos faciles inflan AUC/AP frente a un "
    "escenario real de ranking.",
]


def write_model_card(artifacts_path, link_metrics: dict, master, edges_df, edges_clean, data_dir) -> Path:
    """Model card del artefacto GNN: hash, datos, metricas en aristas reservadas y limitaciones (Fase 4)."""
    card = {
        "model": "modelo2_artifacts",
        "version": MODEL2_VERSION,
        "sha256_16": _sha256_16(artifacts_path),
        "task": "Embeddings de componentes (GraphSAGE, link prediction) para proponer candidatos complementarios al ranker de reglas.",
        "data": {
            "master": {"path": f"{data_dir}/Component_Master_Clean.csv", "sha256_16": _sha256_16(f"{data_dir}/Component_Master_Clean.csv"), "nodes": int(len(master))},
            "edges": {
                "path": f"{data_dir}/Component_Relationship_Edges_Clean.csv",
                "sha256_16": _sha256_16(f"{data_dir}/Component_Relationship_Edges_Clean.csv"),
                "rows": int(len(edges_df)),
                "used_for_training": int(len(edges_clean)),
                "by_class": {str(k): int(v) for k, v in edges_df["relationship_class"].value_counts().items()},
                "useful_classes": sorted(USEFUL_CLASSES),
            },
            "node_features": FEATURE_COLS,
        },
        "algorithm": (
            f"GraphSAGE 2 capas (64 -> 32), decoder producto punto, Adam lr=0.005 wd=1e-4, negativos muestreados, "
            f"early stop por ROC-AUC de validacion (paciencia {PATIENCE}, max {MAX_EPOCHS} epochs, se restaura el mejor epoch), seed {SEED}"
        ),
        "split": "70 % aristas para entrenar / 15 % validacion (early stop) / 15 % test (metricas); val y test fuera del grafo de mensaje",
        "metrics_held_out_edges": link_metrics,
        "acceptance_threshold": {"roc_auc_min": 0.65, "passed": bool(link_metrics["roc_auc"] >= 0.65)},
        "limitations": MODEL_CARD_LIMITATIONS,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    MODEL_CARD_PATH.write_text(json.dumps(card, indent=2, ensure_ascii=False), encoding="utf-8")
    return MODEL_CARD_PATH
SEED = 42
PATIENCE = 15
MAX_EPOCHS = 300
TRAIN_FRAC, VAL_FRAC = 0.70, 0.15
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


def link_auc_ap(model, x, message_edge_index, pos_edge_index, neg_edge_index) -> tuple[float, float]:
    """ROC-AUC y AP de link prediction: aristas positivas reservadas vs negativos dados."""
    from sklearn.metrics import average_precision_score, roc_auc_score

    model.eval()
    with torch.no_grad():
        z = model.encode(x, message_edge_index)
        pos_scores = torch.sigmoid(model.decode(z, pos_edge_index)).cpu().numpy()
        neg_scores = torch.sigmoid(model.decode(z, neg_edge_index)).cpu().numpy()
    y_true = np.concatenate([np.ones_like(pos_scores), np.zeros_like(neg_scores)])
    y_score = np.concatenate([pos_scores, neg_scores])
    return float(roc_auc_score(y_true, y_score)), float(average_precision_score(y_true, y_score))


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
    n_train = int(TRAIN_FRAC * len(src))
    n_val = int(VAL_FRAC * len(src))
    src_t, dst_t = torch.tensor(src), torch.tensor(dst)

    def _split(idx):
        return torch.stack([src_t[idx], dst_t[idx]]).to(device)

    train_edge_index = _split(perm[:n_train])
    val_edge_index = _split(perm[n_train:n_train + n_val])
    test_edge_index = _split(perm[n_train + n_val:])
    # Negativos de validacion fijos: si cambiaran cada epoch, el AUC de val tendria ruido de muestreo y el
    # early stop reaccionaria a ese ruido en vez de a la generalizacion.
    val_neg = negative_sampling(edge_index=data.edge_index, num_nodes=x.shape[0],
                                num_neg_samples=val_edge_index.shape[1]).to(device)

    model = GraphSAGE(in_ch=len(FEATURE_COLS), hidden_ch=64, out_ch=32).to(device)
    opt   = torch.optim.Adam(model.parameters(), lr=0.005, weight_decay=1e-4)

    print(f"Entrenando GraphSAGE en {device}...")
    # Early stop por ROC-AUC en aristas de validacion. Antes se paraba por loss de entrenamiento, que sigue
    # bajando mientras el modelo memoriza el grafo de entrenamiento; el AUC de val mide generalizacion.
    best_val_auc = -1.0
    best_epoch = 0
    best_state = None
    best_loss = float("inf")
    patience_count = 0
    epochs_run = 0
    for epoch in range(MAX_EPOCHS):
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
        epochs_run = epoch + 1
        best_loss = min(best_loss, loss_val)

        val_auc, _ = link_auc_ap(model, x, train_edge_index, val_edge_index, val_neg)
        if (epoch + 1) % 20 == 0:
            print(f"  Epoch {epoch+1:3d} | Loss: {loss_val:.4f} | Val AUC: {val_auc:.4f}")
        if val_auc > best_val_auc + 1e-4:
            best_val_auc = val_auc
            best_epoch = epoch + 1
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
            patience_count = 0
        else:
            patience_count += 1
        if patience_count >= PATIENCE:
            print(f"  Early stop en epoch {epoch+1} | Mejor val AUC {best_val_auc:.4f} en epoch {best_epoch}")
            break

    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    # Evaluacion en aristas de test (15 %, nunca usadas para entrenar ni para elegir el epoch). Si AUC o AP no
    # superan claramente 0.5, el GNN no aporta sobre el ranker de reglas y debe eliminarse (plan, Fase 4).
    test_neg = negative_sampling(edge_index=data.edge_index, num_nodes=x.shape[0],
                                 num_neg_samples=test_edge_index.shape[1]).to(device)
    test_auc, test_ap = link_auc_ap(model, x, train_edge_index, test_edge_index, test_neg)
    link_metrics = {
        "test_edges": int(test_edge_index.shape[1]),
        "val_edges": int(val_edge_index.shape[1]),
        "train_edges": int(train_edge_index.shape[1]),
        "roc_auc": test_auc,
        "average_precision": test_ap,
        "best_val_roc_auc": float(best_val_auc),
        "best_epoch": int(best_epoch),
        "epochs_run": int(epochs_run),
        "best_train_loss": float(best_loss),
        "seed": SEED,
    }
    print(f"Link prediction (held-out): AUC={link_metrics['roc_auc']:.3f}  AP={link_metrics['average_precision']:.3f}")
    if link_metrics["roc_auc"] < 0.65:
        print("ADVERTENCIA: AUC < 0.65; el GNN no discrimina aristas mejor que el azar de forma util. Considerar eliminarlo.")

    with torch.no_grad():
        Z = model.encode(x, data.edge_index).cpu().numpy()

    joblib.dump({
        "model_state":     model.state_dict(),
        "model_version":   MODEL2_VERSION,
        "trained_at":      datetime.now(timezone.utc).isoformat(),
        "link_prediction_metrics": link_metrics,
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
    card_path = write_model_card(ARTIFACTS_PATH, link_metrics, master, edges_df, edges_clean, DATA_DIR)
    print(f"Model card: {card_path}")
    print(f"Embeddings: {Z.shape}  |  Pares riesgosos: {len(risky_pairs)//2}")


if __name__ == "__main__":
    train()
