import json
import tempfile
import unittest
from pathlib import Path

from ber.profiling import StageProfiler


class Sequence:
    def __init__(self, values):
        self.values = iter(values)

    def __call__(self):
        return next(self.values)


class StageProfilerTests(unittest.TestCase):
    def test_aggregates_repeated_stage_calls(self):
        profiler = StageProfiler(
            metadata={"cap": 640},
            clock=Sequence([1.0, 1.25, 2.0, 2.75]),
            rss_reader=Sequence([100, 120, 120, 150]),
            peak_reader=Sequence([1000, 1100, 1100, 1400, 1400]),
        )
        with profiler.stage("retrieval"):
            pass
        with profiler.stage("retrieval"):
            pass
        result = profiler.snapshot()
        stage = result["stages"]["retrieval"]
        self.assertEqual(stage["count"], 2)
        self.assertEqual(stage["wall_seconds"], 1.0)
        self.assertEqual(stage["max_call_seconds"], 0.75)
        self.assertEqual(stage["rss_start_bytes"], 100)
        self.assertEqual(stage["rss_end_bytes"], 150)
        self.assertEqual(stage["rss_delta_bytes"], 50)
        self.assertEqual(stage["peak_rss_bytes"], 1400)
        self.assertEqual(result["metadata"]["cap"], 640)

    def test_empty_stage_name_is_rejected(self):
        profiler = StageProfiler()
        with self.assertRaises(ValueError):
            with profiler.stage(""):
                pass

    def test_writes_atomic_json(self):
        profiler = StageProfiler(
            clock=Sequence([3.0, 3.5]),
            rss_reader=Sequence([None, None]),
            peak_reader=Sequence([None, None, None]),
        )
        with profiler.stage("score"):
            pass
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            profiler.write_json(path)
            data = json.loads(path.read_text())
            self.assertEqual(data["schema_version"], 1)
            self.assertEqual(data["stages"]["score"]["wall_seconds"], 0.5)
            self.assertFalse(path.with_suffix(".json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
