"""Funciones puras de la validacion peruana con ENDES."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

endes = pytest.importorskip("scripts.training.validar_anemia_endes")


def test_caseid_splits_into_household_and_line() -> None:
    hhid, line = endes.caseid_parts(pd.Series(["      000102201  2", "      325503101 14"]))
    assert hhid.tolist() == ["000102201", "325503101"]
    assert line.tolist() == [2.0, 14.0]


def test_official_anemia_target_codes() -> None:
    target = endes.anemia_target_from_v457(pd.Series(["1", "2", "3", "4", "9", None]))
    assert target.tolist()[:4] == [1.0, 1.0, 1.0, 0.0]
    assert np.isnan(target.iloc[4]) and np.isnan(target.iloc[5])


def test_who_cutoff_uses_pregnancy_threshold() -> None:
    # V456 en g/dL x10: 115 -> 11.5 g/dL
    hb = pd.Series(["115", "115", "125", None])
    pregnant = pd.Series([0, 1, 0, 0])
    target = endes.anemia_target_who(hb, pregnant)
    assert target.tolist()[:3] == [1.0, 0.0, 0.0]  # 11.5 < 12 anemia si no embarazada; >= 11 no anemia si embarazada
    assert np.isnan(target.iloc[3])


def test_features_match_nhanes_contract_and_add_endes_columns() -> None:
    women = pd.DataFrame(
        {
            "V012": ["30", "17"], "V106": ["3", "0"], "V213": ["0", "1"], "V445": ["2636", "9998"], "V437": ["659", "500"], "V438": ["1581", "1500"],
            "QS200": ["1", "2"], "QS201": ["1", None], "QS208": ["2", None], "QS109": ["2", "1"], "QS102": ["2", None],
            "HV040": ["2338", "150"], "V025": ["1", "2"], "V190": ["5", "1"], "V024": ["15", "3"], "V005": ["111791", "90000"],
        }
    )
    f = endes.features_from_endes(women)
    assert set(endes.CAT_FEATURES + endes.NUM_FEATURES) <= set(f.columns)
    assert set(endes.ENDES_CAT + endes.ENDES_NUM) <= set(f.columns)
    assert f["sexo"].tolist() == ["femenino", "femenino"]
    assert f["bmi"].tolist()[0] == pytest.approx(26.36) and np.isnan(f["bmi"].iloc[1])  # 9998 = marcado
    assert f["peso_kg"].iloc[0] == pytest.approx(65.9) and f["talla_cm"].iloc[0] == pytest.approx(158.1)
    assert f["embarazo"].tolist() == ["no", "si"]
    assert f["fuma"].tolist() == ["actual", "nunca"]
    assert f["diabetes_dx"].tolist() == ["no", "si"]
    assert f["altitud_m"].tolist() == [2338.0, 150.0] and f["urbano"].tolist() == ["urbano", "rural"]
    assert not [c for c in f.columns if c.upper().startswith(("LBX", "V453", "V456", "V457"))]
