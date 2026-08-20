# -*- coding: utf-8 -*-
"""
evaluator.py — 牌型评估器。

从 7 张牌（2 张底牌 + 最多 5 张公共牌）中选出最强的 5 张组合并评估牌型。

牌型等级（从高到低）：
  9  皇家同花顺  Royal Flush      A-K-Q-J-T 同花
  8  同花顺      Straight Flush
  7  四条        Four of a Kind
  6  葫芦        Full House
  5  同花        Flush
  4  顺子        Straight
  3  三条        Three of a Kind
  2  两对        Two Pair
  1  一对        One Pair
  0  高牌        High Card

评估结果统一表示为一个 6 元组：(category, t1, t2, t3, t4, t5)
Python 的元组比较规则可直接用于牌型大小比较（先比 category，再依次比各 tiebreaker）。
"""

from itertools import combinations

# 牌型等级常量
ROYAL_FLUSH = 9
STRAIGHT_FLUSH = 8
FOUR_OF_A_KIND = 7
FULL_HOUSE = 6
FLUSH = 5
STRAIGHT = 4
THREE_OF_A_KIND = 3
TWO_PAIR = 2
ONE_PAIR = 1
HIGH_CARD = 0

CATEGORY_NAMES = {
    ROYAL_FLUSH: "皇家同花顺",
    STRAIGHT_FLUSH: "同花顺",
    FOUR_OF_A_KIND: "四条",
    FULL_HOUSE: "葫芦",
    FLUSH: "同花",
    STRAIGHT: "顺子",
    THREE_OF_A_KIND: "三条",
    TWO_PAIR: "两对",
    ONE_PAIR: "一对",
    HIGH_CARD: "高牌",
}


def evaluate_5(cards):
    """评估恰好 5 张牌，返回可比 6 元组。"""
    ranks = sorted((c // 4 for c in cards), reverse=True)
    is_flush = len({c % 4 for c in cards}) == 1

    # 顺子检测（含 A-2-3-4-5 轮子）
    uniq = sorted(set(ranks), reverse=True)
    straight_high = 0
    if len(uniq) == 5:
        if uniq[0] - uniq[4] == 4:
            straight_high = uniq[0]
        elif uniq == [14, 5, 4, 3, 2]:
            straight_high = 5  # 轮子：A 当 1 用，最高牌为 5

    # 点数计数，按 (数量, 点数) 降序分组
    counts = {}
    for r in ranks:
        counts[r] = counts.get(r, 0) + 1
    groups = sorted(counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)

    if is_flush and straight_high:
        if straight_high == 14:
            return (ROYAL_FLUSH, 0, 0, 0, 0, 0)
        return (STRAIGHT_FLUSH, straight_high, 0, 0, 0, 0)

    top_count = groups[0][1]

    if top_count == 4:
        return (FOUR_OF_A_KIND, groups[0][0], groups[1][0], 0, 0, 0)

    if top_count == 3 and groups[1][1] == 2:
        return (FULL_HOUSE, groups[0][0], groups[1][0], 0, 0, 0)

    if is_flush:
        return (FLUSH, ranks[0], ranks[1], ranks[2], ranks[3], ranks[4])

    if straight_high:
        return (STRAIGHT, straight_high, 0, 0, 0, 0)

    if top_count == 3:
        kickers = [g[0] for g in groups[1:]]
        return (THREE_OF_A_KIND, groups[0][0], kickers[0], kickers[1], 0, 0)

    if top_count == 2 and groups[1][1] == 2:
        return (TWO_PAIR, groups[0][0], groups[1][0], groups[2][0], 0, 0)

    if top_count == 2:
        kickers = [g[0] for g in groups[1:]]
        return (ONE_PAIR, groups[0][0], kickers[0], kickers[1], kickers[2], 0)

    return (HIGH_CARD, ranks[0], ranks[1], ranks[2], ranks[3], ranks[4])


def evaluate_7(cards):
    """从 5~7 张牌中选出最佳 5 张并评估，返回可比 6 元组。

    注：曾尝试改写为单遍位运算直达版，但纯 Python 的位运算/多趟循环
    反而比 `combinations + evaluate_5`（evaluate_5 内部用 C 实现的
    sorted/set/dict）更慢约 12%。蒙特卡洛单步仅约 50ms，离 1 秒时限
    还有 20 倍余量，评估器不是瓶颈，故沿用此实现。
    """
    best = None
    for combo in combinations(cards, 5):
        e = evaluate_5(combo)
        if best is None or e > best:
            best = e
    return best


def category_name(result):
    """返回牌型的中文名称。"""
    return CATEGORY_NAMES.get(result[0], "未知")


def compare(my_cards, opp_cards):
    """比较双方手牌（7 张），返回 1（我胜）/ 0（平）/ -1（我负）。"""
    m = evaluate_7(my_cards)
    o = evaluate_7(opp_cards)
    if m > o:
        return 1
    if m < o:
        return -1
    return 0
