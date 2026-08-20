# -*- coding: utf-8 -*-
"""test_delayed.py — 延迟施压（delayed aggression）测试。"""
import sys

sys.path.insert(0, ".")

from game_state import parse_request
from strategy import _delayed_aggression_bonus
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
            "my_chips": 19800, "my_cards": [24, 17], "public_cards": [],
            "history": [], "hand": 0, "max_hand": 50,
            "total_win_chips": [0, 0], "total_win_games": [0, 0]}
    base.update(kw)
    return base


def hist_3_check():
    """翻前 raise/call + 翻牌 check-check + 转牌 check-check（3 街持续过牌）"""
    return [
        {"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
        {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
        {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
        {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
        {"round": 2, "player_id": 1, "action": 0, "action_type": "check"},
        {"round": 2, "player_id": 0, "action": 0, "action_type": "check"},
    ]


# ---------- 延迟施压加成 ----------
# 河牌（cur_round=3）前两街都 check-check，我方河牌首次出手 → FULL(0.20)
stp_full = parse_request(req(public_cards=[46, 22, 5, 7, 11], history=hist_3_check()))
check("delayed:上两街check-check→河牌首次出手(FULL=0.20)",
      _delayed_aggression_bonus(stp_full) == 0.20, "")
# 转牌（cur_round=2）翻牌 check-check，转牌首次出手 → PARTIAL(0.10)
stp_part = parse_request(req(public_cards=[46, 22, 5, 7], history=hist_3_check()[:4]))
check("delayed:翻牌check-check→转牌首次出手(PARTIAL=0.10)",
      _delayed_aggression_bonus(stp_part) == 0.10, "")
# 对照：仅翻牌 check-check（无转牌 check）→ 转牌首次出手仍是 PARTIAL
hist_only_flop = [
    {"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
    {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
    {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
    {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
]
stp_part2 = parse_request(req(public_cards=[46, 22, 5, 7], history=hist_only_flop))
check("delayed:仅翻牌check-check→转牌(PARTIAL=0.10)",
      _delayed_aggression_bonus(stp_part2) == 0.10, "")
# 对照：无 check → 0
no_chk = parse_request(req(public_cards=[46, 22, 5],
                          history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                                   {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                   {"round": 1, "player_id": 1, "action": 300, "action_type": "raise"}]))
check("delayed:无check不触发", _delayed_aggression_bonus(no_chk) == 0.0, "")
# 对照：仅对手 check 我方未 check（如我方下注）→ 0
opp_only = parse_request(req(public_cards=[46, 22, 5],
                            history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                                     {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                     {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
                                     {"round": 1, "player_id": 0, "action": 300, "action_type": "raise"}]))
check("delayed:仅对手check不触发(我方没check)",
      _delayed_aggression_bonus(opp_only) == 0.0, "")

print("\n%s" % ("全部通过 ✅" if fails == 0 else "有 %d 项失败 ❌" % fails))
sys.exit(1 if fails else 0)
