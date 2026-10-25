"""Precision real del sistema: lo que la encuesta estima contra lo que el examen de laboratorio confirma.

Cada par es (encuesta de una persona, examen de esa misma persona). La prediccion se calcula con la encuesta **sin**
los examenes, para medir lo que importa: que tan bien acierta el sistema con alguien que no tiene examenes. La verdad
es el examen fuera de rango segun `biomarkers.csv` (TRUTH_BIOMARKERS). Se comparan tres variantes:

- ``sistema``: lo que se sirve hoy (Modelo 1 + reglas + segunda opinion NHANES).
- ``reglas``: solo reglas (puntaje >= umbral y dos familias) + segunda opinion NHANES; la alternativa a jubilar el
  Modelo 1 sintetico.
- ``nhanes``: solo el modelo real NHANES, para las condiciones que estima.

Solo produce agregados (conteos y metricas por condicion), dentro de la finalidad "metricas agregadas" del aviso
de privacidad. Entrenar con estos pares es otra finalidad y necesita consentimiento aparte.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

LOW = frozenset({"low", "critical_low"})
HIGH = frozenset({"high", "critical_high"})
ABNORMAL = LOW | HIGH

# Condicion -> examenes que la confirman y en que direccion. Solo condiciones que un examen define; las de bienestar
# (sueño, energia) o las que un examen solo sugiere (zinc para defensas) no se evaluan. Calcio y magnesio en sangre
# quedan fuera: el cuerpo los mantiene estables aunque la ingesta sea baja y no reflejan el deficit (NIH ODS).
TRUTH_BIOMARKERS: dict[str, tuple[tuple[str, frozenset[str]], ...]] = {
    "DEFICIT_VIT_D": (("vitamin_d", LOW),),
    "DEFICIT_B12": (("b12", LOW),),
    "DEFICIT_HIERRO": (("ferritin", LOW), ("hemoglobin", LOW)),
    "DEFICIT_FOLATO": (("folate", LOW),),
    "DEFICIT_ZINC": (("zinc", LOW),),
    "RIESGO_METABOLICO_GLUCOSA": (("hba1c", HIGH), ("glucose", HIGH)),
    "RIESGO_DISLIPIDEMIA": (("total_cholesterol", HIGH), ("ldl", HIGH), ("triglycerides", HIGH), ("hdl", LOW)),
    "SAFETY_RENAL": (("creatinine", HIGH), ("egfr", LOW)),
    "SAFETY_HEPATICA": (("alt", HIGH), ("ast", HIGH)),
    "SAFETY_TIROIDEA": (("tsh", ABNORMAL),),
}
PREDICTORS = ("sistema", "reglas", "nhanes")
# Con menos casos marcados (o menos positivos reales) la metrica se reporta pero se marca como insuficiente.
MIN_CASES_FOR_METRIC = 10
WILSON_Z = 1.96


def lab_truth(statuses: dict[str, str]) -> dict[str, bool]:
    """Condiciones evaluables con estos examenes (`codigo -> status`) y si el examen las confirma.

    Una condicion es evaluable si se midio al menos uno de sus examenes; es positiva si alguno medido esta fuera
    de rango en la direccion de la condicion.
    """
    truth: dict[str, bool] = {}
    for condition, biomarkers in TRUTH_BIOMARKERS.items():
        measured = [(statuses[code], direction) for code, direction in biomarkers if code in statuses]
        if measured:
            truth[condition] = any(status in direction for status, direction in measured)
    return truth


def predicted_conditions(condition_details: list[dict[str, Any]], lab_risks: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Condiciones marcadas por cada variante a partir del detalle del Modelo 1 y de las estimaciones NHANES."""
    sistema = {item["condition"] for item in condition_details if item.get("positive")}
    reglas = {
        item["condition"]
        for item in condition_details
        if item.get("second_opinion_reason")
        or (
            item.get("corroborated")
            and not item.get("suppressed_by_supplement")
            and float(item.get("rule_score") or 0.0) >= float(item.get("rule_threshold") or math.inf)
        )
    }
    nhanes = {item["condition"] for item in lab_risks if item.get("positive") and item.get("condition")}
    return {"sistema": sistema, "reglas": reglas, "nhanes": nhanes}


def wilson_interval(successes: int, total: int, z: float = WILSON_Z) -> tuple[float, float] | None:
    if total <= 0:
        return None
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return round(max(0.0, center - half), 4), round(min(1.0, center + half), 4)


@dataclass
class Confusion:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    def add(self, predicted: bool, actual: bool) -> None:
        if predicted and actual:
            self.tp += 1
        elif predicted:
            self.fp += 1
        elif actual:
            self.fn += 1
        else:
            self.tn += 1

    def summary(self) -> dict[str, Any]:
        flagged, positives, n = self.tp + self.fp, self.tp + self.fn, self.tp + self.fp + self.fn + self.tn
        return {
            "n": n,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "tn": self.tn,
            # De cada caso que marcamos, cuantos confirmo el examen.
            "precision": round(self.tp / flagged, 4) if flagged else None,
            "precision_ci95": wilson_interval(self.tp, flagged),
            # De cada caso que el examen confirmo, cuantos marcamos.
            "recall": round(self.tp / positives, 4) if positives else None,
            "recall_ci95": wilson_interval(self.tp, positives),
            "specificity": round(self.tn / (self.tn + self.fp), 4) if (self.tn + self.fp) else None,
            "sufficient": flagged >= MIN_CASES_FOR_METRIC and positives >= MIN_CASES_FOR_METRIC,
        }


@dataclass
class PrecisionReport:
    pairs: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    sources: dict[str, int] = field(default_factory=dict)
    confusion: dict[tuple[str, str], Confusion] = field(default_factory=dict)
    positives: dict[str, int] = field(default_factory=dict)
    evaluable: dict[str, int] = field(default_factory=dict)

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1

    def add_pair(self, source: str, truth: dict[str, bool], predictions: dict[str, set[str]]) -> None:
        if not truth:
            self.skip("examen_sin_condicion_evaluable")
            return
        self.pairs += 1
        self.sources[source] = self.sources.get(source, 0) + 1
        for condition, actual in truth.items():
            self.evaluable[condition] = self.evaluable.get(condition, 0) + 1
            self.positives[condition] = self.positives.get(condition, 0) + int(actual)
            for predictor in PREDICTORS:
                self.confusion.setdefault((condition, predictor), Confusion()).add(condition in predictions.get(predictor, set()), actual)

    def to_dict(self) -> dict[str, Any]:
        conditions = {}
        for condition in sorted(self.evaluable):
            n = self.evaluable[condition]
            conditions[condition] = {
                "n": n,
                # Precision de marcar a todos: la linea base contra la que se lee la precision.
                "prevalence": round(self.positives[condition] / n, 4),
                "prevalence_ci95": wilson_interval(self.positives[condition], n),
                "predictors": {
                    predictor: self.confusion[(condition, predictor)].summary()
                    for predictor in PREDICTORS
                    if (condition, predictor) in self.confusion
                },
            }
        return {
            "pairs": self.pairs,
            "sources": dict(sorted(self.sources.items())),
            "skipped": dict(sorted(self.skipped.items())),
            "min_cases_for_metric": MIN_CASES_FOR_METRIC,
            "conditions": conditions,
        }


def build_report(pairs: Iterable[tuple[str, dict[str, str], dict[str, set[str]]]]) -> PrecisionReport:
    """`pairs`: (fuente, statuses del examen, predicciones por variante)."""
    report = PrecisionReport()
    for source, statuses, predictions in pairs:
        report.add_pair(source, lab_truth(statuses), predictions)
    return report
