# -*- coding: utf-8 -*-
"""离线范围审计工具的基础回归。"""
import importlib.util
import os
import sys
import unittest
from unittest.mock import patch


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "测", "_range_condition_audit.py")
SPEC = importlib.util.spec_from_file_location("range_condition_audit", PATH)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)
sys.path.insert(0, os.path.dirname(PATH))
import _range_replay_ab as REPLAY


class TestRangeAudit(unittest.TestCase):
    def test_condition_key(self):
        self.assertEqual(
            AUDIT.condition_key({"pre_raise": False, "has_raise": True}),
            "no_pre_raise_raise")
        self.assertEqual(
            AUDIT.condition_key({"pre_raise": True, "has_raise": False}),
            "pre_raise_no_raise")

    def test_summary(self):
        got = AUDIT.summary([
            {"pct": 0.1},
            {"pct": 0.2},
            {"pct": 0.8},
            {"pct": 0.9},
        ])
        self.assertEqual(got["n"], 4)
        self.assertAlmostEqual(got["mean"], 0.5)
        self.assertAlmostEqual(got["median"], 0.5)
        self.assertEqual(got["pct_le_025"], 50.0)

    def test_empty_summary(self):
        self.assertIsNone(AUDIT.summary([]))

    def test_exact_vs_hole_on_river(self):
        hole = [14 * 4, 13 * 4]
        board = [12 * 4, 11 * 4, 10 * 4, 2 * 4, 3 * 4]
        opp = [9 * 4, 8 * 4]
        value = AUDIT.exact_vs_hole(hole, board, opp)
        self.assertEqual(value, 1.0)

    def test_exact_tie_and_loss(self):
        board = AUDIT.internal_cards(["As", "Ks", "Qs", "Js", "Ts"])
        mine = AUDIT.internal_cards(["2c", "3c"])
        opp = AUDIT.internal_cards(["4d", "5d"])
        self.assertEqual(AUDIT.exact_vs_hole(mine, board, opp), 0.5)
        board = AUDIT.internal_cards(["2c", "3c", "4c", "5c", "9d"])
        mine = AUDIT.internal_cards(["Ah", "Ad"])
        opp = AUDIT.internal_cards(["Ac", "Kd"])
        self.assertEqual(AUDIT.exact_vs_hole(mine, board, opp), 0.0)

    def test_overlapping_cards_rejected(self):
        with self.assertRaises(ValueError):
            AUDIT.exact_vs_hole([8, 9], [10, 11, 12], [8, 13])

    def test_unknown_card_rejected(self):
        with self.assertRaises(ValueError):
            AUDIT.internal_cards(["invalid"])

    def test_seat_ambiguity(self):
        obj = {"match": {"bot_a": {"owner_display": "j1331"},
                         "bot_b": {"owner_display": "opponent"}}}
        self.assertEqual(AUDIT.match_seat(obj), 0)
        obj["match"]["bot_b"]["owner_display"] = "j1331"
        self.assertIsNone(AUDIT.match_seat(obj))
        self.assertIsNone(AUDIT.match_seat({}))

    def test_full_match_id(self):
        self.assertEqual(AUDIT.match_id(
            "botbattle-holdem-20261012170738-4895b988-log.json"),
            "20261012170738-4895b988")

    def test_targets_include_street(self):
        self.assertIn(("20261012172157-11de872b", 57, "turn"), AUDIT.TARGETS)
        self.assertNotIn(("20261012172157-11de872b", 57, "flop"), AUDIT.TARGETS)

    def test_residual_summary(self):
        rows = [{"match_id": "m", "hand": 1,
                 "baseline_eq": .6, "fixed_hole_eq": .4},
                {"match_id": "m", "hand": 1,
                 "baseline_eq": .3, "fixed_hole_eq": .5}]
        got = AUDIT.residual_summary(rows)
        self.assertEqual(got["decisions"], 2)
        self.assertEqual(got["hands"], 1)
        self.assertAlmostEqual(got["mean_signed_error"], 0.0)
        self.assertAlmostEqual(got["mae"], .2)

    def test_frozen_equity_has_no_deadline(self):
        state = type("State", (), {"hole": [8, 9], "board": [10, 11, 12]})()
        with patch.object(AUDIT.E, "monte_carlo_equity", return_value=.7) as mc:
            self.assertEqual(AUDIT.frozen_equity(state, .4, 123, 400), .7)
            self.assertIsNone(mc.call_args.kwargs["deadline"])
            self.assertEqual(mc.call_args.kwargs["iterations"], 400)

    def test_response_comparison_counts_hand_once(self):
        base = [{"match_id": "m", "request_index": i, "hand": 1,
                 "response": 0, "settle_delta_observed_only": -100}
                for i in (0, 1)]
        changed = [dict(row, response=-1) for row in base]
        got = REPLAY.compare(base, changed)
        self.assertEqual(got["changed_decisions"], 2)
        self.assertEqual(got["changed_hands"], 1)
        self.assertEqual(
            got["observed_changed_hand_deltas_not_improvement"], -100)
        self.assertEqual(REPLAY.compare(base, base)["changed_decisions"], 0)

    def test_response_comparison_rejects_misalignment(self):
        base = [{"match_id": "m", "request_index": 0}]
        with self.assertRaises(ValueError):
            REPLAY.compare(base, [])

    def test_turn_prefixes_stop_after_requested_rivers(self):
        state = type("State", (), {"hole": [8, 9],
                                   "board": [10, 11, 12, 13]})()

        def simulated_turn(*args, **kwargs):
            done = 0
            for index in range(46):
                if index % 4 == 0 and AUDIT.E.time.time() >= kwargs["deadline"]:
                    break
                done += 1
            return done

        with patch.object(AUDIT.E, "exact_equity", side_effect=simulated_turn):
            self.assertEqual(
                AUDIT.turn_prefixes(state, .5),
                {"4": 4, "8": 8, "16": 16, "32": 32})

    def test_frozen_equity_repeatability(self):
        state = type("State", (), {
            "hole": AUDIT.internal_cards(["Ah", "Kd"]),
            "board": AUDIT.internal_cards(["Qs", "7c", "2d"])})()
        first = AUDIT.frozen_equity(state, .45, 123, 64)
        self.assertEqual(first, AUDIT.frozen_equity(state, .45, 123, 64))


if __name__ == "__main__":
    unittest.main(verbosity=2)
