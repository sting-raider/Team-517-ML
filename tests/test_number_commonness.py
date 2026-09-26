import math
import unittest

from ber.number_commonness import (
    NUMBER_COMMONNESS_NAMES,
    NUMBER_TOKEN_REGEX,
    build_number_commonness,
    commonness_values,
    profile_joins,
    select_expressions,
)
from ber.v3 import V3_NAMES
from ber.v4 import V4_NAMES


class FakeConnection:
    def __init__(self):
        self.sql = []

    def execute(self, query):
        self.sql.append(query)
        return self


class NumberCommonnessTests(unittest.TestCase):
    def test_rare_shared_and_unmatched_semantics(self):
        values = commonness_values(
            ["12", "12", "999"],
            ["999", "7"],
            {"12": 5000, "999": 2},
            {"999": 3, "7": 1000},
        )
        expected = [
            math.log1p(2),
            math.log1p(3),
            math.log1p(5000),
            math.log1p(1000),
        ]
        for actual, target in zip(values, expected):
            self.assertAlmostEqual(actual, target, places=12)

    def test_empty_and_disjoint_are_explicit_and_finite(self):
        self.assertEqual(commonness_values([], [], {}, {}), [0.0] * 4)
        values = commonness_values(["1"], ["2"], {"1": 7}, {"2": 11})
        self.assertEqual(values[:2], [0.0, 0.0])
        self.assertAlmostEqual(values[2], math.log1p(7))
        self.assertAlmostEqual(values[3], math.log1p(11))
        self.assertTrue(all(math.isfinite(x) for x in values))

    def test_repeated_numbers_are_deduplicated(self):
        once = commonness_values(["42"], ["42"], {"42": 5}, {"42": 9})
        repeated = commonness_values(
            ["42", "42", "42"], ["42", "42"], {"42": 5}, {"42": 9}
        )
        self.assertEqual(once, repeated)

    def test_df_builder_is_country_source_scoped_and_record_deduplicated(self):
        c = FakeConnection()
        build_number_commonness(c, "train")
        self.assertEqual(len(c.sql), 8)
        joined = "\n".join(c.sql)
        self.assertIn("s.source=1", joined)
        self.assertIn("s.source>1", joined)
        self.assertIn("GROUP BY country,token", joined)
        self.assertIn("GROUP BY country,source,token", joined)
        self.assertIn("USING(country,source,token)", joined)
        self.assertGreaterEqual(
            joined.count("list_distinct(regexp_extract_all"), 8
        )
        self.assertEqual(NUMBER_TOKEN_REGEX, r"\p{Nd}+")
        self.assertNotIn("[0-9]+", joined)
        self.assertGreaterEqual(joined.count(r"\p{Nd}+"), 8)
        self.assertIn("m003_train_left_n_df", joined)
        self.assertIn("m003_train_right_a_profile", joined)

    def test_target_profile_joins_pin_the_actual_source(self):
        joins = profile_joins("test")
        self.assertIn("m003_rn.source=r.source", joins)
        self.assertIn("m003_ra.source=r.source", joins)
        self.assertNotIn("m003_ln.source", joins)
        self.assertNotIn("m003_la.source", joins)

    def test_query_contract_has_exact_eight_ordered_features(self):
        self.assertEqual(len(NUMBER_COMMONNESS_NAMES), 8)
        self.assertEqual(len(select_expressions()), 8)
        joins = profile_joins("test")
        self.assertIn("m003_test_left_n_profile", joins)
        self.assertIn("m003_test_right_a_profile", joins)
        self.assertEqual(V4_NAMES[: len(V3_NAMES)], V3_NAMES)
        self.assertEqual(V4_NAMES[len(V3_NAMES) :], NUMBER_COMMONNESS_NAMES)

    def test_invalid_split_fails_closed(self):
        with self.assertRaises(ValueError):
            profile_joins("confirmation")
        with self.assertRaises(ValueError):
            build_number_commonness(FakeConnection(), "dev")


if __name__ == "__main__":
    unittest.main()
