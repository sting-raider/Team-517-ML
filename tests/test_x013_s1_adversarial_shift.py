import numpy as np
import pandas as pd

from tools.experiments.x013_s1_adversarial_shift import (
    grouped_fold,
    normalize_series,
    structural_matrix,
)


def test_normalize_semantic_mirror():
    s = pd.Series(["  Café & Co., LTD.  ", "A_B/C-12"])
    got = normalize_series(s).tolist()
    assert got == ["cafe co ltd", "a b c 12"]


def test_grouped_fold_keeps_identical_text_together():
    country = pd.Series(["US", "US", "India", "India"])
    joint = pd.Series(["same place", "same place", "same place", "same place"])
    folds = grouped_fold(country, joint)
    assert folds[0] == folds[1]
    assert folds[2] == folds[3]
    assert folds.dtype == np.uint8


def test_structural_matrix_uses_text_only_and_is_finite():
    df = pd.DataFrame(
        {
            "business_name": ["Cafe 24", "Alpha"],
            "business_address": ["12 Main St.", "Road-7"],
            "n_name": ["cafe 24", "alpha"],
            "n_addr": ["12 main st", "road 7"],
        }
    )
    x = structural_matrix(df)
    assert x.shape == (2, 22)
    assert np.isfinite(x).all()
