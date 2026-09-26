import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "experiments" / "d015_threshold_plateau.py"
spec = importlib.util.spec_from_file_location("d015_threshold_plateau", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class ThresholdPlateauTests(unittest.TestCase):
    def test_contiguous_component_and_midpoint(self):
        curve = [
            {"threshold": .1, "macro_f0_5": .8},
            {"threshold": .2, "macro_f0_5": .9},
            {"threshold": .3, "macro_f0_5": .91},
            {"threshold": .4, "macro_f0_5": .9},
            {"threshold": .5, "macro_f0_5": .7},
        ]
        out = mod.analyze_curve(curve, epsilons=(.011,))
        band = out["epsilon_optimal_components"]["0.011"]
        self.assertEqual(out["best_threshold"], .3)
        self.assertAlmostEqual(band["low_threshold"], .2)
        self.assertAlmostEqual(band["high_threshold"], .4)
        self.assertAlmostEqual(band["midpoint"], .3)

    def test_neighbor_losses_and_tiebreak(self):
        curve = [
            {"threshold": .1, "macro_f0_5": .8},
            {"threshold": .2, "macro_f0_5": .9},
            {"threshold": .3, "macro_f0_5": .9},
        ]
        out = mod.analyze_curve(curve, epsilons=(0,))
        self.assertEqual(out["best_threshold"], .3)
        self.assertAlmostEqual(out["neighbors"]["left"]["loss"], 0.0)

    def test_rejects_unsorted_or_duplicate_thresholds(self):
        with self.assertRaises(ValueError):
            mod.analyze_curve([
                {"threshold": .2, "macro_f0_5": .8},
                {"threshold": .1, "macro_f0_5": .9},
            ])
        with self.assertRaises(ValueError):
            mod.analyze_curve([
                {"threshold": .1, "macro_f0_5": .8},
                {"threshold": .1, "macro_f0_5": .9},
            ])


if __name__ == "__main__":
    unittest.main()
