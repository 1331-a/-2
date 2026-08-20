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
check("锁注对照:领先1000不锁但增量上限1000", a == {"act": "raise", "num": 1000}, str(a))

# 对照组：落后 2000 不受限
st = parse_request(req(total_win_chips=[-2000, 2000], public_cards=[46, 6, 1],
                       history=[{"round": 0, "player_id": 0, "action": 2500, "action_type": "raise"},
                                {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}]))
a = decide(st, OpponentModel())
check("锁注对照:落后2000不锁但增量上限1000", a == {"act": "raise", "num": 1000}, str(a))

# ---------- 加注增量上限（全局：增量≤1000） ----------
# 翻后无人下注大底池价值注（pot 3000）→ 增量≤1000 → 总注额≤1000
st = parse_request(req(total_win_chips=[0, 0], public_cards=[46, 6, 1], my_chips=15000,
                       history=[{"round": 0, "player_id": 0, "action": 2500, "action_type": "raise"},
                                {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}]))
a = decide(st, OpponentModel())
check("增量上限:大底池价值注增量≤1000", a.get("act") == "raise" and a["num"] <= 1000, str(a))
# 面对下注加注（to_call=300）→ 总注额 ≤ 300+1000=1300
st = parse_request(req(total_win_chips=[0, 0], public_cards=[46, 6, 1], my_chips=18500,
                       history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                                {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                {"round": 1, "player_id": 1, "action": 300, "action_type": "raise"}]))
a = decide(st, OpponentModel())
check("增量上限:面对下注加注增量≤1000", a.get("act") == "raise" and a["num"] <= 1300, str(a))
# 对照组：翻前开池 2.5BB（增量 200<1000）不受影响
st = parse_request(req(total_win_chips=[0, 0], my_chips=19950, my_cards=[48, 51], history=[]))
a = decide(st, OpponentModel())
check("增量上限:开池2.5BB不压", a == {"act": "raise", "num": 250}, str(a))

print("\n%s" % ("全部通过 ✅" if fails == 0 else "有 %d 项失败 ❌" % fails))
sys.exit(1 if fails else 0)
