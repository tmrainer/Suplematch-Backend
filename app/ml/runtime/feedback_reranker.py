from __future__ import annotations

import hashlib
import itertools
import math
from typing import Any

from app.ml.runtime.feedback_store import get_feedback_stats_by_pack


GLOBAL_PRIOR = 0.70
BAYES_M = 8
GNN_WEIGHT = 0.45
COVERAGE_WEIGHT = 0.25
FEEDBACK_WEIGHT = 0.30
UCB_WEIGHT = 0.01


def _pack_key(component_ids: list[str]) -> str:
    clean = sorted(str(cid) for cid in component_ids if cid)
    raw = "|".join(clean)
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]
    return f"pack_{digest}"


def _bayesian_score(pack_id: str, stats: dict[str, dict[str, Any]]) -> tuple[float, int]:
    item = stats.get(pack_id)

    if not item:
        return GLOBAL_PRIOR, 0

    n = int(item["n"])
    avg = float(item.get("avg_score", GLOBAL_PRIOR))

    score = ((n / (n + BAYES_M)) * avg) + ((BAYES_M / (n + BAYES_M)) * GLOBAL_PRIOR)
    return float(score), n


def _make_candidate_packs(recomendaciones: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if not recomendaciones:
        return []

    recs = []
    seen = set()

    for rec in recomendaciones:
        cid = str(rec.get("component_id", "")).strip()
        if not cid or cid in seen:
            continue

        seen.add(cid)
        recs.append(rec)

    recs = recs[:6]

    if len(recs) <= 3:
        return [recs]

    packs = []

    for combo in itertools.combinations(recs, 3):
        packs.append(list(combo))

    return packs[:10]


def rerank_packs(
    recomendaciones: list[dict[str, Any]],
    conditions: list[str],
    alertas: list[Any] | None = None,
) -> list[dict[str, Any]]:
    candidate_packs = _make_candidate_packs(recomendaciones)

    if not candidate_packs:
        return []

    stats = get_feedback_stats_by_pack()
    total_feedback = sum(int(v["n"]) for v in stats.values()) or 1

    ranked = []

    for pack in candidate_packs:
        component_ids = [str(r.get("component_id")) for r in pack if r.get("component_id")]
        component_names = [str(r.get("nombre", r.get("name", cid))) for r, cid in zip(pack, component_ids)]

        pack_id = _pack_key(component_ids)

        raw_scores = []
        covered_conditions = set()

        for rec in pack:
            raw_scores.append(float(rec.get("score", rec.get("score_gnn", 0.7)) or 0.7))

            cond = rec.get("condicion")
            if cond and cond != "soporte_funcional":
                covered_conditions.add(str(cond))

        score_gnn = sum(raw_scores) / max(len(raw_scores), 1)

        useful_conditions = [c for c in conditions if c != "SALUDABLE"]
        if useful_conditions:
            score_coverage = len(covered_conditions.intersection(useful_conditions)) / len(useful_conditions)
        else:
            score_coverage = 1.0

        score_feedback, n_feedback = _bayesian_score(pack_id, stats)

        ucb_bonus = UCB_WEIGHT * math.sqrt(
            math.log(total_feedback + 1) / (n_feedback + 1)
        )

        score_final = (
            GNN_WEIGHT * score_gnn
            + COVERAGE_WEIGHT * score_coverage
            + FEEDBACK_WEIGHT * score_feedback
            + ucb_bonus
        )

        ranked.append({
            "pack_id": pack_id,
            "component_ids": component_ids,
            "component_names": component_names,
            "rank": 0,
            "score_final": float(score_final),
            "score_gnn": float(score_gnn),
            "score_coverage": float(score_coverage),
            "score_feedback": float(score_feedback),
            "feedback_count": n_feedback,
        })

    ranked.sort(key=lambda x: x["score_final"], reverse=True)

    for idx, pack in enumerate(ranked, start=1):
        pack["rank"] = idx

    return ranked
