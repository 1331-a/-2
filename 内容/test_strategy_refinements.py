"""Focused tests for paired-board classification and draw-cost candidate."""
import unittest
import time
from types import SimpleNamespace
from unittest.mock import patch

import strategy as S
from game_state import parse_request
from opponent import OpponentModel


class TestBottomPocket(unittest.TestCase):
    def state(self, hole, board):
        # All cards in these tests are internal rank*4+suit values.
        return SimpleNamespace(hole=hole, board=board)

    def test_exact_reported_bottom_pocket(self):
        st = self.state([11, 8], [37, 38, 43])  # 2s2c on 9d9hTs
        self.assertEqual(S._effective_category(st), S.TWO_PAIR)
        self.assertTrue(S.should_avoid_risk(st))
        with patch.object(S, "BOTTOM_POCKET_RISK_ON", False):
            self.assertFalse(S.should_avoid_risk(st))

    def test_full_house_is_exempt(self):
        self.assertFalse(S.should_avoid_risk(
            self.state([8, 9], [36, 37, 10])))

    def test_overpair_is_exempt(self):
        self.assertFalse(S.should_avoid_risk(
            self.state([48, 49], [36, 37, 40])))

    def test_unpaired_board_is_exempt(self):
        self.assertFalse(S.should_avoid_risk(
            self.state([8, 9], [36, 41, 46])))

    def test_double_paired_board_is_exempt(self):
        self.assertFalse(S.should_avoid_risk(
            self.state([8, 9], [36, 37, 40, 41])))

    def test_river_is_unchanged(self):
        self.assertFalse(S.should_avoid_risk(
            self.state([8, 9], [36, 37, 40, 45, 50])))

    def test_postflop_no_longer_labels_bottom_pocket_strong(self):
        req = {
            "num_players": 2, "dealer_id": 0, "my_id": 0,
            "my_chips": 19500, "my_cards": [3, 0],
            "public_cards": [29, 30, 35], "history": [],
            "hand": 10, "max_hand": 70,
            "total_win_chips": [0, 0], "total_win_games": [0, 0],
        }
        st = parse_request(req)
        S._DECISION_STARTED_WALL = time.time()
        with patch.object(S, "equity_best", return_value=.364), \
                patch.object(S, "_check_side", return_value={"act": "check"}) as side, \
                patch.object(S, "_stability_mode", return_value=False):
            S._postflop_decide(st, OpponentModel())
            self.assertFalse(side.call_args.args[4])
            with patch.object(S, "BOTTOM_POCKET_RISK_ON", False):
                S._postflop_decide(st, OpponentModel())
                self.assertTrue(side.call_args.args[4])
if __name__ == "__main__":
    unittest.main(verbosity=2)
