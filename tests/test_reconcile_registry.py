import csv
import tempfile
import unittest
from pathlib import Path

from tools.reconcile_registry import HEADER, RegistryError, read_registry, reconcile, render


def make_row(experiment_id, status="PROMOTE", note=""):
    return (
        experiment_id,
        "#1",
        "I",
        "test-agent",
        f"agent/i/{experiment_id.lower()}",
        "deadbeef",
        "hypothesis",
        "slice",
        "baseline",
        "candidate",
        "0",
        note,
        "1s",
        status,
        f"reports/swarm/{experiment_id}.md",
    )


def write_registry(path, rows, header=HEADER):
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


class RegistryReconcilerTests(unittest.TestCase):
    def test_disjoint_rows_are_unioned_in_deterministic_id_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a.tsv"
            b = Path(tmp) / "b.tsv"
            write_registry(a, [make_row("R010"), make_row("I002")])
            write_registry(b, [make_row("X001"), make_row("D003")])

            rows = reconcile([a, b])

            self.assertEqual([row[0] for row in rows], ["D003", "I002", "R010", "X001"])

    def test_identical_duplicate_row_is_deduplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a.tsv"
            b = Path(tmp) / "b.tsv"
            row = make_row("I019")
            write_registry(a, [row])
            write_registry(b, [row])

            self.assertEqual(reconcile([a, b]), [row])

    def test_conflicting_duplicate_id_fails_with_both_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "left.tsv"
            b = Path(tmp) / "right.tsv"
            write_registry(a, [make_row("R001", status="PROMOTE")])
            write_registry(b, [make_row("R001", status="REJECT")])

            with self.assertRaises(RegistryError) as ctx:
                reconcile([a, b])

            message = str(ctx.exception)
            self.assertIn("R001", message)
            self.assertIn(str(a), message)
            self.assertIn(str(b), message)

    def test_malformed_header_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.tsv"
            good = Path(tmp) / "good.tsv"
            write_registry(bad, [], header=("wrong",))
            write_registry(good, [])

            with self.assertRaises(RegistryError):
                reconcile([bad, good])

    def test_malformed_row_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.tsv"
            good = Path(tmp) / "good.tsv"
            with bad.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
                writer.writerow(HEADER)
                writer.writerow(["R001", "too-short"])
            write_registry(good, [])

            with self.assertRaises(RegistryError):
                reconcile([bad, good])

    def test_empty_fields_survive_render_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.tsv"
            other = Path(tmp) / "other.tsv"
            rendered = Path(tmp) / "rendered.tsv"
            row = make_row("I019", note="")
            write_registry(source, [row])
            write_registry(other, [])

            rendered.write_text(render(reconcile([source, other])), encoding="utf-8")
            self.assertEqual(read_registry(rendered), [row])

    def test_requires_two_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            only = Path(tmp) / "only.tsv"
            write_registry(only, [])
            with self.assertRaises(RegistryError):
                reconcile([only])


if __name__ == "__main__":
    unittest.main()
