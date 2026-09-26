import unittest

import numpy as np
from catboost import CatBoostClassifier


class X012CatBoostSaturationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows = []
        labels = []
        for value in range(1, 101):
            for context in (0.0, 1.0):
                rows.append([float(value), context])
                labels.append(
                    int((value > 45) ^ (context > 0.5 and value < 70))
                )
        cls.train = np.asarray(rows, dtype=np.float32)
        cls.labels = np.asarray(labels, dtype=np.uint8)

        # Deliberately place feature-0 validation values far above learn support.
        # The repository also supplies early-stop data as eval_set, so this checks
        # that eval-only outliers do not become train-time numerical borders.
        eval_x = np.asarray(
            [[1000.0, 0.0], [2000.0, 1.0], [5000.0, 0.0]],
            dtype=np.float32,
        )
        eval_y = np.asarray([1, 1, 1], dtype=np.uint8)

        cls.model = CatBoostClassifier(
            iterations=40,
            depth=5,
            learning_rate=0.1,
            loss_function="Logloss",
            l2_leaf_reg=10,
            random_seed=517,
            task_type="CPU",
            thread_count=2,
            verbose=False,
            allow_writing_files=False,
        )
        cls.model.fit(
            cls.train,
            cls.labels,
            eval_set=(eval_x, eval_y),
            verbose=False,
        )

    def test_auto_borders_stay_inside_learn_support(self):
        borders = self.model.get_borders()[0]
        self.assertTrue(borders)
        self.assertLess(max(borders), float(self.train[:, 0].max()))

    def test_values_above_learn_max_share_prediction_for_fixed_context(self):
        train_max = float(self.train[:, 0].max())
        for context in (0.0, 1.0):
            probes = np.asarray(
                [
                    [train_max, context],
                    [train_max + 1.0, context],
                    [train_max * 10.0, context],
                    [1e9, context],
                ],
                dtype=np.float64,
            )
            probabilities = self.model.predict_proba(probes)[:, 1]
            np.testing.assert_array_equal(
                probabilities,
                np.repeat(probabilities[0], len(probabilities)),
            )


if __name__ == "__main__":
    unittest.main()
