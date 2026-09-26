import importlib.util
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "experiments" / "i026_int003_confirmation_composition.py"
spec = importlib.util.spec_from_file_location("i026", MODULE)
i026 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(i026)

def test_truth_count():
    assert i026.parse_truth_count("") == 0
    assert i026.parse_truth_count("S2-1") == 1
    assert i026.parse_truth_count("S2-1,S3-2,S3-3") == 3

def test_sample_key_is_deterministic_and_id_sensitive():
    assert i026.sample_key("S1-1") == i026.sample_key("S1-1")
    assert i026.sample_key("S1-1") != i026.sample_key("S1-2")

def test_z_prop_zero_at_population_rate():
    assert i026.z_prop(0.2, 0.2, 5000) == 0.0
