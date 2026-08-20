# -*- coding: utf-8 -*-
"""test_allin_jump.py — 第 19 手修复验证 + 对手突袭大注检测测试。"""
import sys

sys.path.insert(0, ".")

from game_state import parse_request
from strategy import _allin_floor_guard, _opp_bet_jumped, decide
from opponent import OpponentModel

fails = 0


def check(name, cond, detail=""):
    global fails
    if not cond:
        fails += 1
        print("[FAIL] %s %s" % (name, detail))
    else:
        print("[PASS] %s" % name)


def req(**kw):
    base = {"num_players": 2, "dealer_id": 0, "my_id": 1,
            "my_chips": 19800, "my_cards": [48, 51], "public_cards": [],
            "history": [], "hand": 0, "max_hand": 50,
            "total_win_chips": [0, 0], "total_win_games": [0, 0]}
    base.update(kw)
    return base


# ---------- 1. 第 19 手：累计已投 5171 跟全下应放行 ----------
# 6♠6♦ + 公对 8 + 领先 +5810(my_id=1, total=[-2905,2905]),
# my_chips=14829（已投 5171），跟全下 2000 → 累计 invest=7171 > 6810 → 放行
stg_h19 = req(my_id=1, my_chips=14829, my_cards=[40, 41],
              public_cards=[4, 40, 22, 44, 22],
              total_win_chips=[-2905, 2905],
              history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                       {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                       {"round": 1, "player_id": 1, "action": 100, "action_type": "raise"},
                       {"round": 1, "player_id": 0, "action": 0, "action_type": "call"},
                       {"round": 2, "player_id": 1, "action": 0, "action_type": "check"},
                       {"round": 2, "player_id": 0, "action": 0, "action_type": "check"},
                       {"round": 3, "player_id": 1, "action": 8000, "action_type": "raise"},
                       {"round": 3, "player_id": 0, "action": 5171, "action_type": "raise"},
                       {"round": 3, "player_id": 1, "action": 2000, "action_type": "raise"}])
check("第19手:累计已投跟全下放行",
      _allin_floor_guard(parse_request(stg_h19), {"act": "allin"}) == {"act": "allin"}, "")

# 对照：领先极大(30000)+短筹码(6000)+跟全下 6000
# → 累计 invest=20000 < 门槛 31000 → 拦截弃牌（极高领先时仍保护）
stg_heavy = req(my_id=1, my_chips=6000, my_cards=[40, 41],
                total_win_chips=[-15000, 15000],  # lead=30000
                history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                         {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                         {"round": 1, "player_id": 1, "action": -2, "action_type": "allin"}])
check("累计拦截:领先极大+已投不足仍弃牌",
      _allin_floor_guard(parse_request(stg_heavy), {"act": "allin"}) == {"act": "fold"}, "")

# ---------- 2. _opp_bet_jumped 检测 ----------
stj1 = req(my_id=0, my_cards=[48, 50], public_cards=[46, 6, 1],
           history=[{"round": 0, "player_id": 1, "action": 200, "action_type": "raise"},
                    {"round": 0, "player_id": 0, "action": 0, "action_type": "call"},
                    {"round": 1, "player_id": 1, "action": 2000, "action_type": "raise"}])
check("jumped:翻牌突袭(200→2000)检测", _opp_bet_jumped(parse_request(stj1)) is True, "")

stj2 = req(my_id=0, my_cards=[48, 50], public_cards=[46, 6, 1],
           history=[{"round": 0, "player_id": 1, "action": 200, "action_type": "raise"},
                    {"round": 0, "player_id": 0, "action": 0, "action_type": "call"},
                    {"round": 1, "player_id": 1, "action": 500, "action_type": "raise"}])
check("jumped:正常节奏不触发", _opp_bet_jumped(parse_request(stj2)) is False, "")

stj3 = req(my_id=0, my_cards=[48, 50], public_cards=[46, 6, 1],
           history=[{"round": 0, "player_id": 1, "action": 5000, "action_type": "raise"}])
check("jumped:首次加注(prior=0)不触发", _opp_bet_jumped(parse_request(stj3)) is False, "")

stj4 = req(my_id=0, my_cards=[48, 50], public_cards=[46, 6, 1],
           history=[{"round": 0, "player_id": 1, "action": 500, "action_type": "raise"},
                    {"round": 0, "player_id": 0, "action": 0, "action_type": "call"},
                    {"round": 1, "player_id": 1, "action": 600, "action_type": "raise"}])
check("jumped:跨轮正常跟注不触发", _opp_bet_jumped(parse_request(stj4)) is False, "")

print("\n%s" % ("全部通过 ✅" if fails == 0 else "有 %d 项失败 ❌" % fails))
sys.exit(1 if fails else 0)
