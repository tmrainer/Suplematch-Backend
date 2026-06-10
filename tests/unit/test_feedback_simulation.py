"""
Pruebas de simulación: verifican que el reranker cambia el orden de packs
cuando muchos usuarios dan feedback positivo o negativo.

Se usan 6 componentes para que el reranker genere múltiples packs en competencia
(combinaciones de 3). El feedback simulado es sintético — no requiere base de
datos ni modelos entrenados.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from app.ml.runtime import feedback_store
from app.ml.runtime.feedback_reranker import rerank_packs


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _six_components():
    """6 componentes → el reranker genera hasta C(6,3)=20 packs, capeado en 10."""
    return [
        {"component_id": "cmp_vit_d",     "nombre": "Vitamin D",   "condicion": "DEFICIT_VIT_D",   "score": 0.72},
        {"component_id": "cmp_calcium",   "nombre": "Calcium",     "condicion": "DEFICIT_CALCIO",  "score": 0.71},
        {"component_id": "cmp_magnesium", "nombre": "Magnesium",   "condicion": "ESTRES_CRONICO",  "score": 0.68},
        {"component_id": "cmp_zinc",      "nombre": "Zinc",        "condicion": "BAJO_INMUNE",     "score": 0.65},
        {"component_id": "cmp_omega3",    "nombre": "Omega-3",     "condicion": "COLESTEROL_ALTO", "score": 0.63},
        {"component_id": "cmp_iron",      "nombre": "Iron",        "condicion": "DEFICIT_HIERRO",  "score": 0.60},
    ]


def _with_temp_store(callback):
    original_rec  = feedback_store.RECOMMENDATION_EVENTS_PATH
    original_fb   = feedback_store.USER_FEEDBACK_EVENTS_PATH
    original_db   = feedback_store.FEEDBACK_DB_PATH

    with TemporaryDirectory() as tmp:
        p = Path(tmp)
        feedback_store.RECOMMENDATION_EVENTS_PATH = p / "recommendation_events.json"
        feedback_store.USER_FEEDBACK_EVENTS_PATH  = p / "user_feedback_events.json"
        feedback_store.FEEDBACK_DB_PATH           = p / "feedback.sqlite3"
        try:
            callback()
        finally:
            feedback_store.RECOMMENDATION_EVENTS_PATH = original_rec
            feedback_store.USER_FEEDBACK_EVENTS_PATH  = original_fb
            feedback_store.FEEDBACK_DB_PATH           = original_db


def _simulate_votes(pack_id: str, component_ids: list[str], rating: int, n: int) -> None:
    for i in range(n):
        feedback_store.save_feedback_event(
            recommendation_id=f"rec_sim_{pack_id}_{i}",
            pack_id=pack_id,
            component_ids=component_ids,
            rating_overall=rating,
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_popular_pack_rises_to_rank_1():
    """
    Un pack que comienza en posición baja sube al rank 1 cuando muchos
    usuarios lo valoran con 5 estrellas.
    """
    def run():
        conditions = ["DEFICIT_VIT_D", "DEFICIT_CALCIO", "ESTRES_CRONICO",
                      "BAJO_INMUNE", "COLESTEROL_ALTO", "DEFICIT_HIERRO"]
        baseline = rerank_packs(_six_components(), conditions)

        # El último pack del ranking (peor score inicial)
        target = baseline[-1]
        assert target["rank"] == len(baseline)

        # 20 usuarios lo votan con 5 estrellas
        _simulate_votes(target["pack_id"], target["component_ids"], rating=5, n=20)

        updated = rerank_packs(_six_components(), conditions)
        new_rank = next(p["rank"] for p in updated if p["pack_id"] == target["pack_id"])

        assert new_rank == 1, (
            f"El pack {target['pack_id']} debería ser rank 1 tras 20 votos positivos, "
            f"pero quedó en rank {new_rank}"
        )

    _with_temp_store(run)


def test_negative_feedback_drops_top_pack():
    """
    El pack que inicia en rank 1 cae de posición cuando acumula votos negativos
    consistentes mientras los demás packs permanecen sin feedback.
    """
    def run():
        conditions = ["DEFICIT_VIT_D", "DEFICIT_CALCIO", "BAJO_INMUNE"]
        baseline = rerank_packs(_six_components(), conditions)

        top = baseline[0]
        assert top["rank"] == 1

        # 15 usuarios lo votan con 1 estrella
        _simulate_votes(top["pack_id"], top["component_ids"], rating=1, n=15)

        updated = rerank_packs(_six_components(), conditions)
        new_rank = next(p["rank"] for p in updated if p["pack_id"] == top["pack_id"])

        assert new_rank > 1, (
            f"El pack {top['pack_id']} debería bajar del rank 1 tras 15 votos negativos, "
            f"pero sigue en rank {new_rank}"
        )

    _with_temp_store(run)


def test_competing_packs_winner_determined_by_votes():
    """
    Dos packs compiten. Pack A recibe 15 votos de 5 estrellas,
    Pack B recibe 15 votos de 1 estrella. Al final Pack A debe superar a Pack B.
    """
    def run():
        conditions = ["DEFICIT_VIT_D", "DEFICIT_CALCIO", "BAJO_INMUNE"]
        baseline = rerank_packs(_six_components(), conditions)

        # Tomamos el primer y último pack como competidores
        pack_a = baseline[0]
        pack_b = baseline[-1]

        _simulate_votes(pack_a["pack_id"], pack_a["component_ids"], rating=5, n=15)
        _simulate_votes(pack_b["pack_id"], pack_b["component_ids"], rating=1, n=15)

        updated = rerank_packs(_six_components(), conditions)
        rank_a = next(p["rank"] for p in updated if p["pack_id"] == pack_a["pack_id"])
        rank_b = next(p["rank"] for p in updated if p["pack_id"] == pack_b["pack_id"])
        score_a = next(p["score_final"] for p in updated if p["pack_id"] == pack_a["pack_id"])
        score_b = next(p["score_final"] for p in updated if p["pack_id"] == pack_b["pack_id"])

        assert rank_a < rank_b, (
            f"Pack A (votos positivos) debería tener rank < Pack B (votos negativos). "
            f"Obtenido: rank_a={rank_a}, rank_b={rank_b}"
        )
        assert score_a > score_b, (
            f"Pack A debería tener score_final > Pack B. "
            f"Obtenido: score_a={score_a:.4f}, score_b={score_b:.4f}"
        )

    _with_temp_store(run)


def test_bayesian_smoothing_single_vote_does_not_fully_override():
    """
    Un único voto de 5 estrellas no debe disparar el score al máximo.
    El prior bayesiano (GLOBAL_PRIOR=0.70, BAYES_M=8) amortigua votos aislados.
    Con n=1, el peso del voto es 1/(1+8) ≈ 11 %, por lo que el score debe
    quedar entre el prior y 1.0 sin llegar a ninguno de los dos extremos.
    """
    def run():
        conditions = ["DEFICIT_VIT_D", "DEFICIT_CALCIO"]
        baseline = rerank_packs(_six_components(), conditions)
        pack = baseline[0]

        prior_score = pack["score_feedback"]  # debería ser GLOBAL_PRIOR = 0.70

        feedback_store.save_feedback_event(
            recommendation_id="rec_single",
            pack_id=pack["pack_id"],
            component_ids=pack["component_ids"],
            rating_overall=5,
        )

        updated_pack = next(
            p for p in rerank_packs(_six_components(), conditions)
            if p["pack_id"] == pack["pack_id"]
        )

        assert updated_pack["score_feedback"] > prior_score, "Un voto 5★ debe subir el score_feedback"
        assert updated_pack["score_feedback"] < 1.0, "Un único voto no debe llevar el score a 1.0"
        assert updated_pack["feedback_count"] == 1

    _with_temp_store(run)


def test_more_votes_same_rating_increases_confidence():
    """
    A igual rating promedio (5★), más votos deben producir un score_feedback
    mayor, porque el prior bayesiano pierde peso conforme n crece.
    """
    def run():
        conditions = ["DEFICIT_VIT_D", "DEFICIT_CALCIO"]
        packs = rerank_packs(_six_components(), conditions)
        pack = packs[0]

        _simulate_votes(pack["pack_id"], pack["component_ids"], rating=5, n=5)
        after_5 = next(
            p for p in rerank_packs(_six_components(), conditions)
            if p["pack_id"] == pack["pack_id"]
        )

        _simulate_votes(pack["pack_id"], pack["component_ids"], rating=5, n=15)
        after_20 = next(
            p for p in rerank_packs(_six_components(), conditions)
            if p["pack_id"] == pack["pack_id"]
        )

        assert after_20["score_feedback"] > after_5["score_feedback"], (
            f"20 votos 5★ deben dar mayor score_feedback que 5 votos 5★. "
            f"5 votos: {after_5['score_feedback']:.4f}, "
            f"20 votos: {after_20['score_feedback']:.4f}"
        )
        assert after_20["feedback_count"] == 20

    _with_temp_store(run)


def test_mixed_feedback_averages_correctly():
    """
    Feedback mixto (mitad 5★, mitad 1★) debe producir un score_feedback
    cercano al prior bayesiano (0.70), no claramente mejor ni peor.
    """
    def run():
        conditions = ["DEFICIT_VIT_D", "DEFICIT_CALCIO"]
        packs = rerank_packs(_six_components(), conditions)
        pack = packs[0]

        _simulate_votes(pack["pack_id"], pack["component_ids"], rating=5, n=10)
        _simulate_votes(pack["pack_id"], pack["component_ids"], rating=1, n=10)

        mixed_pack = next(
            p for p in rerank_packs(_six_components(), conditions)
            if p["pack_id"] == pack["pack_id"]
        )

        assert mixed_pack["feedback_count"] == 20
        # Rating promedio ≈ 3 → score ≈ 0.5; mezclado con prior 0.70 → ~0.58
        assert 0.50 <= mixed_pack["score_feedback"] <= 0.72, (
            f"Score con feedback mixto debería estar entre 0.50 y 0.72, "
            f"obtenido: {mixed_pack['score_feedback']:.4f}"
        )

    _with_temp_store(run)
