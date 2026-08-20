# -*- coding: utf-8 -*-
"""
test_evaluator.py — 牌型评估器单元测试。

运行：python test_evaluator.py
"""

import unittest

import cards
import evaluator


def E(*card_strs):
    """把牌字符串列表转成整数列表。"""
    return cards.parse_cards(list(card_strs))


class TestEvaluate(unittest.TestCase):

    def _cat(self, *card_strs):
        return evaluator.evaluate_7(E(*card_strs))[0]

    def test_royal_flush(self):
        # 手牌 A K 同花 + 公共牌 Q J T 同花
        hand = ["SA", "SK"]
        board = ["SQ", "SJ", "ST"]
        self.assertEqual(self._cat(*hand, *board), evaluator.ROYAL_FLUSH)

    def test_straight_flush(self):
        hand = ["S9", "S8"]
        board = ["S7", "S6", "S5"]
        self.assertEqual(self._cat(*hand, *board), evaluator.STRAIGHT_FLUSH)

    def test_four_of_a_kind(self):
        hand = ["SA", "HA"]
        board = ["CA", "DA", "SK"]
        self.assertEqual(self._cat(*hand, *board), evaluator.FOUR_OF_A_KIND)

    def test_full_house(self):
        hand = ["SA", "HA"]
        board = ["CA", "SK", "HK"]
        self.assertEqual(self._cat(*hand, *board), evaluator.FULL_HOUSE)

    def test_flush(self):
        hand = ["SA", "S3"]
        board = ["S9", "S7", "S2", "H4", "H5"]
        self.assertEqual(self._cat(*hand, *board), evaluator.FLUSH)

    def test_straight(self):
        hand = ["S9", "S8"]
        board = ["H7", "D6", "C5"]
        self.assertEqual(self._cat(*hand, *board), evaluator.STRAIGHT)

    def test_wheel_straight(self):
        # A-2-3-4-5 轮子顺
        hand = ["SA", "H2"]
        board = ["D3", "C4", "S5"]
        self.assertEqual(self._cat(*hand, *board), evaluator.STRAIGHT)

    def test_three_of_a_kind(self):
        hand = ["SA", "HA"]
        board = ["CA", "S7", "D2"]
        self.assertEqual(self._cat(*hand, *board), evaluator.THREE_OF_A_KIND)

    def test_two_pair(self):
        hand = ["SA", "HA"]
        board = ["CK", "SK", "D2"]
        self.assertEqual(self._cat(*hand, *board), evaluator.TWO_PAIR)

    def test_one_pair(self):
        hand = ["SA", "H7"]
        board = ["CK", "SK", "D2"]
        self.assertEqual(self._cat(*hand, *board), evaluator.ONE_PAIR)

    def test_high_card(self):
        hand = ["SA", "H7"]
        board = ["C9", "SK", "D2"]
        self.assertEqual(self._cat(*hand, *board), evaluator.HIGH_CARD)

    def test_compare_flush_beats_straight(self):
        flush = E("SA", "S3", "S9", "S7", "S2", "H4", "H5")
        straight = E("S9", "S8", "H7", "D6", "C5", "H2", "D3")
        self.assertEqual(evaluator.compare(flush, straight), 1)

    def test_compare_kicker(self):
        # 都是一对 A，比踢脚：A-K 胜 A-Q
        ak = E("SA", "HK", "CA", "D7", "C2", "H9", "D5")
        aq = E("HA", "HQ", "DA", "D7", "C2", "H9", "D5")
        self.assertEqual(evaluator.compare(ak, aq), 1)

    def test_compare_tie(self):
        # 公共牌决定，双方相同 -> 平局
        a = E("SA", "H2", "C3", "D4", "S5", "H6", "D7")
        b = E("HA", "S2", "C3", "D4", "S5", "H6", "D7")
        self.assertEqual(evaluator.compare(a, b), 0)

    def test_best_five_of_seven(self):
        # 7 张里能凑成葫芦，应识别为葫芦而非两对
        hand = ["SA", "HA"]
        board = ["CA", "SK", "HK", "H2", "D3"]
        self.assertEqual(self._cat(*hand, *board), evaluator.FULL_HOUSE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
