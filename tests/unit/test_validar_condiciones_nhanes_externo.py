"""Validacion externa NHANES 2021-2023: reporte de faltantes por feature."""

from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.training.entrenar_condiciones_nhanes import CYCLES
from scripts.training.validar_condiciones_nhanes_externo import EXTERNAL_CYCLE, missing_share


def test_external_cycle_is_registered_but_not_used_for_training() -> None:
    from scripts.training.entrenar_condiciones_nhanes import TEST_CYCLE, TRAIN_CYCLE

    assert CYCLES[EXTERNAL_CYCLE] == {"year": "2021", "suffix": "L"}
    assert EXTERNAL_CYCLE not in {TRAIN_CYCLE, TEST_CYCLE}


def test_missing_share_counts_nan_and_missing_category() -> None:
    frame = pd.DataFrame({"sexo": ["femenino", "missing", "masculino", "missing"], "edad": [30.0, np.nan, 40.0, 50.0]})
    assert missing_share(frame) == {"sexo": 0.5, "edad": 0.25}
