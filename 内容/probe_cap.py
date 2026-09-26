# -*- coding: utf-8 -*-
"""probe_cap.py — 量化「开池 3.5BB」与翻前 PREFLOP_MAX_BET(1000) 上限的交互。

关注点：3-bet 目标 = 3.0 × 对手开池额，4-bet 目标 = 2.3 × 对手 3bet 额。
开池尺寸上移后，这些目标更早撞到 1000 上限 → 会被 `_normalize` 夹紧甚至
降级为 call（无法合法加注）。本脚本给出「撞线起点」。
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import game_state
import opponent
import strategy

random.seed(11)
strategy.DecisionLogger.enable(False)


def mk(my_id, dealer, my_chips, hole, hist):
    return {"num_players": 2, "dealer_id": dealer, "my_id": my_id,
            "my_chips": my_chips, "my_cards": [c - 8 for c in hole],
            "public_cards": [], "history": hist, "hand": 5, "max_hand": 70,
            "total_win_chips": [0, 0], "total_win_games": [0, 0]}


print("对手开池 → 我方（大盲，AA=超强牌）实际动作   上限 %d" % strategy.PREFLOP_MAX_BET)
for opp_open in (250, 300, 350, 400, 500, 800):
    st = game_state.parse_request(mk(1, 0, 19900, [56, 58],
        [{"round": 0, "player_id": 0, "action": opp_open, "action_type": "raise"}]))
    a = strategy.decide(st, opponent.OpponentModel())
    print("  对手 %-4d  →  %s" % (opp_open, a))

print()
print("3-bet 目标 = 3.0 × 对手开池额：")
for o in (250, 300, 333, 350, 400):
    t = 3.0 * o
    print("  对手 %-4d → 目标 %-6.0f  撞 1000? %s" % (o, t, t > strategy.PREFLOP_MAX_BET))

print()
print("结论：开池 2.5BB(250) 时 3-bet 目标 750 不撞线；")
print("      开池 3.5BB(350) 时 3-bet 目标 1050 已撞线，被夹到 1000。")
print("      → 撞线起点从「对手开池 >333」提前到「对手开池 >333」，")
print("        但**我方自己的开池** 350 使对手的 3-bet 更容易撞线（其视角），")
print("        且我方 4-bet（2.3×对手3bet）在对手 3bet ≥435 时即无法合法加注。")
