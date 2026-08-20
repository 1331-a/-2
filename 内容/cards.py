# -*- coding: utf-8 -*-
"""
cards.py — 扑克牌表示与解析工具。

内部统一用一个整数表示一张牌：card = rank * 4 + suit
  - rank（点数）: 2..14（11=J, 12=Q, 13=K, 14=A）
  - suit（花色）: 0=黑桃S, 1=红桃H, 2=方块D, 3=梅花C

BotZone 牌字符串格式："花色 + 点数"，例如
  "SA" -> 黑桃 A，  "HT" -> 红桃 10，  "C3" -> 梅花 3，  "DQ" -> 方块 Q
"""

# 花色
SUIT_NAMES = {0: "S", 1: "H", 2: "D", 3: "C"}
SUITS = {"S": 0, "H": 1, "D": 2, "C": 3}

# 点数
RANK_NAMES = {2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8",
              9: "9", 10: "T", 11: "J", 12: "Q", 13: "K", 14: "A"}
RANK_STR = {v: k for k, v in RANK_NAMES.items()}
RANK_STR["t"] = 10  # 兼容小写 t 表示 10


def parse_card(s):
    """把 BotZone 牌字符串解析为整数。例如 'SA' -> 56。"""
    s = s.strip()
    return RANK_STR[s[1]] * 4 + SUITS[s[0]]


def card_str(c):
    """把整数牌转回字符串。"""
    return SUIT_NAMES[c % 4] + RANK_NAMES[c // 4]


def rank(c):
    """牌的点数（2..14）。"""
    return c // 4


def suit(c):
    """牌的花色（0..3）。"""
    return c % 4


def full_deck():
    """返回一副完整 52 张牌（整数列表）。"""
    return [r * 4 + s for r in range(2, 15) for s in range(4)]


def parse_cards(seq):
    """把牌字符串列表解析为整数列表。"""
    return [parse_card(s) for s in seq]
