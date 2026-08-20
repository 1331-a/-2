# -*- coding: utf-8 -*-
"""test_lead_lock.py — 优势锁定模式（领先>2000 不 allin + 注码≤1000）。"""
import sys

sys.path.insert(0, ".")

from game_state import parse_request
from strategy import decide
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
    base = {"num_players": 2, "dealer_id": 0, "my_id": 0,
            "my_chips": 15000, "my_cards": [48, 50], "public_cards": [],
            "history": [], "hand": 20, "max_hand": 70,
            "total_win_chips": [0, 0], "total_win_games": [0, 0]}
    base.update(kw)
    return base


# 场景1：领先 3000（>2000）翻后强牌（AA）无人下注 → 注码 ≤1000 且非 allin
st = parse_request(req(total_win_chips=[3000, -3000], public_cards=[46, 6, 1],
                       history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                                {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}]))
a = decide(st, OpponentModel())
check("锁注:领先3000注码≤1000", a.get("act") in ("raise", "check") and
      (a.get("act") != "raise" or a["num"] <= 1000), str(a))
check("锁注:领先3000不allin", a.get("act") != "allin", str(a))

# 场景2：领先 3000 面对 800 下注（min_raise=1600>1000 无法加注）→ call
st = parse_request(req(total_win_chips=[3000, -3000], public_cards=[46, 6, 1],
                       history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                                {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                {"round": 1, "player_id": 1, "action": 800, "action_type": "raise"}]))
a = decide(st, OpponentModel())
check("锁注:领先3000面对大注降级call", a.get("act") in ("call", "fold"), str(a))

# 场景3：领先 3000 + 对手全下 → 无论如何不 allin（弃牌）
st = parse_request(req(total_win_chips=[3000, -3000], public_cards=[46, 6, 1],
                       my_chips=6000,
                       history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                                {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                {"round": 1, "player_id": 1, "action": -2, "action_type": "allin"}]))
a = decide(st, OpponentModel())
check("锁注:领先3000对手全下也弃(不allin)", a == {"act": "fold"}, str(a))

# 对照组：领先 1000（≤2000）不受限 → 可正常大注
st = parse_request(req(total_win_chips=[1000, -1000], public_cards=[46, 6, 1],
                       history=[{"round": 0, "player_id": 0, "action": 2500, "action_type": "raise"},
                                {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}]))
a = decide(st, OpponentModel())
check("锁注对照:领先1000不受限可大注", a.get("act") == "raise" and a["num"] > 1000, str(a))

# 对照组：落后 2000 不受限
st = parse_request(req(total_win_chips=[-2000, 2000], public_cards=[46, 6, 1],
                       history=[{"round": 0, "player_id": 0, "action": 2500, "action_type": "raise"},
                                {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}]))
a = decide(st, OpponentModel())
check("锁注对照:落后2000不受限", a.get("act") == "raise" and a["num"] > 1000, str(a))

print("\n%s" % ("全部通过 ✅" if fails == 0 else "有 %d 项失败 ❌" % fails))
sys.exit(1 if fails else 0)
