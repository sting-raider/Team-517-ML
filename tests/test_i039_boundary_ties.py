import unittest

from ber.boundary_ties import (
    boundary_tie,
    filtered_base_boundary,
    rank_rows,
    select_final_pool,
    summarize_ties,
)


class BoundaryTieTests(unittest.TestCase):
    def test_exact_tie_crossing_cut(self):
        rows = [(1.0, 9, "a"), (.8, 8, "b"), (.8, 7, "c"), (.8, 6, "d"), (.5, 5, "e")]
        detail = boundary_tie(rows, 3, truth_items={"c", "d"})
        self.assertEqual(detail["tie_size"], 3)
        self.assertEqual(detail["selected_from_tie"], 2)
        self.assertEqual(detail["excluded_from_tie"], 1)
        self.assertEqual(detail["actual_selected_truth"], 1)
        self.assertEqual(detail["min_selected_truth"], 1)
        self.assertEqual(detail["max_selected_truth"], 2)
        self.assertEqual(detail["true_link_span"], 1)

    def test_non_crossing_equal_scores_are_safe(self):
        rows = [(1.0, 3, "a"), (1.0, 2, "b"), (.5, 1, "c")]
        self.assertIsNone(boundary_tie(rows, 2))

    def test_identifier_direction_changes_membership_only_inside_tie(self):
        rows = [(1.0, 1, "a"), (.5, 2, "b"), (.5, 3, "c"), (.1, 4, "d")]
        desc = rank_rows(rows, tie_desc=True)[:2]
        asc = rank_rows(rows, tie_desc=False)[:2]
        self.assertEqual(desc[0][2], asc[0][2])
        self.assertEqual({desc[1][2], asc[1][2]}, {"b", "c"})

    def test_final_pool_dense_priority_and_dedup(self):
        dense = [(1.0, 1, "x"), (.9, 2, "y")]
        base = [(.8, "a", "x"), (.7, "b", "z"), (.6, "c", "w")]
        out = select_final_pool(dense, base, cap=4, base_pre_cap=3)
        self.assertEqual([r[2] for r in out], ["x", "y", "z", "w"])

    def test_filtered_base_boundary_ignores_dense_duplicates(self):
        base = [(1.0, "a", "d1"), (.9, "b", "b1"), (.8, "c", "b2"), (.8, "d", "b3"), (.7, "e", "b4")]
        detail = filtered_base_boundary(base, {"d1"}, final_cap=3, dense_slots=1)
        self.assertEqual(detail["score"], .8)
        self.assertEqual(detail["tie_size"], 2)

    def test_summary(self):
        d1 = boundary_tie([(1, 3, "a"), (.5, 2, "b"), (.5, 1, "c")], 2, truth_items={"c"})
        summary = summarize_ties([d1, None], anchors=2)
        self.assertEqual(summary["tie_anchors"], 1)
        self.assertEqual(summary["tie_rate"], .5)
        self.assertEqual(summary["truth_sensitive_tie_anchors"], 1)

    def test_saved_prefix_can_differ_when_shard_boundary_is_tied(self):
        shard = [(1.0, 9, "a"), (.9, 8, "b"), (.9, 7, "c")]
        self.assertIsNotNone(boundary_tie(shard, 2))
        selected = rank_rows(shard, tie_desc=True)[:2]
        self.assertEqual([r[2] for r in selected], ["a", "b"])

    def test_no_boundary_tie_makes_tiebreak_direction_irrelevant(self):
        rows = [(1.0, 1, "a"), (.9, 2, "b"), (.8, 3, "c")]
        self.assertIsNone(boundary_tie(rows, 2))
        self.assertEqual(
            {r[2] for r in rank_rows(rows, tie_desc=True)[:2]},
            {r[2] for r in rank_rows(rows, tie_desc=False)[:2]},
        )

    def test_bad_sort_rejected(self):
        with self.assertRaises(ValueError):
            boundary_tie([(.5, 1, "a"), (.8, 2, "b"), (.8, 3, "c")], 2)


if __name__ == "__main__":
    unittest.main()
