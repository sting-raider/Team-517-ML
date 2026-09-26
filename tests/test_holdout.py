import json
import tempfile
import unittest
from pathlib import Path

from ber.holdout import (
    authorize_confirmation,
    load_freeze,
    register_consumption,
    require_confirmation_reuse,
)


FREEZE = {
    "version": 1,
    "forbidden": [
        {"label": "development", "offset": 0, "size": 30000},
        {"label": "expanded_fit", "offset": 50000, "size": 150000},
    ],
    "consumed": [
        {"label": "v1", "offset": 35000, "size": 5000},
        {"label": "v2", "offset": 40000, "size": 5000},
        {"label": "v3", "offset": 45000, "size": 5000},
    ],
}


class HoldoutGuardTests(unittest.TestCase):
    def test_forbidden_ranges_are_never_confirmation(self):
        for offset, size in ((29999, 2), (50000, 5000), (195000, 5000)):
            with self.subTest(offset=offset, size=size):
                with self.assertRaisesRegex(ValueError, "forbidden"):
                    authorize_confirmation(
                        FREEZE, offset, size, consume_new=True, reason="final check"
                    )

    def test_current_consumed_windows_refuse_default_reuse(self):
        for offset in (35000, 40000, 45000):
            with self.subTest(offset=offset):
                with self.assertRaisesRegex(ValueError, "already consumed"):
                    authorize_confirmation(FREEZE, offset, 5000)

    def test_exact_reuse_requires_reason(self):
        with self.assertRaisesRegex(ValueError, "non-empty reason"):
            authorize_confirmation(FREEZE, 45000, 5000, allow_reuse=True)
        result = authorize_confirmation(
            FREEZE, 45000, 5000, allow_reuse=True, reason="reproduce INT003 table"
        )
        self.assertEqual(result["action"], "reuse")
        self.assertEqual(result["prior"]["label"], "v3")

    def test_partial_overlap_is_refused_even_with_reuse_override(self):
        with self.assertRaisesRegex(ValueError, "partially overlaps"):
            authorize_confirmation(
                FREEZE, 42500, 5000, allow_reuse=True, reason="bad idea"
            )

    def test_first_post_training_window_is_fresh_but_explicit(self):
        with self.assertRaisesRegex(ValueError, "currently fresh"):
            authorize_confirmation(FREEZE, 200000, 5000)
        with self.assertRaisesRegex(ValueError, "non-empty reason"):
            authorize_confirmation(FREEZE, 200000, 5000, consume_new=True)
        result = authorize_confirmation(
            FREEZE, 200000, 5000, consume_new=True, reason="future final gate"
        )
        self.assertEqual(result["action"], "consume_new")

    def test_require_reuse_fails_closed_on_fresh_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "freeze.json"
            path.write_text(json.dumps(FREEZE), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "currently fresh"):
                require_confirmation_reuse(200000, 5000, "not allowed here", path)
            result = require_confirmation_reuse(
                40000, 5000, "reproduce INT002", path
            )
            self.assertEqual(result["prior"]["label"], "v2")

    def test_register_new_consumption_updates_manifest_and_blocks_repeat(self):
        minimal = {"version": 1, "forbidden": [], "consumed": []}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "freeze.json"
            path.write_text(json.dumps(minimal), encoding="utf-8")
            decision = authorize_confirmation(
                minimal, 200000, 5000, consume_new=True, reason="one final check"
            )
            entry = register_consumption(
                path,
                decision,
                report=Path("reports/new.json"),
                config={"cap": 160},
                result={"score": 0.9},
            )
            self.assertEqual(entry["offset"], 200000)
            updated = load_freeze(path)
            self.assertEqual(len(updated["consumed"]), 1)
            with self.assertRaisesRegex(ValueError, "already consumed"):
                authorize_confirmation(updated, 200000, 5000)

    def test_shipped_manifest_matches_current_confirmation_history(self):
        path = Path(__file__).resolve().parents[1] / "reports" / "CONFIRMATION_FREEZE.json"
        freeze = load_freeze(path)
        consumed = {(int(x["offset"]), int(x["size"])) for x in freeze["consumed"]}
        self.assertEqual(
            consumed,
            {(30000, 5000), (35000, 5000), (40000, 5000), (45000, 5000)},
        )
        forbidden = {(int(x["offset"]), int(x["size"])) for x in freeze["forbidden"]}
        self.assertIn((0, 30000), forbidden)
        self.assertIn((50000, 150000), forbidden)

    def test_invalid_manifest_version_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "freeze.json"
            path.write_text(
                json.dumps({"version": 2, "forbidden": [], "consumed": []}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                load_freeze(path)


if __name__ == "__main__":
    unittest.main()
