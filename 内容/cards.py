# -*- coding: utf-8 -*-
"""
cards.py — 扑克牌的生成工具。

内部统一用一个整数表示一张牌：card = rank * 4 + suit
  - rank（点数）: 2..14（11=J, 12=Q, 13=K, 14=A）
  - suit（花色）: 0=黑桃S, 1=红桃H, 2=方块D, 3=梅花C

说明：本模块原有 parse_card / card_str / rank / suit 等字符串互转工具，
经「零引用」扫描确认在机器人运行路径中无人调用，已清理（需要时可从
git 历史取回）。当前仅保留 equity.py 蒙特卡洛抽样所需的 full_deck()。
"""


def full_deck():
    """返回一副完整 52 张牌（内部编码整数列表）。"""
    return [r * 4 + s for r in range(2, 15) for s in range(4)]
