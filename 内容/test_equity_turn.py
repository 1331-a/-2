# -*- coding: utf-8 -*-
"""Regression tests for bounded turn equity estimation."""
import random
import time
import unittest

import equity


class TestTurnEquity(unittest.TestCase):
    HOLE = [33, 12]
    BOARD = [42, 18, 21, 26]
    RANGE_PCT = 0.5049765395348838

    def test_unlimited_turn_is_exact_reference(self):
        value = equity.exact_equity(
            self.HOLE, self.BOARD, self.RANGE_PCT, deadline=None)
        self.assertAlmostEqual(value, 0.1952733758542117, places=12)

    def test_deadline_turn_does_not_use_fixed_deck_prefix(self):
        exact = equity.exact_equity(
            self.HOLE, self.BOARD, self.RANGE_PCT, deadline=None)
        # A future deadline lets the bounded estimator use its full fixed
        # sample budget, while retaining the production deadline code path.
        values = [
            equity.exact_equity(
                self.HOLE, self.BOARD, self.RANGE_PCT,
                deadline=time.time() + 30.0, rng=random.Random(seed))
            for seed in (1, 2)
        ]
        self.assertTrue(all(abs(value - exact) < 0.035 for value in values),
                        values)
        self.assertTrue(all(abs(value - 0.8188137434872846) > 0.10
                            for value in values), values)

    def test_deadline_is_bounded_when_already_expired(self):
        value = equity.exact_equity(
            self.HOLE, self.BOARD, self.RANGE_PCT,
            deadline=time.time() - 1.0, rng=random.Random(1))
        self.assertEqual(value, 0.5)

    def test_seeded_turn_estimate_is_repeatable(self):
        first = equity.exact_equity(
            self.HOLE, self.BOARD, self.RANGE_PCT,
            deadline=time.time() + 30.0, rng=random.Random(77))
        second = equity.exact_equity(
            self.HOLE, self.BOARD, self.RANGE_PCT,
            deadline=time.time() + 30.0, rng=random.Random(77))
        self.assertEqual(first, second)

    def test_weighted_range_and_river_compatibility(self):
        hole = [48, 49]
        board = [44, 45, 46, 47, 40]
        weights = {(8, 9): 1.0, (10, 11): 3.0}
        value = equity.exact_equity(
            hole, board, opp_range_pct=0.1, opp_weights=weights)
        self.assertGreaterEqual(value, 0.0)
        self.assertLessEqual(value, 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
